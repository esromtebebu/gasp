#!/usr/bin/env python

import json
from flask import Flask, request, render_template, session, redirect, url_for
from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField, StringField, IntegerField
from wtforms.validators import DataRequired
from flask_socketio import SocketIO, send, emit
from flask_cors import CORS
from threading import Thread
from scipy.optimize import linprog
import time
import random
import urllib.request
import urllib.error
from multiprocessing import Lock
import sys
from scipy.optimize import minimize
import numpy as np
import math
import base64
BIDDER_PORT = 38400
AUCTION_SERV_URL = "http://localhost:5000"

app = Flask(__name__, static_url_path='/static')
cors = CORS(app)
app.config['SECRET_KEY'] = '*********'
app.config['DEBUG'] = True
socketio = SocketIO(app, cors_allowed_origins='*')

valuations = {}
allocations = {}
budgets = {}
agent_ids = {}
competition_id = None
goods = None
competition_data = {}
agents_data = {}
competitions = {}
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
mechanism = None
auction_type = None
agent_ids = {}
rationality = {}
utility = {}
acquired_goods = {}
joint_allocation = {}
auction_state = {}
paid = {}
goods_image = {}
players = []
lock = Lock()

def log(msg, agent_id):
    with lock:
        sys.stdout.write(f'Bidder {agent_id} > {msg}\n')

def compute_valuations(valuation, still_to_sell): #still_to_sell -> goods?
    leafy_utility = {}
    ic_utility = {}
    bundles = []
    bounds = ()

    for good in still_to_sell:
        leafy_utility[good] = 0

    for node in valuation['child_nodes']:
        if node['node'] == 'leaf' and node['good'] in still_to_sell:
            leafy_utility[node['good']] += node['value']
            bounds += ((0, node['units']), )
        elif node['node'] == 'leaf' and node['good'] in still_to_sell:
            bundles.append([child_node['good'] for child_node in node['child_nodes']])
            ic_utility[len(bundles) - 1] = node['value']
    return leafy_utility, ic_utility, bundles, bounds

def sea_optimize_internal_based_strategy(leafy_utility, ic_utility, bundles, price, bounds, budget, still_to_sell, acquired_goods, forthcoming_goods):
  p = []
  c = []
  bounds_constraint = []
  for leaf in leafy_utility:
    if leaf in still_to_sell:
        p.append(price - leafy_utility[leaf])
        c.append(-leafy_utility[leaf])
        bounds_constraint.append(bounds[list(leafy_utility.keys()).index(leaf)])
  for bundle in bundles:
    if all((good in acquired_goods) or (good in still_to_sell) or (good in forthcoming_goods) for good in bundle):
      for good in bundle:
        if good in still_to_sell:
          p[still_to_sell.index(good)] -= ic_utility[bundles.index(bundle)]/(len(bundle))
  b_ub = np.array([budget])
  result = linprog(c=p, A_ub=-np.array([c]), b_ub=b_ub, bounds=bounds_constraint, method='highs')
  decision = []
  for good in still_to_sell:
    if result.x is not None and result.x[still_to_sell.index(good)] >= 1:
        decision.append(good)
  return decision

def ssba_optimize_internal_based_strategy(leafy_utility, ic_utility, bundles, bounds, budget, still_to_sell, acquired_goods, forthcoming_goods):
  p = []
  bounds_constraint = []
  for leaf in leafy_utility:
    if leaf in still_to_sell:
        p.append(-leafy_utility[leaf])
        bounds_constraint.append(bounds[list(leafy_utility.keys()).index(leaf)])
  for bundle in bundles:
    if all((good in acquired_goods) or (good in still_to_sell) or (good in forthcoming_goods) for good in bundle):
      for good in bundle:
        if good in still_to_sell:
          p[still_to_sell.index(good)] -= ic_utility[bundles.index(bundle)]/(len(bundle))
  b_ub = np.array([budget])
  result = linprog(c=p, A_ub=-np.array([p]), b_ub=b_ub, bounds=bounds_constraint, method='highs')
  decision = {}
  for good in still_to_sell:
    if result.x is not None:
        decision[good] = result.x[still_to_sell.index(good)]*p[still_to_sell.index(good)]*-1
  return decision

