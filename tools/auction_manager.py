#!/usr/bin/python3

import base64
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
import os

AUCTION_SERV_URL = "http://localhost:5000"
PORT_NUMBER = 9000
app = Flask(__name__, static_url_path='/static')
cors = CORS(app)
# cors = CORS(app, resources={r'/': {'origins': f'http://localhost:80'}})
app.config['SECRET_KEY'] = '*********'
app.config['DEBUG'] = True
socketio = SocketIO(app, cors_allowed_origins='*')

server_msg = {}
auction_state = {}
next_competition = False
current_competition_id = None
len_active_auctions = 0
sequential = False
temp_results = {}
def_results = {}
results = {}
goods_image = []    
still_to_sell = []

class CreateAuctions(FlaskForm):
    '''
        Create single or sequential auctions.
    '''
    auction_type = SelectField("What type of auction do you want to create?",
                               choices=[("sequential", "Enchères séquentielles"), ("single", "Enchères indépendantes")])
    submit = SubmitField("Commencer")


@app.route('/', methods=['GET', 'POST'])
def index():
    with open('tools/seq_auctions.json') as sequential_auctions_data:
        sequential_auctions = json.load(sequential_auctions_data)
        sequential_auction = [(sequential_auctions[i]['competition_id'], sequential_auctions[i]['title'])
                    for i in range(len(sequential_auctions))]

    with open('tools/sing_auctions.json') as simple_auctions_data:
        simple_auctions = json.load(simple_auctions_data)
        simple_auction = [(simple_auctions[i]['competition_id'], simple_auctions[i]['title'])
                    for i in range(len(simple_auctions))]
    form = CreateAuctions()
    if form.validate_on_submit():
        session['auction_type'] = form.auction_type.data
        if session['auction_type'] == "sequential":
            for auction in sequential_auction:
                for i in range(len(sequential_auctions)):
                    if sequential_auctions[i]['competition_id'] == auction[0]:
                        for j in  sequential_auctions[i]['goods']:
                            file_path = os.path.join('tools', j['good_image'])
                            with open(file_path, 'rb') as good_image:
                                j['good_image'] = base64.b64encode(good_image.read()).decode('utf-8')
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
            for auction in simple_auction:
                for i in range(len(simple_auctions)):
                    if simple_auctions[i]['competition_id'] == auction[0]:
                        for j in  simple_auctions[i]['goods']:
                            file_path = os.path.join('tools', j['good_image'])
                            with open(file_path, 'rb') as good_image:
                                j['good_image'] = base64.b64encode(good_image.read()).decode('utf-8')
                chosen_auction = json.dumps(
                    next((simple_auctions[i] for i in range(len(simple_auctions))
                    if simple_auctions[i]['competition_id'] == auction[0]))
                )
                req = urllib.request.Request(
                    f'{AUCTION_SERV_URL}/competitions',
                    headers={'Content-type': 'application/json'},
                    data=chosen_auction.encode('utf-8')
                )        
                res = urllib.request.urlopen(req)
                msg = res.read().decode('utf-8')
                # print(msg)
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
        competition_id = SelectField('Choisissez la compétition',
                                choices=[competition[i]
                                        for i in range(len(competition))],
                                validators=[DataRequired()])
        submit = SubmitField("Lancer l'enchère")
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
        print(start_message)
        return redirect(url_for('active_auction', competition_id=session["competition_id"]))
        # socketio.emit('redirect', {'url': url_for('active_auction', competition_id=competition_id)})
    return render_template('start_auction.html', form=form, htmldoc=htmldoc, agent_ids=agent_ids)

@app.route('/launch/<competition_id>', methods=['GET', 'POST'])
def active_auction(competition_id):
    global server_msg, next_competition, auction_state, current_competition_id, len_active_auctions, sequential, goods_image, still_to_sell, def_results, temp_results
    current_competition_id = competition_id
    message = request.data.decode('utf-8')
    if message:
        next_competition = False
        server_msg = json.loads(message)
        auction_state = json.loads(server_msg['auction_state'])
        goods = server_msg["goods"]
        still_to_sell = goods
        if 'sold' in auction_state:
            still_to_sell = [good for idx, good in enumerate(goods) if not auction_state['sold'][idx]]
        print(message)
        goods_image = []
        for good in server_msg['goods']:
            req = urllib.request.Request(f'{AUCTION_SERV_URL}/{competition_id}/goods/{urllib.parse.quote(good)}', method='GET')
            res = urllib.request.urlopen(req)
            good_image_byte64 = json.loads(res.read().decode('utf-8'))
            goods_image.append({'good_name': good, 'good_image': good_image_byte64[0]['good_image']})
        socketio.emit('reload', 'new message')
        # req = urllib.request.Request(f'{AUCTION_SERV_URL}/competitions', method='GET')
        # res = urllib.request.urlopen(req)
        # active_competitions = json.loads(res.read().decode('utf-8'))
        @socketio.on('force_ready')
        def force_ready(message):
            print(message)
            req = urllib.request.Request(f'{AUCTION_SERV_URL}/{competition_id}/next',
                                        method='GET')
            res = urllib.request.urlopen(req)
            msg = res.read().decode('utf-8')
            print(msg)
        if auction_state['propositions']['terminated'] == True: 
            results[competition_id] = auction_state
            print(results)
            req = urllib.request.Request(f'{AUCTION_SERV_URL}/competitions', method='GET')
            res = urllib.request.urlopen(req)
            active_competitions = json.loads(res.read().decode('utf-8'))
            len_active_auctions = len(active_competitions)
            sequential = active_competitions[0]['auction_type'] == 'sequential'
            if len(active_competitions) > 1 and active_competitions[0]['auction_type'] == 'sequential':
                next_competition = True
                temp_results = {}
                socketio.emit('redirect', {'url': url_for('preliminary_results')})
            elif len(active_competitions) > 1 and active_competitions[0]['auction_type'] == 'single':
                next_competition = True
                def_results = {}
                socketio.emit('redirect', {'url': url_for('final_results')})
                # return redirect(url_for('final_results'))
            else:
                next_competition = False
                def_results = {}
                socketio.emit('redirect', {'url': url_for('final_results')})
        return {'response': 'received'}
    return render_template('active_auction.html', 
                           competition_id=competition_id, 
                           start_message=start_message, 
                           message=server_msg, 
                           next_competition=next_competition, 
                           propositions=auction_state['propositions'],
                           auction_state=auction_state,
                           len_active_auctions=len_active_auctions,
                           sequential=sequential,
                           goods_image=goods_image,
                           still_to_sell=still_to_sell)
    #  return render_template('active_auction.html', competition_id=competition_id, start_message=start_message, message=json.loads(message))


