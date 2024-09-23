import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core.model import Auction, Bidder, GoodType

class SAAuction(Auction):
    """
This class represents the simultaneous ascending auction mechanism. This
mechanism is similar to the traditional English auction, except that
several items are sold simultaneously.
    """
    def __init__(self, bidders: list[Bidder], goods: list[GoodType], start_price, increment):
        super().__init__("Simultaneous Ascending Auction", bidders, goods)
        self.increment = increment
        self.price = start_price
        self.start_price = start_price
        self.sold_prices = [None for _ in self.goods]
        self.bids = [set() for _ in self.goods]
        self.sold = [False for _ in self.goods]

    def does(self, bidder, action):
        """
        Executes the given action for the given bidder.
        Here, we consider that an action is simply a good or a list of goods,
        indicating that the given bidder bids for the given good(s).
        (Slightly different from the JAAMAS'22 paper).
        This is legal if and only if this good has not been sold yet
        (see `is_legal`) and it simply adds this bid to the bid list.
        """
        if action != 'noop':
            bidder = self.get_bidder_idx(bidder)
            goods = action
            if type(goods) != list:
                goods = [goods]
            goods = [self.get_good_idx(good) for good in goods]
            for good in goods:
                self.bids[good].add(bidder)

    def is_legal(self, action):
        """
        Evaluates whether the given action is legal or not.
        Here, we consider that an action is a pair (bidder, good)
        or (bidder, list of goods)
        indicating that the given bidder bids for the given goods.
        (Slightly different from the JAAMAS'22 paper).
        This is legal if and only if this good has not been sold yet.
        """
        bidder, goods = action
        bidder = self.get_bidder_idx(bidder)
        if type(goods) != list:
            goods = [goods]
        goods = [self.get_good_idx(good) for good in goods]
        return bidder >= 0 and bidder < len(self.bidders) \
            and all(good >= 0 and good < len(self.goods) for good in goods) \
            and not self.is_terminated() \
            and all(not self.sold[good] for good in goods)

    def next(self):
        """
        Computes the next state.
        """
        if self.terminated:
            return
        self.terminated = True
        for j in range(self.m):
            if not self.sold[j]:
                if len(self.bids[j]) > 0:
                    self.terminated = False
                if len(self.bids[j]) == 1:
                    winner = next(iter(self.bids[j]))
                    self.trades[winner][j] = 1
                    self.sold[j] = True
                    self.sold_prices[j] = self.price
                    self.payments[winner] += self.price
                self.bids[j] = set()
        self.terminated = self.terminated or all(self.sold)
        self.price += self.increment

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
            "price": self.price,
            "start_price": self.start_price,
            "increment": self.increment,
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
        string += f'Current price is {self.price}, '
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
                + ', '.join(str(self.bidders[bidder]) for bidder in self.bids[j]) + '}'
                for j, good in enumerate(self.goods)
                if not self.sold[j])
        return string

    def __str__(self):
        return f'{self.name} <[{", ".join(str(bidder) for bidder in self.bidders)}], ' + \
            f'[{", ".join(str(good) for good in self.goods)}], ' + \
            f'{self.start_price}, {self.increment}>'
