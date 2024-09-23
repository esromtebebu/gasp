import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core.model import Auction, Bidder, GoodType

class SSBAuction2(Auction):
    '''
    This class represents the simultaneous sealed bid auction mechanism with second-price payment.
    This mechanism is similar to the traditional sealed bid auction, except that
    several items are sold simultaneously.
    '''
    def __init__(self, bidders: list[Bidder], goods: list[GoodType]):
        super().__init__("Simultaneous Sealed Bid Auction with Second Price Payment", bidders, goods)
        self.sold_prices = [None for _ in self.goods]
        self.bids = [set() for _ in self.goods]
        self.sold = [False for _ in self.goods]
    
    def does(self, bidder, action):
        '''
        Executes the given action for the given bidder.
        Here, we consider that an action is simply a tuple of a good (or a list of goods) and a price (or a list of prices),
        indicating that the given bidder bids for the given good(s) with a price for each.
        In this case, the action is always legal since it is an one-shot auction (cf. `is_legal`),
        and it simply adds this bid to the bid list.
        '''
        if action != 'noop':
            bidder = self.get_bidder_idx(bidder)
            goods = list(action.keys())
            offer_prices = list(action.values())
            if type(goods) != list:
                goods = [goods]
            if type(offer_prices) != list:
                offer_prices = [offer_prices]
            goods = [self.get_good_idx(good) for good in goods]
            for good in goods:
                self.bids[good].add((bidder, offer_prices[goods.index(good)]))
    
    def is_legal(self, action):
        '''
        Evaluates whether the given action is legal or not.
        Here, we consider that an action is a triple (bidder, good, price)
        or (bidder, list of goods, list of prices for each good)
        indicating that the given bidder bids for the given goods.
        This action is always in a one-shot auction.
        '''
        bidder, offer = action
        bidder = self.get_bidder_idx(bidder)
        goods = list(offer.keys())
        offer_prices = list(offer.values())
        if type(goods) != list:
                goods = [goods]
        if type(offer_prices) != list:
            offer_prices = [offer_prices]
        goods = [self.get_good_idx(good) for good in goods]
        return bidder >= 0 and bidder < len(self.bidders) \
            and all(good >= 0 and good < len(self.goods) for good in goods) \
            and not self.is_terminated() \
            and all(not self.sold[good] for good in goods)
    
    def next(self):
        '''
        Computes the next--and final--state.
        '''
        if self.terminated:
            return
        self.terminated = True
        for j in range(self.m):
            if self.bids[j] and max(self.bids[j], key = lambda x: x[1])[1] > 0:
                winner = max(self.bids[j], key = lambda x: x[1])[0]
                self.trades[winner][j] = 1
                self.sold[j] = True
                if len(self.bids[j]) < 2:
                    self.sold_prices[j] = max(self.bids[j], key = lambda x: x[1])[1]
                    self.payments[winner] += max(self.bids[j], key = lambda x: x[1])[1]
                else:
                    highest_price = max(self.bids[j], key=lambda x: x[1])[1]
                    second_highest_price = max([x for x in self.bids[j] if x[1] != highest_price], key=lambda x: x[1])[1]
                    if second_highest_price > 0:
                        self.sold_prices[j] = second_highest_price
                        self.payments[winner] += self.sold_prices[j]
                    else:
                        self.sold_prices[j] = max(self.bids[j], key = lambda x: x[1])[1]
                        self.payments[winner] += max(self.bids[j], key = lambda x: x[1])[1]
        self.bids[j] = set()
        self.terminated = True
    
    def state(self):
        """
        Returns a JSON representation of the auction state.
        Useful for the auction server.
        """
        auction_state = {}
        auction_state["joint_trade"] = {
            str(bidder): {
                str(good): self.trades[i][j]
                for j, good in enumerate(self.goods)
                if self.trades[i][j]
            }
            for i, bidder in enumerate(self.bidders)
            }
        auction_state["joint_allocation"] = auction_state["joint_trade"]
        auction_state["joint_payment"] = {
            str(bidder): self.payments[j]
            for j, bidder in enumerate(self.bidders)
            if self.payments[j]
            }
        auction_state["propositions"] = {
            "terminated": self.terminated,
            "sold_prices": self.sold_prices,
            "sold": self.sold
            }
        return auction_state
    
    def pretty(self):
        """
        Returns a string displaying detailed information about the current
        state of this auction.
        """
        string = str(self) + '\n'
        string += 'Auction is ' + ('still running'
                                   if not self.is_terminated()
                                   else 'terminated') + '\n'
        string += '\n'.join(
            str(bidder) + ' bought {'
            + ', '.join(str(good) + f' (€{self.sold_prices[j]})'
                        for j, good in enumerate(self.goods) if self.trades[i][j]) + '}'
            + f' for €{self.payments[i]}'
            for i, bidder in enumerate(self.bidders)
            ) + '\n'
        string += 'Unsold goods: {' + \
            ', '.join(str(good) for j, good in enumerate(self.goods) if not self.sold[j]) + \
            '}'
        if not self.is_terminated():
            string += '\nCurrent bids:\n'
            string += '\n'.join(
                str(good) + ' → {'
                + ', '.join(str(self.bidders[bidder[0]]) for bidder in self.bids[j]) + '}'
                for j, good in enumerate(self.goods)
                if not self.sold[j])
        return string

    def __str__(self):
        return f'{self.name} <[{", ".join(str(bidder) for bidder in self.bidders)}], ' + \
            f'[{", ".join(str(good) for good in self.goods)}], '