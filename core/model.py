
class Bidder:
    """
This class represents a bidder participating to an auction.
    """
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name


class GoodType:
    """
This class represents a good type involved in an auction.
    """
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name


class Auction:
    """
    This class represents a general auction. Must be extended to describe precise auctions.
    """
    def __init__(self, name: str, bidders: list[Bidder], goods: list[GoodType]):
        self.name = name
        self.bidders = bidders
        self.bidder_idx = {bidder.name: idx for idx, bidder in enumerate(bidders)}
        self.goods = goods
        self.good_idx = {good.name: idx for idx, good in enumerate(goods)}
        self.n = len(bidders)
        self.m = len(goods)
        self.trades = [[0 for _ in self.goods] for _ in self.bidders]
        self.payments = [0 for _ in self.bidders]
        self.terminated = False

    def does(self, action):
        """
        Executes the given action for the given bidder.
        Assumes it is legal (should be checked beforehand)!
        Should be defined in subclasses.
        """
        raise NotImplementedError

    def is_legal(self, action):
        """
        Evaluates whether the given action is legal or not.
        Should be defined in subclasses.
        """
        raise NotImplementedError

    def next(self):
        """
        Computes the next state.
        Should be defined in subclasses.
        """
        raise NotImplementedError

    def is_terminated(self):
        """
        Returns True if and only if the auction is in its terminal state.
        """
        return self.terminated

    def payment(self, bidder):
        """
        Returns the total price that the bidder has to pay.
        """
        return self.payments[self.get_bidder_idx(bidder)]

    def state(self):
        """
        Returns a JSON representation of the auction state.
        Useful for the auction server.
        """
        raise NotImplementedError

    def pretty(self):
        """
        Returns a string displaying detailed information about the current
        state of this auction.
        Should be defined in subclasses.
        """
        raise NotImplementedError

    def get_bidder_idx(self, bidder):
        """
        Gets the agent index given the agent id.
        """
        bidder = bidder.name if type(bidder) == Bidder else bidder
        return self.bidder_idx[bidder]

    def get_good_idx(self, good):
        """
        Gets the good index given the good id. (This is a good id...)
        """
        good = good.name if type(good) == GoodType else good
        return self.good_idx[good]