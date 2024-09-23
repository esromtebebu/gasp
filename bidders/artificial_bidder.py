#!/usr/bin/env python

import json
from flask import Flask, request
from threading import Thread
import time
import urllib.request
from multiprocessing import Lock
import sys
import random
import numpy as np
from scipy.optimize import linprog
from flask_socketio import SocketIO

AUCTION_SERV_URL = "http://localhost:5000"
BIDDER_PORT = 8000
app = Flask(__name__)
socketio = SocketIO(app)

valuations = {}
budgets = {}
agent_ids = {}
competition_id = None
goods = None
paid = {}
acquired_goods = {}
mechanism = None
auction_type = None
allocation = {}
agent_type = {}
auction_state = {}
joint_allocation = {}
utility = {}
rationality = {}
lock = Lock()


def log(msg, agent_id):
    with lock:
        sys.stdout.write(f'Bidder {agent_id} > {msg}\n')

def compute_valuations(valuations, still_to_sell): #still_to_sell -> goods?
    leafy_utility = {}
    ic_utility = {}
    bundles = []
    bounds = ()

    for good in still_to_sell:
        leafy_utility[good] = 0
    print("Valuations", valuations)
    for node in valuations['child_nodes']:
        if node['node'] == 'leaf' and node['good'] in still_to_sell:
            leafy_utility[node['good']] += node['value']
            bounds += ((0, node['units']), )
        elif node['node'] == 'leaf' and node['good'] in still_to_sell:
            bundles.append([child_node['good'] for child_node in node['child_nodes']])
            ic_utility[len(bundles) - 1] = node['value']
    return leafy_utility, ic_utility, bundles, bounds

def sea_optimize_risk_averse(leafy_utility, ic_utility, bundles, price, bounds, budget, still_to_sell, acquired_goods):
  p = []
  c = []
  bounds_constraint = []
  for leaf in leafy_utility:
    if leaf in still_to_sell:
        p.append(price - leafy_utility[leaf])
        c.append(price)
        bounds_constraint.append(bounds[list(leafy_utility.keys()).index(leaf)])
  for bundle in bundles:
    if all((good in acquired_goods) or (good in still_to_sell) for good in bundle):
      for good in bundle:
        if good in still_to_sell:
          p[still_to_sell.index(good)] -= ic_utility[bundles.index(bundle)]/(len(bundle)-len([good for good in bundle if good in acquired_goods]))
  b_ub = np.array([budget])
  result = linprog(c=p, A_ub=np.array([c]), b_ub=b_ub, bounds=bounds_constraint, method='highs')
  print(result.x)
  decision = []
  for good in still_to_sell:
    if result.x is not None and result.x[still_to_sell.index(good)] >= 1:
        decision.append(good)
  print("2////////////", decision, p)
  return decision

def sea_stochastic(still_to_sell, price, budget):
    decision = []
    for good in still_to_sell:
        if random.randint(0, 1) > .5 and budget > 0:
           decision.append(good)
           budget -= price
    return decision
        

def sea_optimize_internal_based_strategy(leafy_utility, ic_utility, bundles, price, bounds, budget, still_to_sell, acquired_goods, forthcoming_goods):
  p = []
  c = []
  bounds_constraint = []
  for leaf in leafy_utility:
    if leaf in still_to_sell:
        p.append(price - leafy_utility[leaf])
        c.append(price)
        bounds_constraint.append(bounds[list(leafy_utility.keys()).index(leaf)])
  for bundle in bundles:
    if all((good in acquired_goods) or (good in still_to_sell) or (good in forthcoming_goods) for good in bundle):
      for good in bundle:
        if good in still_to_sell:
          p[still_to_sell.index(good)] -= ic_utility[bundles.index(bundle)]/(len(bundle))
  b_ub = np.array([budget])
  result = linprog(c=p, A_ub=np.array([c]), b_ub=b_ub, bounds=bounds_constraint, method='highs')
  print(result.x)
  decision = []
  for good in still_to_sell:
    # if still_to_sell is not None and good in still_to_sell:
    if result.x is not None and result.x[still_to_sell.index(good)] >= 1:
        decision.append(good)
  return decision

