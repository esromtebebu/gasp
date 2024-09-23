#!/usr/bin/python3

import os
import sys
import urllib.request

AUCTION_SERV_URL = "http://localhost:5000"

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.stderr.write(f'Usage: {sys.argv[1]} <file name>\n')
        sys.exit(1)
    auction_filename = sys.argv[1]
    with open(auction_filename, 'r') as auction_file:
        auction_desc = auction_file.read()
        
        req = urllib.request.Request(
            f'{AUCTION_SERV_URL}/competitions',
            headers={'Content-type': 'application/json'},
            data=auction_desc.encode('utf-8')
        )
        try:
            res = urllib.request.urlopen(req)
            htmldoc = res.read().decode('utf-8')
            print(htmldoc)
        except:
            sys.stderr.write(f'Connection refused at URL {AUCTION_SERV_URL}/competitions.\nIs the server running and accepting connections?\n')
