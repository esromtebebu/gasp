#!/usr/bin/env python

import json
from flask import Flask, request, render_template, session, redirect, url_for
from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField, SelectMultipleField, RadioField
from wtforms.validators import DataRequired
from flask_socketio import SocketIO, send, emit
from threading import Thread
import time
import urllib.request
from multiprocessing import Lock
import ast
import html
import sys

BIDDER_PORT = 38400
AUCTION_SERV_URL = "http://localhost:5000"

app = Flask(__name__)
app.config['SECRET_KEY'] = '*********'
app.config['DEBUG'] = True
socketio = SocketIO(app, cors_allowed_origins='*')

valuations = {}
budgets = {}
agent_ids = {}
competition_id = None
goods = None
message = {}
start_message = {}
bid_request = {}
stop_message = {}
abort_message = {}
still_to_bid = {}
state = {}
still_to_sell = None
bid_msg = {}
bid_form = None
lock = Lock()

def log(msg, agent_id):
    with lock:
        sys.stdout.write(f'Bidder {agent_id} > {msg}\n')

@app.route('/', methods=['GET', 'POST'])
def competition():
    req = urllib.request.Request(f'{AUCTION_SERV_URL}/competitions', method='GET')
    res = urllib.request.urlopen(req)
    htmldoc = res.read().decode('utf-8')
    competitions = json.loads(htmldoc)
    class CompetitionForm(FlaskForm):
        competition_choice = SelectField('Competition',
                                  choices=[(competition['competition_id'], competition['competition_id'])
                                           for competition in competitions])
        submit = SubmitField('OK')
    competition_form = CompetitionForm()
    if competition_form.validate_on_submit():
        session['competition_choice'] = competition_form.competition_choice.data
        return redirect(url_for('bidder', competition_id=session['competition_choice']))
    return render_template('competition.html', form=competition_form)

@app.route('/<competition_id>', methods=['GET', 'POST'])
def bidder(competition_id):
    global competition_data
    req = urllib.request.Request(f'{AUCTION_SERV_URL}/{competition_id}', method='GET')
    res = urllib.request.urlopen(req)
    htmldoc = res.read().decode('utf-8')
    competition_data = json.loads(htmldoc)
    class BidderForm(FlaskForm):
        agent_id = SelectField('Agent', 
                                choices=[(agent['id'], agent['id'])
                                        for agent in competition_data['agents']])
        submit = SubmitField(f'Join')
    bidder_form = BidderForm()
    if bidder_form.validate_on_submit():
        session['agent_id'] = bidder_form.agent_id.data
        socketio.emit('agent_id', session['agent_id'])
        print(f'Bidder {session["agent_id"]} joined {competition}.')
        return redirect(url_for('bid', competition_id=competition_id, agent_id=session['agent_id']))
    return render_template('bidder.html', form=bidder_form)

def rational_bid(valuation, budget, agent_id, competition_id, current_price, sold, payments):
    global still_to_sell
    still_to_sell = {good for idx, good in enumerate(goods) if not sold[idx]}
    paid = 0
    bidder_number = list(agent_ids.values()).index(agent_id)
    if len(payments) > bidder_number:
        paid = payments[bidder_number]
    basket_value = 0
    for cn in valuation['child_nodes']:
        if ((cn['value'] >= current_price)
            and (cn['good'] in still_to_sell)
            and (basket_value <= (budget - paid))):
                basket_value += current_price
    return [
        cn['good']
        for cn in valuation['child_nodes']
        if ((cn['value'] >= current_price)
            and (cn['good'] in still_to_sell)
            and (basket_value <= (budget - paid)))
    ]

def send_bid(agent_id, competition_id, selected_goods):
    msg = {
        "message_type": "bid",
        "competition_id": competition_id,
        "agent_id": agent_id,
        "bid": selected_goods
    }
    time.sleep(5)
    log(f'Submitting bid {selected_goods}', agent_id)
    req = urllib.request.Request(f'{AUCTION_SERV_URL}/{competition_id}/{agent_id}/bid',
                                 headers={'Content-type': 'application/json'},
                                 data=json.dumps(msg).encode('utf-8'))
    res = urllib.request.urlopen(req)
    htmldoc = res.read().decode('utf-8')
    log(f'Response received: {htmldoc}', agent_id)
    bid_msg[agent_id] = msg