def compute_utility(trades, sold_prices, agent_id):
    leafy_utility, ic_utility, bundles, bounds = compute_valuations(valuations[agent_id], goods)
    for good in trades[agent_id]:
      utility[agent_id] += leafy_utility[good]
      for bundle in bundles:
        if good in bundle and all((good in joint_allocation[agent_id]) for good in bundle if joint_allocation[agent_id][good] != 0):
          utility[agent_id] += ic_utility[bundles.index(bundle)]/len(bundle)
      utility[agent_id] -= sold_prices[goods.index(good)]
    return utility[agent_id]


def send_bid(agent_id, competition_id, selected_goods):
    global bid_msg
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

def update_agent_data(final_budget, competition_id, agent_id, existing_allocation, trades, sold_prices, rationality, auction_type, final):
    data = {
        'final_budget': final_budget,
        'competition_id': competition_id,
        'agent_id': agent_id,
        'new_allocation': existing_allocation[agent_id],
        'utility': compute_utility(trades,  sold_prices, agent_id),
        'rationality': rationality[agent_id],
        'auction_type': auction_type,
        'final': final
    }
    time.sleep(5)
    req = urllib.request.Request(
        f'{AUCTION_SERV_URL}/{competition_id}',
        headers={'Content-type': 'application/json'},
        data=json.dumps(data).encode('utf-8'),
        method='PATCH'
    )        
    res = urllib.request.urlopen(req)
    msg = res.read().decode('utf-8')
    print(msg)  

def update_manager(agent_id, trades, sold_prices, rationality, url, final_budget, existing_allocation):
    data = {
    'agent_id': agent_id,
    'utility': utility[agent_id],
    'rationality': rationality[agent_id],
    'final_budget': final_budget,
    'new_allocation': existing_allocation[agent_id], 
    }
    req = urllib.request.Request(
        f'{url}',
        headers={'Content-type': 'application/json'},
        data=json.dumps(data).encode('utf-8'),
        method='POST'
    )        
    res = urllib.request.urlopen(req)
    msg = res.read().decode('utf-8')
    print(msg) 

with open('bidders/players.json') as players_data:
    players = json.load(players_data)

@app.route('/', methods=['GET', 'POST'])
def competition():
    global agent_ids, competitions
    req = urllib.request.Request(f'{AUCTION_SERV_URL}/competitions', method='GET')
    res = urllib.request.urlopen(req)
    htmldoc = res.read().decode('utf-8')
    competitions = json.loads(htmldoc)
    class CompetitionForm(FlaskForm):
        username = StringField('Pseudonyme', validators=[DataRequired()])
        submit = SubmitField('Rejoindre')
    competition_form = CompetitionForm()
    if competition_form.validate_on_submit():
        session['username'] = competition_form.username.data
        agent_ids[session['username']] = session['username']
        return redirect(url_for('bidder', agent_id=session['username']))
    return render_template('competition.html', form=competition_form, competitions=competitions)

@app.route('/<agent_id>', methods=['GET', 'POST'])
def bidder(agent_id):
    global agents_data, competitions, players
    competition_data = {}
    agents_data[agent_id] = {}
    for competition in competitions:
        print("Attempting to connect to http://localost:5000/" + competition['competition_id'])
        req = urllib.request.Request(f'{AUCTION_SERV_URL}/{competition["competition_id"]}', method='GET')
        res = urllib.request.urlopen(req)
        htmldoc = res.read().decode('utf-8')
        competition_data[competition["competition_id"]] = json.loads(htmldoc)
    for competition_id in competition_data:
        if players:
            for competition in players:
                if competition_data[competition_id]["title"] == competition["title"] and len(competition["agents"]) > 0 and agent_id != "favicon.ico":
                    random_player = random.randint(0, len(competition["agents"]) - 1)
                    agents_data[agent_id][competition_id] = {}
                    agents_data[agent_id][competition_id] = competition["agents"][random_player]
                    agents_data[agent_id][competition_id]["id"] = agent_id
                    agents_data[agent_id][competition_id]["competition_id"] = competition_id
                    agents_data[agent_id][competition_id]["url"] = 'http://localhost:38400/' + agent_id
                    del competition["agents"][random_player]
                    print("rand_num deleted", random_player)
        else:
            with open('bidders/players.json') as players_data:
                players = json.load(players_data)
            for competition in players:
                if competition_data[competition_id]["title"] == competition["title"] and len(competition["agents"]) > 0 and agent_id != "favicon.ico":
                    random_player = random.randint(0, len(competition["agents"]) - 1)
                    agents_data[agent_id][competition_id] = {}
                    agents_data[agent_id][competition_id] = competition["agents"][random_player]
                    agents_data[agent_id][competition_id]["id"] = agent_id
                    agents_data[agent_id][competition_id]["competition_id"] = competition_id
                    agents_data[agent_id][competition_id]["url"] = 'http://localhost:38400/' + agent_id
                    del competition["agents"][random_player]
                    print("rand_num deleted", random_player)

    print("agent_data", agent_id, agents_data[agent_id].keys())
    @socketio.on('bidder_join')
    def receive_bidder_join(msg):
        print(msg)
        agent_id = msg['agent_id']
        agents_data[agent_id] = msg['data']
        for competition_id in agents_data[agent_id]:
            print("competition_id", competition_id)
            req = urllib.request.Request(
                f'{AUCTION_SERV_URL}/{competition_id}',
                headers={'Content-type': 'application/json'},
                data=json.dumps(agents_data[agent_id][competition_id]).encode('utf-8'),
                method='POST'
            )
            res = urllib.request.urlopen(req)
            htmldoc = res.read().decode('utf-8')
            print(htmldoc)
    return render_template('join.html', agent_data=agents_data,
                           agent_id=agent_id)

