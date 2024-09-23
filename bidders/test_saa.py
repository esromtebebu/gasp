#!/usr/bin/env python

import json
from flask import Flask, request
import logging
import random
from threading import Thread
import time
import urllib.request
from multiprocessing import Lock

LOGGING_LEVEL = logging.INFO
NB_TESTS = 10

AUCTION_SERV_URL = "http://localhost:5000"
BIDDER_PORT = 38400
SEED = None
RANGE_NB_BIDDERS = (2, 5)  # bounds included
RANGE_NB_GOODS = (3, 15)  # bounds included
RANGE_SLEEP = (1, 3)
MAX_VALUE = 50

app = Flask(__name__)


valuations = None
agent_ids = None
competition_id = None
goods = None
stop_messages_received = 0
final_auction = None
lock = Lock()
seed = None


def log(msg, bidder_number=None, level=logging.INFO):
    with lock:
        if bidder_number:
            logging.getLogger(__name__).log(level, f'Bidder {bidder_number + 1} > {msg}')
        else:
            logging.getLogger(__name__).log(level, f'{msg}')


def send_bid(bidder_number, valuation, agent_id, competition_id, current_price, sold):
    still_to_sell = {good for idx, good in enumerate(goods) if not sold[idx]}
    still_to_bid = [
        cn['good']
        for cn in valuation['child_nodes']
        if (cn['value'] >= current_price and cn['good'] in still_to_sell)
    ]
    msg = {
        "message_type": "bid",
        "competition_id": competition_id,
        "agent_id": agent_id,
        "bid": still_to_bid
    }
    time.sleep(random.randint(*RANGE_SLEEP))
    log(f'Submitting bid {still_to_bid} − current price : € {current_price}', bidder_number,
        logging.DEBUG)
    req = urllib.request.Request(f'{AUCTION_SERV_URL}/{competition_id}/{agent_id}/bid',
                                 headers={'Content-type': 'application/json'},
                                 data=json.dumps(msg).encode('utf-8'))
    res = urllib.request.urlopen(req)
    htmldoc = res.read().decode('utf-8')
    log(f'Response received: {htmldoc}', bidder_number, logging.DEBUG)


def truthful_bidder(bidder_number):
    global valuations, competition_id, goods
    message = json.loads(request.data.decode("utf-8"))
    if message['message_type'] == 'start':
        log('start message received', bidder_number, logging.DEBUG)
        valuations[bidder_number] = json.loads(message['valuation'])
        agent_ids[bidder_number] = message['agent_id']
        competition_id = message['competition_id']
        goods = message['goods']
        return {'response': 'ready'}
    if message['message_type'] == 'bid_request':
        log('bid request message received', bidder_number, logging.DEBUG)
        auction_state = json.loads(message['auction_state'])['propositions']
        t = Thread(target=send_bid, args=(bidder_number,
                                          valuations[bidder_number],
                                          agent_ids[bidder_number], competition_id,
                                          auction_state['price'],
                                          auction_state['sold']))
        t.start()
        return {'response': 'received'}
    if message['message_type'] == 'stop':
        log('stop message received', bidder_number, logging.DEBUG)
        log('{\n\t'
            + '\n\t'.join(f'{key}: {value}' for key, value in message.items())
            + '\n}', bidder_number, logging.DEBUG)
        global final_auction, stop_messages_received
        final_auction = json.loads(message['auction_state'])
        stop_messages_received += 1
        return {'response': 'done'}
    if message['message_type'] == 'abort':
        log('abort message received', bidder_number, logging.DEBUG)
        return {'response': 'done'}
    return {'response': 'Unimplemented request'}


@app.route("/bidder<bidder_number>", methods=["GET", "POST"])
def bidder(bidder_number):
    return truthful_bidder(int(bidder_number) - 1)


