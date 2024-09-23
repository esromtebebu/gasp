#!/usr/bin/python3

import urllib.request, urllib.parse
import requests
import json
import time
from flask import Flask, render_template, session, redirect, url_for, jsonify, request
from flask_wtf import FlaskForm
from flask_cors import CORS
from wtforms import SelectField, SubmitField, SelectMultipleField
from wtforms.validators import DataRequired
from flask_socketio import SocketIO, send, emit

AUCTION_SERV_URL = "http://localhost:5000"
PORT_NUMBER = 9000
app = Flask(__name__)
cors = CORS(app)
# cors = CORS(app, resources={r'/': {'origins': f'http://localhost:80'}})
app.config['SECRET_KEY'] = '*********'
app.config['DEBUG'] = True
socketio = SocketIO(app, cors_allowed_origins='*')

server_msg = {}
auction_state = {}
next_competition = False
results = {}

with open('tools/sequential_auctions.json') as sequential_auctions_data:
    sequential_auctions = json.load(sequential_auctions_data)
    sequential_auction = [(sequential_auctions[i]['competition_id'], sequential_auctions[i]['title'])
                for i in range(len(sequential_auctions))]

with open('tools/single_auctions.json') as simple_auctions_data:
    simple_auctions = json.load(simple_auctions_data)
    simple_auction = [(simple_auctions[i]['competition_id'], simple_auctions[i]['title'])
                for i in range(len(simple_auctions))]

class CreateAuctions(FlaskForm):
    '''
        Create single or sequential auctions.
    '''
    auction_type = SelectField("What type of auction do you want to create?",
                               choices=[("sequential", "Sequential Auctions"), ("single", "Single Auctions")])
    submit = SubmitField("Proceed")


@app.route('/', methods=['GET', 'POST'])
def index():
    form = CreateAuctions()
    if form.validate_on_submit():
        session['auction_type'] = form.auction_type.data
        if session['auction_type'] == "sequential":
            for auction in sequential_auction:
                chosen_auction = json.dumps(
                    next((sequential_auctions[i] for i in range(len(sequential_auctions))
                    if sequential_auctions[i]['competition_id'] == auction[0]))
                )
                req = urllib.request.Request(
                    f'{AUCTION_SERV_URL}/competitions',
                    headers={'Content-type': 'application/json'},
                    data=chosen_auction.encode('utf-8')
                )        
                res = urllib.request.urlopen(req)
                msg = res.read().decode('utf-8')
                print(msg)
        else:
            chosen_auction = json.dumps(
                next((simple_auctions[i] for i in range(len(simple_auctions))))
            )
            req = urllib.request.Request(
                f'{AUCTION_SERV_URL}/competitions',
                headers={'Content-type': 'application/json'},
                data=chosen_auction.encode('utf-8')
            )        
            res = urllib.request.urlopen(req)
            msg = res.read().decode('utf-8')
            print(msg)
        return redirect(url_for('start_auction'))
    return render_template('create_auctions.html', form=form)       

@app.route('/launch', methods=['GET', 'POST'])
def start_auction():
    global start_message
    req = urllib.request.Request(f'{AUCTION_SERV_URL}/competitions', method='GET')
    res = urllib.request.urlopen(req)
    available_competitions = json.loads(res.read().decode('utf-8'))
    competition = [(available_competitions[i]['competition_id'], available_competitions[i]['title'])
                for i in range(len(available_competitions))]
    class StartAuction(FlaskForm):
        '''
            Start auction.
        '''
        competition_id = SelectField('Start a competition',
                                choices=[competition[i]
                                        for i in range(len(competition))],
                                validators=[DataRequired()])
        submit = SubmitField('Start Auction')
    form = StartAuction()
    htmldoc = None
    agent_ids = []
    if request.method == 'POST':
        agent_id = request.data.decode('utf-8')
        print(agent_id)
        agent_ids.append(agent_id)
        socketio.emit('agent_id', agent_id)
        # return f'{agent_id} successfully joined auction.'
    if form.validate_on_submit():
        session['competition_id'] = form.competition_id.data
        req = urllib.request.Request(f'{AUCTION_SERV_URL}/{session["competition_id"]}/start', method='GET')
        res = urllib.request.urlopen(req)
        start_message = res.read().decode('utf-8')
        print(htmldoc)
        return redirect(url_for('active_auction', competition_id=session["competition_id"]))
        # socketio.emit('redirect', {'url': url_for('active_auction', competition_id=competition_id)})
    return render_template('start_auction.html', form=form, htmldoc=htmldoc, agent_ids=agent_ids)

@app.route('/launch/<competition_id>', methods=['GET', 'POST', 'DELETE'])
def active_auction(competition_id):
    global server_msg, next_competition, auction_state
    message = request.data.decode('utf-8')
    if message:
        next_competition = False
        server_msg = json.loads(message)
        auction_state = json.loads(server_msg['auction_state'])
        print(auction_state['propositions'])
        socketio.emit('reload', 'new message')
        req = urllib.request.Request(f'{AUCTION_SERV_URL}/competitions', method='GET')
        res = urllib.request.urlopen(req)
        active_competitions = json.loads(res.read().decode('utf-8'))
        if auction_state['propositions']['terminated'] == True:
            results[competition_id] = auction_state
            print(results)
            if len(active_competitions) > 1:
                next_competition = True
                @socketio.on('next_auction')
                def goto_next_bid(message):
                    print(message)
                    req = urllib.request.Request(f'{AUCTION_SERV_URL}/{competition_id}',
                                                method='DELETE')
                    res = urllib.request.urlopen(req)
                    msg = res.read().decode('utf-8')
                    print(msg)
                    print(f'{competition_id} deleted.')
                    # return redirect(url_for('start_auction'))
                    socketio.emit('redirect', {'url': url_for('start_auction')})
            else:
                next_competition = False
                @socketio.on('back_to_home')
                def goto_home(message):
                    req = urllib.request.Request(f'{AUCTION_SERV_URL}/{competition_id}',
                                                method='DELETE')
                    res = urllib.request.urlopen(req)
                    msg = res.read().decode('utf-8')
                    print(msg)
                    print(f'{competition_id} deleted.')
                    socketio.emit('redirect', {'url': url_for('index')})
        return {'response': 'received'}
    return render_template('active_auction.html', 
                           competition_id=competition_id, 
                           start_message=start_message, 
                           message=server_msg, 
                           next_competition=next_competition, 
                           auction_state=auction_state['propositions'])
    #  return render_template('active_auction.html', competition_id=competition_id, start_message=start_message, message=json.loads(message))

@app.route('/preliminary-results', methods=['GET', 'POST'])
def preliminary_results():
    return render_template('preliminary_results.html', auction_state=auction_state['propositions'])
if __name__ == '__main__':
    socketio.run(app, port=PORT_NUMBER)