def truthful_bidder(agent_id):
    global valuations, goods, message, competition_id, allocations, \
        mechanism, auction_type, still_to_sell, rationality, utility, \
        acquired_goods, joint_allocation, auction_state, auction_state, \
        paid, goods_image
    request_data = request.data.decode('utf-8')
    if request_data:
        message = json.loads(request.data.decode("utf-8")) 
        socketio.emit('reload', 'new message')
        if message['agent_id'] == agent_id and agent_id != 'favicon.ico':
            print("///Agent ID" + agent_id)
            if message['message_type'] == 'start':
                start_message[agent_id] = message
                state[agent_id] = 'start'
                socketio.emit('reload', 'new message')
                log('start message received', agent_id)
                competition_id = message['competition_id']
                valuations[agent_id] = json.loads(message['valuation'])
                allocations[agent_id] = json.loads(message['allocation'])
                budgets[agent_id] = message['budget']
                agent_ids[agent_id] = message['agent_id']
                goods = message['goods']
                mechanism = message['mechanism']
                rationality[agent_id] = message['rationality']
                utility[agent_id] = message['utility']
                auction_type = message['auction_type']
                acquired_goods[agent_id] = []
                goods_image = {}
                paid[agent_id] = 0
                for good in goods:
                    req = urllib.request.Request(f'{AUCTION_SERV_URL}/{competition_id}/goods/{urllib.parse.quote(good)}', method='GET')
                    res = urllib.request.urlopen(req)
                    good_image_byte64 = json.loads(res.read().decode('utf-8'))
                    goods_image[good] = {'good_name': good, 'good_image': good_image_byte64[0]['good_image']}
                print(agents_data)
                print(allocations[agent_id], agent_id)
                for good in allocations[agent_id]:
                    if allocations[agent_id][good] != 0:
                        acquired_goods[agent_id].append(good)
                return {'response': 'ready'}
            if message['message_type'] == 'bid_request':
                bid_request[agent_id] = message
                joint_allocation = json.loads(message['auction_state'])['joint_allocation']
                state[agent_id] = 'bid_request'
                log('bid request message received', agent_id)
                auction_state = json.loads(message['auction_state'])['propositions']
                payments = json.loads(message['auction_state'])['joint_payment']       
                still_to_sell = [good for idx, good in enumerate(goods) if not auction_state['sold'][idx]]
                paid[agent_id] = 0
                if agent_id in payments.keys():
                    paid[agent_id] = payments[agent_id]
                if agent_id in joint_allocation:
                    for good in joint_allocation[agent_id]:
                        if good not in acquired_goods[agent_id]:
                            acquired_goods[agent_id].append(good)
                socketio.emit('reload', 'new message')
                # print(goods_image)
                return {'response': 'received'}    
            if message['message_type'] == 'stop':
                stop_message[agent_id] = message
                state[agent_id] = 'stop'
                socketio.emit('reload', 'new message')
                log('stop message received', agent_id)
                log('{\n\t'
                    + '\n\t'.join(f'{key}: {value}' for key, value in message.items())
                    + '\n}', agent_id)
                req = urllib.request.Request(f'{AUCTION_SERV_URL}/competitions', method='GET')
                res = urllib.request.urlopen(req)
                active_competitions = json.loads(res.read().decode('utf-8'))
                existing_allocation = {}
                if len(active_competitions) > 1 and auction_type == 'sequential':
                    for competition in active_competitions:
                        payments = json.loads(message['auction_state'])['joint_payment']
                        joint_allocation = json.loads(message['auction_state'])['joint_allocation']
                        trades = json.loads(message['auction_state'])['joint_trade']
                        sold_prices = json.loads(message['auction_state'])['propositions']['sold_prices']
                        new_allocation = {}
                        if agent_id in joint_allocation:
                            new_allocation[agent_id] = {}
                            for good in joint_allocation[agent_id]:
                                new_allocation[agent_id][good] = joint_allocation[agent_id][good]
                        if competition['competition_id'] != competition_id:
                            paid[agent_id] = 0
                            existing_allocation[agent_id] = {}
                            if agent_id in payments.keys():
                                paid[agent_id] = payments[agent_id]
                                final_budget = budgets[agent_id] - paid[agent_id]
                                req = urllib.request.Request(f'{AUCTION_SERV_URL}/{competition["competition_id"]}', method='GET')
                                res = urllib.request.urlopen(req)
                                competition_data = json.loads(res.read().decode('utf-8'))
                                for agent in competition_data["agents"]:
                                    if agent["id"] == agent_id:
                                        existing_allocation[agent_id] = agent["allocation"]
                                for good in new_allocation[agent_id]:
                                    existing_allocation[agent_id][good] = new_allocation[agent_id][good]
                                t = Thread(target=update_agent_data, args=(final_budget, competition["competition_id"], agent_id, existing_allocation, trades, sold_prices, rationality, auction_type, 'False'))
                                t.start() 
                else:
                    payments = json.loads(message['auction_state'])['joint_payment']
                    joint_allocation = json.loads(message['auction_state'])['joint_allocation']
                    trades = json.loads(message['auction_state'])['joint_trade']
                    sold_prices = json.loads(message['auction_state'])['propositions']['sold_prices']
                    new_allocation = {}
                    if agent_id in joint_allocation:
                        new_allocation[agent_id] = {}
                        for good in joint_allocation[agent_id]:
                            new_allocation[agent_id][good] = joint_allocation[agent_id][good]
                    paid[agent_id] = 0
                    final_budget = budgets[agent_id]
                    existing_allocation[agent_id] = {}
                    if agent_id in payments.keys():
                        paid[agent_id] = payments[agent_id]
                        final_budget = budgets[agent_id] - paid[agent_id]
                        req = urllib.request.Request(f'{AUCTION_SERV_URL}/{competition_id}', method='GET')
                        res = urllib.request.urlopen(req)
                        competition_data = json.loads(res.read().decode('utf-8'))
                        for agent in competition_data["agents"]:
                            if agent["id"] == agent_id:
                                existing_allocation[agent_id] = agent["allocation"]
                        for good in new_allocation[agent_id]:
                            existing_allocation[agent_id][good] = new_allocation[agent_id][good]
                    t = Thread(target=update_agent_data, args=(final_budget, competition_id, agent_id, existing_allocation, trades, sold_prices, rationality, auction_type, 'True'))
                    t.start() 
                if len(active_competitions) > 1 and auction_type == 'sequential':
                    payments = json.loads(message['auction_state'])['joint_payment']
                    joint_allocation = json.loads(message['auction_state'])['joint_allocation']
                    trades = json.loads(message['auction_state'])['joint_trade']
                    sold_prices = json.loads(message['auction_state'])['propositions']['sold_prices']
                    new_allocation = {}
                    if agent_id in joint_allocation:
                        new_allocation[agent_id] = {}
                        for good in joint_allocation[agent_id]:
                            new_allocation[agent_id][good] = joint_allocation[agent_id][good]
                    paid[agent_id] = 0
                    final_budget = budgets[agent_id]
                    existing_allocation[agent_id] = {}
                    if agent_id in payments.keys():
                        paid[agent_id] = payments[agent_id]
                        final_budget = budgets[agent_id] - paid[agent_id]
                        req = urllib.request.Request(f'{AUCTION_SERV_URL}/{competition_id}', method='GET')
                        res = urllib.request.urlopen(req)
                        competition_data = json.loads(res.read().decode('utf-8'))
                        for agent in competition_data["agents"]:
                            if agent["id"] == agent_id:
                                existing_allocation[agent_id] = agent["allocation"]
                        for good in new_allocation[agent_id]:
                            existing_allocation[agent_id][good] = new_allocation[agent_id][good]
                    t = Thread(target=update_manager, args=(agent_id, trades, sold_prices, rationality, 'http://localhost:9000/preliminary-results', final_budget, existing_allocation))
                    t.start()
                else:
                    payments = json.loads(message['auction_state'])['joint_payment']
                    joint_allocation = json.loads(message['auction_state'])['joint_allocation']
                    trades = json.loads(message['auction_state'])['joint_trade']
                    sold_prices = json.loads(message['auction_state'])['propositions']['sold_prices']
                    new_allocation = {}
                    if agent_id in joint_allocation:
                        new_allocation[agent_id] = {}
                        for good in joint_allocation[agent_id]:
                            new_allocation[agent_id][good] = joint_allocation[agent_id][good]
                    paid[agent_id] = 0
                    final_budget = budgets[agent_id]
                    existing_allocation[agent_id] = {}
                    if agent_id in payments.keys():
                        paid[agent_id] = payments[agent_id]
                        final_budget = budgets[agent_id] - paid[agent_id]
                        req = urllib.request.Request(f'{AUCTION_SERV_URL}/{competition_id}', method='GET')
                        res = urllib.request.urlopen(req)
                        competition_data = json.loads(res.read().decode('utf-8'))
                        for agent in competition_data["agents"]:
                            if agent["id"] == agent_id:
                                existing_allocation[agent_id] = agent["allocation"]
                        for good in new_allocation[agent_id]:
                            existing_allocation[agent_id][good] = new_allocation[agent_id][good]
                    t = Thread(target=update_manager, args=(agent_id, trades, sold_prices, rationality, 'http://localhost:9000/final-results', final_budget, existing_allocation))
                    t.start()
                for i in competitions:
                    if i['competition_id'] == competition_id:
                        competitions.remove(i)
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
                           still_to_bid=still_to_bid,
                           goods=goods,
                           mechanism=mechanism,
                           goods_image=goods_image,
                           budgets=budgets,
                           paid=paid,
                           agent_data=agents_data,
                           auction_state=auction_state,
                           competition_id=competition_id,
                           valuation=valuations,
                           acquired_goods=acquired_goods)