def ssba_optimize_risk_averse(leafy_utility, ic_utility, bundles, bounds, budget, still_to_sell, acquired_goods):
  p = []
  bounds_constraint = []
  for leaf in leafy_utility:
    if leaf in still_to_sell:
        p.append(-leafy_utility[leaf])
        bounds_constraint.append(bounds[list(leafy_utility.keys()).index(leaf)])
  for bundle in bundles:
    if all((good in acquired_goods) or (good in still_to_sell) for good in bundle):
      for good in bundle:
        if good in still_to_sell:
          p[still_to_sell.index(good)] -= ic_utility[bundles.index(bundle)]/(len(bundle)-len([good for good in bundle if good in acquired_goods]))
  b_ub = np.array([budget])
  result = linprog(c=p, A_ub=-np.array([p]), b_ub=b_ub, bounds=bounds_constraint, method='highs')
  decision = {}
  for good in still_to_sell:
    if result.x is not None:
        decision[good] = result.x[still_to_sell.index(good)]*p[still_to_sell.index(good)]*-1
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
  print("Result " + str(result.x))
  print("P: " + str(p))
  print("Still to sell: " + str(still_to_sell))
  decision = {}
  for good in still_to_sell:
    if result.x is not None:
        decision[good] = result.x[still_to_sell.index(good)]*p[still_to_sell.index(good)]*-1
  return decision

def ssba_stochastic(still_to_sell, budget):
    decision = {}
    for good in still_to_sell:
        if budget > 0:
            decision[good] = random.random()*budget
            budget -= decision[good]
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

def send_bid(agent_id, competition_id, still_to_bid):
    msg = {
        "message_type": "bid",
        "competition_id": competition_id,
        "agent_id": agent_id,
        "bid": still_to_bid
    }
    time.sleep(5)
    log(f'Submitting bid {still_to_bid}', agent_id)
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
        'utility': utility[agent_id],
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

def update_manager(agent_id, trades, sold_prices, rationality, url):
    data = {
    'agent_id': agent_id,
    'utility': utility[agent_id],
    'rationality': rationality[agent_id]
    }
    req = urllib.request.Request(
        f'{url}',
        headers={'Content-type': 'application/json'},
        data=json.dumps(data).encode('utf-8'),
        method='POST'
    )        
    res = urllib.request.urlopen(req)
    msg = res.read().decode('utf-8')
    # print(msg) 