def create_competition(nb_bidders, nb_goods, max_value, start_price, increment, seed):
    random.seed(time.time())
    auction = {
        "competition_id": f"random_competition_{random.randint(1, 10000000)}",
        "title": "lorem ipsum",
        "description": "lorem ipsum",
        "starts": "2021-10-25T18:25:43.511Z",
        "response_clock": 10,
        "bid_clock": 10,
        "mechanism": "SAA",
        "start_price": start_price,
        "increment": increment,
        "goods": [f"Good{nb + 1}" for nb in range(nb_goods)],
        "agents": []
    }
    random.seed(seed)
    values = [
        [random.randint(0, max_value) for _ in range(nb_goods)]
        for _ in range(nb_bidders)
    ]
    for nb in range(nb_bidders):
        current_agent = {
            "id": f"agent{nb + 1}",
            "url": f"http://localhost:{BIDDER_PORT}/bidder{nb + 1}",
            "valuation": {
                "node": "ic",
                "value": 0,
                "min": 0,
                "max": 4,
                "child_nodes": [
                    {
                        "node": "leaf",
                        "value": values[nb][good_idx],
                        "units": 1,
                        "good": good
                    }
                    for good_idx, good in enumerate(auction['goods'])
                    ]
            },
            "allocation": {
                good: 0
                for good in auction['goods']
            },
            "budget": max_value * (max_value + 1)  # enough budget to buy everything
        }
        auction["agents"].append(current_agent)

    req = urllib.request.Request(f'{AUCTION_SERV_URL}/competitions',
                                 headers={'Content-type': 'application/json'},
                                 data=json.dumps(auction).encode('utf-8'))
    res = urllib.request.urlopen(req)
    received = json.loads(res.read().decode('utf-8'))
    if 'message' not in received and received['message'] != 'Competition created':
        raise Exception('Error during competition creation! Message received from server:'
                        + f'\n{received}')
    global valuations, agent_ids
    valuations = [None] * nb_goods
    agent_ids = [None] * nb_bidders
    return auction, values, received['url']


def predict_winners(auction, values):
    global sold_prices, winners
    last_prices = [
        [auction["increment"] * ((value - auction["start_price"]) // auction["increment"])
         + auction["start_price"]
         for value in row]
        for row in values
    ]
    nb_goods = len(values[0])
    nb_bidders = len(values)
    first_prices = [0] * nb_goods
    second_prices = [0] * nb_goods
    winners = [None] * nb_goods
    for good in range(nb_goods):
        for bidder in range(nb_bidders):
            if last_prices[bidder][good] >= first_prices[good]:
                second_prices[good] = first_prices[good]
                first_prices[good] = last_prices[bidder][good]
                winners[good] = bidder
            elif last_prices[bidder][good] > second_prices[good]:
                second_prices[good] = last_prices[bidder][good]
    sold_prices = [
        0 if first_prices[good] == second_prices[good]
        else second_prices[good] + auction["increment"]
        for good in range(nb_goods)]


def check_result(auction_state):
    global sold_prices, winners, goods
    consistent = True
    for idx, good in enumerate(goods):
        if sold_prices[idx] != (0 if not auction_state['propositions']['sold_prices'][idx] else
                                auction_state['propositions']['sold_prices'][idx]):
            consistent = False
            log(f'>>> Inconsistent sold price for good {good}: '
                + f'{auction_state["propositions"]["sold_prices"][idx]} '
                + f'(expected {sold_prices[idx]})', logging.ERROR)
    return consistent


def run_tests():
    global agent_ids, stop_messages_received, final_auction
    time.sleep(2)  # Wait for 2 seconds (so that the bidder server has time to start)
    for test_nb in range(1, NB_TESTS + 1):
        log(f"Starting test {test_nb} / {NB_TESTS}", None, logging.INFO)
        run_test()
        nb_bidders = len(agent_ids)
        while stop_messages_received < nb_bidders:
            time.sleep(2)
        if check_result(final_auction):
            log("Test succeeded", None, logging.INFO)


def run_test():
    url = prepare_auction()
    global stop_messages_received, final_auction
    stop_messages_received = 0
    final_auction = None
    send_start(url)


def prepare_auction():
    global seed
    seed = time.time() if SEED is None else SEED
    random.seed(seed)
    nb_bidders = random.randint(*RANGE_NB_BIDDERS)
    nb_goods = random.randint(*RANGE_NB_GOODS)
    auction, values, url = create_competition(nb_bidders, nb_goods, MAX_VALUE, 5, 5, seed)
    log(f"Competition created! URL : {url}", None, logging.DEBUG)
    global sold_prices
    log(f"Bidder values : {values}", None, logging.DEBUG)
    predict_winners(auction, values)
    log(f"Sold prices : {sold_prices}", None, logging.DEBUG)
    return url


def send_start(url):
    log("Sending Start", None, logging.DEBUG)
    req = urllib.request.Request(f'{url}/start')
    res = urllib.request.urlopen(req)
    received = json.loads(res.read().decode('utf-8'))
    if 'message' not in received or received['message'] != 'Competition started':
        raise Exception(f'Bad start message received: {received}')


if __name__ == '__main__':
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    logging.getLogger(__name__).setLevel(LOGGING_LEVEL)
    logging.getLogger(__name__).addHandler(logging.StreamHandler())
    t = Thread(target=run_tests)
    t.start()
    app.run(port=BIDDER_PORT, use_reloader=False)