@app.route("/<agent_id>/play", methods=["GET", "POST", "PATCH"])
def bid(agent_id):
    return truthful_bidder(agent_id)

@socketio.on('bid_msg')
def receive_bid_msg(msg):
    agent_id = list(msg)[0]
    competition_id = msg['competition_id']
    selected_goods = msg[agent_id]
    bid_msg[agent_id] = selected_goods
    print(msg)
    leafy_utility, ic_utility, bundles, bounds = compute_valuations(valuations[agent_id], still_to_sell)
    if agent_id in joint_allocation and agent_id != 'favicon.ico':
        for good in joint_allocation[agent_id]:
            if good not in acquired_goods[agent_id]:
                acquired_goods[agent_id].append(good)
    print(f"Acquired goods for {agent_id}", acquired_goods[agent_id])
    forthcoming_goods = {}
    forthcoming_goods[agent_id] = []
    for bundle in bundles:
        for good in bundle:
            if good not in acquired_goods and good not in still_to_sell and good not in allocations[agent_id]:
                forthcoming_goods[agent_id].append(good)
    if mechanism == 'SAA' or mechanism == 'SDA':
        rational_bid = sea_optimize_internal_based_strategy(leafy_utility, ic_utility, bundles, auction_state["price"], bounds, budgets[agent_id] - paid[agent_id], still_to_sell, acquired_goods[agent_id], forthcoming_goods[agent_id])
        for good in rational_bid:
            if good in selected_goods:
                rationality[agent_id] += 1
            else:
                rationality[agent_id] -= 1
        for good in selected_goods:
            if good not in rational_bid:
                rationality[agent_id] -= 1
        if len(rational_bid) == 0:
            rationality[agent_id] += len(still_to_sell)
    else:
        rational_bid = ssba_optimize_internal_based_strategy(leafy_utility, ic_utility, bundles, bounds, budgets[agent_id], still_to_sell, acquired_goods[agent_id], forthcoming_goods[agent_id])
        print(rational_bid, selected_goods)
        for good in selected_goods:
            if rational_bid[good]*.9 <= selected_goods[good] <= rational_bid[good]*1.1:
                rationality[agent_id] += 1
            else:
                rationality[agent_id] -= 1
    t = Thread(target=send_bid, args=(agent_ids[agent_id],
                                        competition_id,
                                        selected_goods))
    t.start()
    state[agent_id] = 'bid_submitted'
    socketio.emit('reload', 'new message')

if __name__ == '__main__':
    socketio.run(app, port=BIDDER_PORT)