def truthful_bidder(agent_id):
    global valuations, goods, competition_id, paid, budgets, acquired_goods, mechanism, allocation, \
    agent_type, auction_state, joint_allocation, utility, rationality, auction_type
    message = json.loads(request.data.decode("utf-8"))
    if message['message_type'] == 'start':
        log('start message received', agent_id)
        valuations[agent_id] = json.loads(message['valuation'])
        budgets[agent_id] = message['budget']
        agent_ids[agent_id] = message['agent_id']
        utility[agent_id] = message['utility']
        rationality[agent_id] = message['rationality']
        competition_id = message['competition_id']
        mechanism = message['mechanism']
        auction_type = message['auction_type']
        goods = message['goods']
        acquired_goods[agent_id] = []
        allocation[agent_id] = json.loads(message['allocation'])
        agent_type[agent_id] = message['agent_type']
        for good in allocation[agent_id]:
            if allocation[agent_id][good] != 0:
                acquired_goods[agent_id].append(good)
        return {'response': 'ready'}
    if message['message_type'] == 'bid_request':
        log('bid request message received', agent_id)
        auction_state = json.loads(message['auction_state'])['propositions']
        payments = json.loads(message['auction_state'])['joint_payment']
        joint_allocation = json.loads(message['auction_state'])['joint_allocation']
        paid[agent_id] = 0
        print(paid)
        if agent_id in payments.keys():
            paid[agent_id] = payments[agent_id]
        if agent_id in joint_allocation:
           for good in joint_allocation[agent_id]:
              acquired_goods[agent_id].append(good)
        still_to_sell = [good for idx, good in enumerate(goods) if not auction_state['sold'][idx]]
        leafy_utility, ic_utility, bundles, bounds = compute_valuations(valuations[agent_id], still_to_sell)
        forthcoming_goods = {}
        forthcoming_goods[agent_id] = []
        print("/////////Budget", budgets, payments, paid)
        for bundle in bundles:
            for good in bundle:
              if good in still_to_sell[agent_id] and good not in still_to_sell and good not in allocation[agent_id]:
                forthcoming_goods[agent_id].append(good)
        if mechanism == 'SAA' or mechanism == 'SDA':
            if agent_type[agent_id] == "artificial_risk_averse":
                still_to_bid = sea_optimize_risk_averse(leafy_utility, ic_utility, bundles, auction_state["price"], bounds, budgets[agent_id] - paid[agent_id], still_to_sell, acquired_goods[agent_id])
                rational_bid = sea_optimize_internal_based_strategy(leafy_utility, ic_utility, bundles, auction_state["price"], bounds, budgets[agent_id] - paid[agent_id], still_to_sell, acquired_goods[agent_id], forthcoming_goods[agent_id])
                for good in rational_bid:
                  if good in still_to_bid:
                      rationality[agent_id] += 1
                  else:
                      rationality[agent_id] -= 1
                for good in still_to_bid:
                   if good not in rational_bid:
                      rationality[agent_id] -= 1
                if len(rational_bid) == 0:
                   rationality[agent_id] += len(still_to_sell)
                t = Thread(target=send_bid, args=(agent_ids[agent_id],
                                                competition_id,
                                                still_to_bid))
                t.start()
            elif agent_type[agent_id] == "artificial_internal_based_strategy":
                still_to_bid = sea_optimize_internal_based_strategy(leafy_utility, ic_utility, bundles, auction_state["price"], bounds, budgets[agent_id] - paid[agent_id], still_to_sell, acquired_goods[agent_id], forthcoming_goods[agent_id])
                rational_bid = sea_optimize_internal_based_strategy(leafy_utility, ic_utility, bundles, auction_state["price"], bounds, budgets[agent_id] - paid[agent_id], still_to_sell, acquired_goods[agent_id], forthcoming_goods[agent_id])
                for good in rational_bid:
                  if good in still_to_bid:
                      rationality[agent_id] += 1
                  else:
                      rationality[agent_id] -= 1
                for good in still_to_bid:
                   if good not in rational_bid:
                      rationality[agent_id] -= 1   
                if len(rational_bid) == 0:
                    rationality[agent_id] += len(still_to_sell)      
                t = Thread(target=send_bid, args=(agent_ids[agent_id],
                                                competition_id,
                                                still_to_bid))
                t.start()
            else:
                still_to_bid = sea_stochastic(still_to_sell, auction_state["price"], budgets[agent_id] - paid[agent_id])
                rational_bid = sea_optimize_internal_based_strategy(leafy_utility, ic_utility, bundles, auction_state["price"], bounds, budgets[agent_id] - paid[agent_id], still_to_sell, acquired_goods[agent_id], forthcoming_goods[agent_id])
                for good in rational_bid:
                  if good in still_to_bid:
                      rationality[agent_id] += 1
                  else:
                      rationality[agent_id] -= 1
                for good in still_to_bid:
                   if good not in rational_bid:
                      rationality[agent_id] -= 1         
                t = Thread(target=send_bid, args=(agent_ids[agent_id],
                                                competition_id,
                                                still_to_bid))
                t.start()         
        else:
            if agent_type[agent_id] == "artificial_risk_averse":
                still_to_bid = ssba_optimize_risk_averse(leafy_utility, ic_utility, bundles, bounds, budgets[agent_id], still_to_sell, acquired_goods[agent_id])
                rational_bid = ssba_optimize_internal_based_strategy(leafy_utility, ic_utility, bundles, bounds, budgets[agent_id], still_to_sell, acquired_goods[agent_id], forthcoming_goods[agent_id])
                for good in still_to_bid:
                    if rational_bid[good]*.9 <= still_to_bid[good] <= rational_bid[good]*1.1:
                        rationality[agent_id] += 1
                    else:
                        rationality[agent_id] -= 1
                t = Thread(target=send_bid, args=(agent_ids[agent_id],
                                                competition_id,
                                                still_to_bid))
                t.start() 
            elif agent_type[agent_id] == "artificial_internal_based_strategy":
                still_to_bid = ssba_optimize_internal_based_strategy(leafy_utility, ic_utility, bundles, bounds, budgets[agent_id], still_to_sell, acquired_goods[agent_id], forthcoming_goods[agent_id])
                rational_bid = ssba_optimize_internal_based_strategy(leafy_utility, ic_utility, bundles, bounds, budgets[agent_id], still_to_sell, acquired_goods[agent_id], forthcoming_goods[agent_id])
                for good in still_to_bid:
                    if rational_bid[good]*.9 <= still_to_bid[good] <= rational_bid[good]*1.1:
                        rationality[agent_id] += 1
                    else:
                        rationality[agent_id] -= 1                
                t = Thread(target=send_bid, args=(agent_ids[agent_id],
                                                competition_id,
                                                still_to_bid))
                t.start()
            else:
                still_to_bid = ssba_stochastic(still_to_sell, budgets[agent_id])
                rational_bid = ssba_optimize_internal_based_strategy(leafy_utility, ic_utility, bundles, bounds, budgets[agent_id], still_to_sell, acquired_goods[agent_id], forthcoming_goods[agent_id])
                for good in still_to_bid:
                    if rational_bid[good]*.9 <= still_to_bid[good] <= rational_bid[good]*1.1:
                        rationality[agent_id] += 1
                    else:
                        rationality[agent_id] -= 1                
                t = Thread(target=send_bid, args=(agent_ids[agent_id],
                                                competition_id,
                                                still_to_bid))
                t.start()               
        return {'response': 'received'}
    if message['message_type'] == 'stop':
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
                compute_utility(trades,  sold_prices, agent_id)
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
                        # data = {
                        #     'final_budget': final_budget,
                        #     'competition_id': competition['competition_id'],
                        #     'agent_id': agent_id,
                        #     'new_allocation': existing_allocation[agent_id],
                        #     'utility': compute_utility(trades, sold_prices, agent_id),
                        #     'rationality': rationality[agent_id],
                        #     'auction_type': auction_type,
                        #     'final': 'False' 
                        # }
                        # print(agent_id, data)
                        # req = urllib.request.Request(
                        #     f'{AUCTION_SERV_URL}/{competition["competition_id"]}',
                        #     headers={'Content-type': 'application/json'},
                        #     data=json.dumps(data).encode('utf-8'),
                        #     method='PATCH'
                        # )        
                        # res = urllib.request.urlopen(req)
                        # msg = res.read().decode('utf-8')
                        # print(msg)  
        else:
            payments = json.loads(message['auction_state'])['joint_payment']
            joint_allocation = json.loads(message['auction_state'])['joint_allocation']
            trades = json.loads(message['auction_state'])['joint_trade']
            sold_prices = json.loads(message['auction_state'])['propositions']['sold_prices']
            compute_utility(trades,  sold_prices, agent_id)
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
            # data = {
            #     'final_budget': final_budget,
            #     'competition_id': competition_id,
            #     'agent_id': agent_id,
            #     'new_allocation': existing_allocation[agent_id],
            #     'utility': compute_utility(trades,  sold_prices, agent_id),
            #     'rationality': rationality[agent_id],
            #     'auction_type': auction_type,
            #     'final': 'True'
            # }
            # print(agent_id, "final", data)
            # req = urllib.request.Request(
            #     f'{AUCTION_SERV_URL}/{competition_id}',
            #     headers={'Content-type': 'application/json'},
            #     data=json.dumps(data).encode('utf-8'),
            #     method='PATCH'
            # )        
            # res = urllib.request.urlopen(req)
            # msg = res.read().decode('utf-8')
            # print(msg)  
        if len(active_competitions) > 1 and auction_type == 'sequential':
            t = Thread(target=update_manager, args=(agent_id, trades, sold_prices, rationality, 'http://localhost:9000/preliminary-results'))
            t.start()
        else:
            t = Thread(target=update_manager, args=(agent_id, trades, sold_prices, rationality, 'http://localhost:9000/final-results'))
            t.start()
        return {'response': 'done'}
    if message['message_type'] == 'abort':
        log('abort message received', agent_id)
        return {'response': 'done'}
    return {'response': 'Unimplemented request'}


@app.route("/<agent_id>/play", methods=["GET", "POST", "PATCH"])
def bidder(agent_id):
    return truthful_bidder(agent_id)

if __name__ == '__main__':
    socketio.run(app, port=BIDDER_PORT)