@socketio.on('back_to_home')
def goto_home(message):
    print(message)
    req = urllib.request.Request(f'{AUCTION_SERV_URL}/{current_competition_id}',
                                method='DELETE')
    res = urllib.request.urlopen(req)
    msg = res.read().decode('utf-8')
    print(msg)
    print(f'{current_competition_id} deleted.')
    socketio.emit('redirect', {'url': url_for('index')})
    
@socketio.on('next_auction')
def goto_launch(message):
    print(message)
    req = urllib.request.Request(f'{AUCTION_SERV_URL}/{current_competition_id}',
                                method='DELETE')
    res = urllib.request.urlopen(req)
    msg = res.read().decode('utf-8')
    print(msg)
    print(f'{current_competition_id} deleted.')
    socketio.emit('redirect', {'url': url_for('start_auction')})

@app.route('/preliminary-results', methods=['GET', 'POST', 'DELETE'])
def preliminary_results():
    global temp_results
    if request.method == 'POST':
        message = request.data.decode('utf-8')
        msg = json.loads(message)
        print(message)
        temp_results[msg['agent_id']] = {}
        temp_results[msg['agent_id']]['utility'] = msg['utility']
        temp_results[msg['agent_id']]['rationality'] = msg['rationality']
        temp_results[msg['agent_id']]['budget'] = msg['final_budget']
        temp_results[msg['agent_id']]['allocation'] = msg['new_allocation']
        socketio.emit('reload', msg['agent_id'])
        # @socketio.on('next_auction')
        # def goto_launch(message):
        #     print(message)
        #     req = urllib.request.Request(f'{AUCTION_SERV_URL}/{current_competition_id}',
        #                                 method='DELETE')
        #     res = urllib.request.urlopen(req)
        #     msg = res.read().decode('utf-8')
        #     print(msg)
        #     print(f'{current_competition_id} deleted.')
        #     socketio.emit('redirect', {'url': url_for('start_auction')})
    return render_template('preliminary_results.html', preliminary_results=temp_results)

@app.route('/final-results', methods=['GET', 'POST', 'DELETE'])
def final_results():
    global def_results
    if request.method == 'POST':
        message = request.data.decode('utf-8')
        print(message)
        msg = json.loads(message)
        def_results[msg['agent_id']] = {}
        def_results[msg['agent_id']]['utility'] = msg['utility']
        def_results[msg['agent_id']]['rationality'] = msg['rationality']
        def_results[msg['agent_id']]['budget'] = msg['final_budget']
        def_results[msg['agent_id']]['allocation'] = msg['new_allocation']
        socketio.emit('reload', msg['agent_id'])
        # @socketio.on('back_to_home')
        # def goto_home(message):
        #     print(message)
        #     req = urllib.request.Request(f'{AUCTION_SERV_URL}/{current_competition_id}',
        #                                 method='DELETE')
        #     res = urllib.request.urlopen(req)
        #     msg = res.read().decode('utf-8')
        #     print(msg)
        #     print(f'{current_competition_id} deleted.')
        #     socketio.emit('redirect', {'url': url_for('index')})
        # @socketio.on('next_auction')
        # def goto_launch(message):
        #     print(message)
        #     req = urllib.request.Request(f'{AUCTION_SERV_URL}/{current_competition_id}',
        #                                 method='DELETE')
        #     res = urllib.request.urlopen(req)
        #     msg = res.read().decode('utf-8')
        #     print(msg)
        #     print(f'{current_competition_id} deleted.')
        #     socketio.emit('redirect', {'url': url_for('start_auction')})
    # if request.method == 'GET':
    #     return {'response': 'received'}
    return render_template('final_results.html', final_results=def_results, next_competition=next_competition)

if __name__ == '__main__':
    socketio.run(app, port=PORT_NUMBER)