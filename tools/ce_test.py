#!/usr/bin/env python3

import json
import os
import os.path
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import urllib.request
from core.model import GoodType, Bidder
from core.ce import Bid, CombinatorialExchange

AUCTION_SERV_URL = "http://localhost:5000"

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.stderr.write(f'Usage: {sys.argv[0]} <file name>\n')
        sys.exit(1)
    auction_filename = sys.argv[1]
    with open(auction_filename, 'r') as auction_file:
        auction_desc = json.loads(auction_file.read())
        
        valuations = {
            agent['id']: agent['valuation']
            for agent in auction_desc['agents']
        }

        goods = [GoodType(good) for good in auction_desc["goods"]]
        bidders = [Bidder(agent['id']) for agent in auction_desc['agents']]
        allocation = [[0] * len(goods) for _ in bidders]
        for i, agent in enumerate(auction_desc['agents']):
            for j, good in enumerate(goods):
                if good.name in agent['allocation']:
                    allocation[i][j] = agent['allocation'][good.name]


        auction = CombinatorialExchange(bidders, goods, allocation)
        good_dict = {
            good.name: good
            for good in goods
        }
        for bidder in bidders:
            auction.does(bidder, Bid.from_dict(valuations[bidder.name], good_dict))

        print(auction.pretty())

        auction.next()

        print(auction.pretty())
