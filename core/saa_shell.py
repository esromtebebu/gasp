#!/usr/bin/env python3

import cmd
try:
    from model import Bidder, GoodType
    from saa import SAAuction
except ImportError:
    from core.model import Bidder, GoodType
    from core.saa import SAAuction


class IncorrectNumberOfArgumentsException(Exception):
    def __init__(self, msg):
        super().__init__(msg)


class SAAShell(cmd.Cmd):
    intro = 'Welcome to the SAA shell.   Type help or ? to list commands.\n'
    prompt = '(SAA) '
    instance = None

    def _does_not_exit_on_exception(init_fn):
        def _wrapped(*args, **kwargs):
            try:
                return init_fn(*args, **kwargs)
            except Exception as e:
                print(e)
        return _wrapped

    def _with_auction_defined(init_fn):
        def _wrapped(self, *args, **kwargs):
            if self.instance is None:
                print('No auction defined currently')
            else:
                return init_fn(self, *args, **kwargs)
        return _wrapped

    @_does_not_exit_on_exception
    def do_new(self, arg):
        'Creates a new SA Auction by specifying. Syntax: NEW n m start_price increment'
        n, m, start_price, increment = parse(arg, 4)
        self.instance = SAAuction([Bidder(f'agent {i+1}') for i in range(n)],
                                  [GoodType(f'good {i+1}') for i in range(m)],
                                  start_price,
                                  increment)

    @_does_not_exit_on_exception
    @_with_auction_defined
    def do_next(self, arg):
        'Computes the next state of the auction. Syntax: NEXT'
        self.instance.next()
        print('Next state')

    @_does_not_exit_on_exception
    @_with_auction_defined
    def do_bid(self, arg):
        'Sends a bid. Syntax: BID bidder good'
        bidder, good = parse(arg, 2)
        bidder = self.instance.bidders[bidder]
        good = self.instance.goods[good]
        if not self.instance.is_legal((bidder.name, good.name)):
            print('This bid is illegal. The bidder does not exist, the good does not exist, '
                  + 'the good has already been sold or the auction is terminated!')
        else:
            self.instance.does(bidder.name, good.name)
            print('Bid accepted')

    @_does_not_exit_on_exception
    @_with_auction_defined
    def do_show(self, arg):
        'Shows the current auction state.'
        if self.instance is None:
            print('No auction defined currently')
        else:
            print(self.instance.pretty())

    @_does_not_exit_on_exception
    @_with_auction_defined
    def do_state(self, arg):
        'Shows the current auction state in JSON format.'
        if self.instance is None:
            print('No auction defined currently')
        else:
            print(str(self.instance.state()))

    def do_bye(self, arg):
        'Close this shell and exit'
        print('Bye bye')
        return True

    def do_EOF(self, arg):
        'Close this shell and exit'
        return self.do_bye(arg)


def parse(arg, nb_exp):
    'Convert a series of zero or more numbers to an argument tuple'
    parsed_args = tuple(map(int, arg.split()))
    if len(parsed_args) != nb_exp:
        raise IncorrectNumberOfArgumentsException(
            f'Incorrect number of arguments ({nb_exp} expected)')
    return parsed_args


if __name__ == '__main__':
    SAAShell().cmdloop()