def truthful_bidder(competition_id, agent_id):
    global valuations, goods, message
    request_data = request.data.decode('utf-8')
    if request_data:
        message = json.loads(request.data.decode("utf-8")) 
        socketio.emit('reload', 'new message')
        if message['agent_id'] == agent_id:
            if message['message_type'] == 'start':
                start_message[agent_id] = message
                state[agent_id] = 'start'
                socketio.emit('reload', 'new message')
                log('start message received', agent_id)
                valuations[agent_id] = json.loads(message['valuation'])
                budgets[agent_id] = message['budget']
                agent_ids[agent_id] = message['agent_id']
                goods = message['goods']
                return {'response': 'ready'}
            if message['message_type'] == 'bid_request':
                bid_request[agent_id] = message
                state[agent_id] = 'bid_request'
                socketio.emit('reload', 'new message')
                log('bid request message received', agent_id)
                auction_state = json.loads(message['auction_state'])['propositions']
                payments = json.loads(message['auction_state'])['joint_payment']
                still_to_bid[agent_id] = rational_bid(valuations[agent_id],
                                            budgets[agent_id],
                                            agent_ids[agent_id],
                                            competition_id,
                                            auction_state['price'],
                                            auction_state['sold'],
                                            list(payments.values()))
                # state[agent_id] = 'bid_submitted'
                # socketio.emit('reload', 'new message')
                return {'response': 'received'}    
            if message['message_type'] == 'stop':
                stop_message[agent_id] = message
                state[agent_id] = 'stop'
                socketio.emit('reload', 'new message')
                log('stop message received', agent_id)
                log('{\n\t'
                    + '\n\t'.join(f'{key}: {value}' for key, value in message.items())
                    + '\n}', agent_id)
                return {'response': 'done'}
            if message['message_type'] == 'abort':
                abort_message[agent_id] = message
                stop_message
                state[agent_id] = 'abort'
                socketio.emit('reload', 'new message')
                log('abort message received', agent_id)
                return {'response': 'done'}
            return {'response': 'Unimplemented request'}
    return render_template('start_bidding.html',
                           message=message,
                           agent_id=agent_id, 
                           state=state, 
                           start_message=start_message, 
                           bid_request=bid_request, 
                           stop_message=stop_message, 
                           abort_message=abort_message, 
                           bid_msg=bid_msg,
                           still_to_sell=still_to_sell,
                           still_to_bid=still_to_bid)

@app.route("/<competition_id>/<agent_id>", methods=["GET", "POST"])
def bid(competition_id, agent_id):
    return truthful_bidder(str(competition_id), agent_id)

@socketio.on('bid_msg')
def receive_bid_msg(msg):
    agent_id = list(msg)[0]
    competition_id = msg['competition_id']
    selected_goods = msg[agent_id]
    print(msg[agent_id][0])
    t = Thread(target=send_bid, args=(agent_ids[agent_id],
                                        competition_id,
                                        selected_goods))
    t.start()
    state[agent_id] = 'bid_submitted'
    socketio.emit('reload', 'new message')

if __name__ == '__main__':
    socketio.run(app, port=BIDDER_PORT)

'''
{% extends "base.html"%}
{% block content %}
<div class="jumbotron">
    {% if state[agent_id] %}
        {{ message }} 
        <br />
        {% if state[agent_id] == 'start' %}
            <h1>Competition started</h1>
            {{ start_message[agent_id] }}
        {% elif state[agent_id] == 'bid_request' %}
            {{ bid_request[agent_id] }}
            <h1>Available goods: {{ still_to_sell }}</h1>
            <br/>
            <h1>{{ agent_id }}, do you want to bid on {{ still_to_bid[agent_id] }}?</h1>
            <form id="bid-form" method='POST'>
                <label for="bid-select">Choose goods:</label>
                <select name="bid" id="bid-select" multiple>
                    <option value="">--Please choose an option--</option>
                    {% for good in still_to_sell %}
                    <option value="{{good}}">{{good}}</option>
                    {% endfor %}
                </select>
                <input type="submit" value="Bid"/>
            </form>
        {% elif state[agent_id] == 'bid_submitted' %}
            <h1>Bid submitted.</h1>
            {{ bid_msg[agent_id] }}
            <br/>
            <h1>Waiting for next state...</h1>
        {% elif state[agent_id] == 'stop' %}  
            <h1>Competition stopped</h1>
            {{ stop_message[agent_id] }}
        {% elif state[agent_id] == 'abort' %}
            <h1>Competition aborted</h1>
            {{ abort_message[agent_id] }}
        {% else %}
            <h1>Server error</h1>
        {% endif %}
    {% else %}
        <h1>Waiting for competition to start</h1>
    {% endif %}
</div>
<script src="https://code.jquery.com/jquery-3.7.0.min.js" integrity="sha256-2Pmvv0kuTBOenSvLm6bvfBSSHrUJ+3A7x6P5Ebd07/g=" crossorigin="anonymous"></script>
<script src="https://cdn.socket.io/4.6.0/socket.io.min.js" integrity="sha384-c79GN5VsunZvi+Q/WObgk2in0CbZsHnjEqvFxC5DxHn9lTfNce2WW6h2pH6u/kF+" crossorigin="anonymous"></script>
<script type="text/javascript">
    var socket_bidder = io.connect('http://127.0.0.1:38400');
    socket_bidder.on('reload', function(msg) {
        location.reload();
    });
    $('#bid-form').on('submit', function(event) {
        event.preventDefault();
        let selectedGoods = $('#bid-select').val();
        socket_bidder.emit('bid_msg', {'{{agent_id}}': selectedGoods, 'competition_id': '{{message["competition_id"]}}'});
    });
</script>
{% endblock %}
'''