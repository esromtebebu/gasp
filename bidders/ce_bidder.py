#!/usr/bin/env python

import json
from flask import Flask, request
from threading import Thread
import time
import urllib.request
from multiprocessing import Lock
import sys

AUCTION_SERV_URL = "http://localhost:5000"
BIDDER_PORT = 38400

app = Flask(__name__)

valuations = []
agent_ids = []
competition_id = None
goods = None
lock = Lock()


def log(msg, bidder_number):
    with lock:
        sys.stdout.write(f'Bidder {bidder_number + 1} > {msg}\n')


def send_bid(bidder_number, valuation, agent_id, competition_id):
    msg = {
        "message_type": "bid",
        "competition_id": competition_id,
        "agent_id": agent_id,
        "bid": valuation
    }
    time.sleep(5)
    log(f'Submitting bid {valuation}', bidder_number)
    req = urllib.request.Request(f'{AUCTION_SERV_URL}/{competition_id}/{agent_id}/bid',
                                 headers={'Content-type': 'application/json'},
                                 data=json.dumps(msg).encode('utf-8'))
    res = urllib.request.urlopen(req)
    htmldoc = res.read().decode('utf-8')
    log(f'Response received: {htmldoc}', bidder_number)


def truthful_bidder(bidder_number):
    global valuations, competition_id, goods
    message = json.loads(request.data.decode("utf-8"))
    if message['message_type'] == 'start':
        log('start message received', bidder_number)
        valuations.insert(bidder_number, json.loads(message['valuation']))
        agent_ids.insert(bidder_number, message['agent_id'])
        competition_id = message['competition_id']
        goods = message['goods']
        return {'response': 'ready'}
    if message['message_type'] == 'bid_request':
        log('bid request message received', bidder_number)
        auction_state = json.loads(message['auction_state'])['propositions']
        t = Thread(target=send_bid, args=(bidder_number,
                                          valuations[bidder_number],
                                          agent_ids[bidder_number], competition_id))
        t.start()
        return {'response': 'received'}
    if message['message_type'] == 'stop':
        log('stop message received', bidder_number)
        log('{\n\t'
            + '\n\t'.join(f'{key}: {value}' for key, value in message.items())
            + '\n}', bidder_number)
        return {'response': 'done'}
    if message['message_type'] == 'abort':
        log('abort message received', bidder_number)
        return {'response': 'done'}
    return {'response': 'Unimplemented request'}


@app.route("/bidder<bidder_number>", methods=["GET", "POST"])
def bidder(bidder_number):
    return truthful_bidder(int(bidder_number) - 1)


if __name__ == '__main__':
    app.run(port=BIDDER_PORT)
