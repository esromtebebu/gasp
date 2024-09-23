from typing import Dict, List, Tuple
import pulp
from typing import TypeVar, Type

import os
import os.path
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from core.model import Auction, GoodType, Bidder

# The following type variable is intended to give a type
# annotation to a class method of Bid
T = TypeVar('T', bound='Bid')

class Bid:
    def __init__(self, value) -> None:
        self.sat = pulp.LpVariable(f'sat_{Bid.var_number}', 0, 1, pulp.LpInteger)
        Bid.var_number += 1
        self.value = value

    def as_dict(self) -> Dict:
        """
        Returns a JSON representation of the bid tree.
        Useful for the auction server.
        """        
        raise NotImplementedError

    def has_valid_goods(self, goods: List[GoodType]) -> bool:
        """
        Returns True if and only if the bid tree only contains
        goods from the good list in parameter.
        """
        raise NotImplementedError

    def __str__(self, prefix: str = None) -> str:
        raise NotImplementedError
    
    def collect_node_variables(self,
                               d: Dict[GoodType, Tuple[List[pulp.pulp.LpVariable], List[int]]]) -> None:
        raise NotImplementedError
    
    def collect_ic_constraints(self) -> List:
        raise NotImplementedError
    
    def collect_node_variables_and_values(self,
                                          l: List[Tuple[pulp.pulp.LpVariable, int]]) -> None:
        l.append((self.sat, self.value))

    @classmethod
    def from_dict(cls: Type[T], d: Dict, goods: Dict) -> T:
        if d["node"] == "leaf":
            return Leaf(d["units"], goods[d["good"]], d["value"])
        elif d["node"] == "ic":
            return IntervalChoose(d["min"], d["max"], d["value"],
                                  [Bid.from_dict(child_dict, goods)
                                   for child_dict in d["child_nodes"]])
        else:
            raise Exception(f"Unknown node type {d['node']}")
    
    var_number = 1

    def is_seller(self) -> bool:
        raise NotImplementedError

    def is_buyer(self) -> bool:
        raise NotImplementedError


class Leaf(Bid):
    """
This class represents a leaf of the bid tree expressed in TBBL.
    """
    def __init__(self, quantity: int, good: GoodType, value: int) -> None:
        super().__init__(value)
        self.quantity = quantity
        self.good = good
    
    def as_dict(self) -> Dict:
        return {
            "node": "leaf",
            "value": self.value,
            "units": self.quantity,
            "good": self.good
        }
    
    def has_valid_goods(self, goods: List[GoodType]) -> bool:
        return self.good in goods
    
    def __str__(self, prefix: str = None) -> str:
        if prefix is None:
            prefix = ""
        return (
            prefix +
            ("Sell " if self.value < 0 else "Buy ") +
            f"{abs(self.quantity)} unit(s) of {self.good} for € {abs(self.value)}"
        )        

    def collect_node_variables(self,
                               d: Dict[GoodType, Tuple[List[pulp.pulp.LpVariable], List[int]]]) -> None:
        if self.good not in d:
            d[self.good] = ([], [])
        vars, quantities = d[self.good]
        vars.append(self.sat)
        quantities.append(self.quantity)
    
    def collect_ic_constraints(self) -> List:
        return []

    def is_seller(self) -> bool:
        return self.quantity < 0

    def is_buyer(self) -> bool:
        return self.quantity > 0
        


class IntervalChoose(Bid):
    """
This class represents an internal node of the bid tree expressed in TBBL.
    """
    def __init__(self, lower_bound: int, upper_bound: int, value: int, bids: List[Bid] = None) -> None:
        super().__init__(value)
        self.bids = [] if bids is None else [bid for bid in bids]
        self.lb = lower_bound
        self.ub = upper_bound
    
    def add_bid(self, bid: Bid) -> None:
        "Adds a bid to the bid list."
        self.bids.append(bid)

    def as_dict(self) -> Dict:
        return {
            "node": "ic",
            "value": self.value,
            "min": self.lb,
            "max": self.ub,
            "child_nodes": [node.as_dict for node in self.bids]
        }
    
    def has_valid_goods(self, goods: List[GoodType]) -> bool:
        return all(node.has_valid_goods(goods) for node in self.bids)
    
    def __str__(self, prefix: str = None) -> str:
        if prefix is None:
            prefix = ""
        return (
            prefix +
            f'[+] btw {self.lb} and {self.ub} for € {abs(self.value)}\n' +
            '\n'.join(node.__str__(f'{prefix} |-- ') for node in self.bids)
        )

    def collect_node_variables(self,
                               d: Dict[GoodType, Tuple[List[pulp.pulp.LpVariable], List[int]]]) -> None:
        for bid in self.bids:
            bid.collect_node_variables(d)
    
    def collect_node_variables_and_values(self,
                                          l: List[Tuple[pulp.pulp.LpVariable, int]]) -> None:
        super().collect_node_variables_and_values(l)
        for bid in self.bids:
            bid.collect_node_variables_and_values(l)

    def collect_ic_constraints(self) -> List:
        constraints = []
        child_vars = [node.sat for node in self.bids]
        constraints.append(pulp.lpSum(child_vars) <= self.ub * self.sat)
        constraints.append(pulp.lpSum(child_vars) >= self.lb * self.sat)
        for node in self.bids:
            constraints += node.collect_ic_constraints()
        return constraints

    def is_seller(self) -> bool:
        return all((bid.is_seller() for bid in self.bids))

    def is_buyer(self) -> bool:
        return all((bid.is_buyer() for bid in self.bids))


    @staticmethod
    def XOR(value: int, bids: List[Bid]) -> Bid:
        ic = IntervalChoose(1, 1, value, bids)
    
    @staticmethod
    def OR(value: int, bids: List[Bid]) -> Bid:
        ic = IntervalChoose(1, len(bids), value, bids)
    
    @staticmethod
    def AND(value: int, bids: List[Bid]) -> Bid:
        ic = IntervalChoose(len(bids), len(bids), value, bids)
    


class CombinatorialExchange(Auction):
    """
This class represents the combinatorial exchange mechanism. In this
mechanism, The bidders initially hold goods and bid for exchanges
using the TBBL language. A winner determination optimization program
is run to determine which exchanges are made. This auction is a one-step auction.
    """
    def __init__(self, bidders: List[Bidder], goods: List[GoodType],
                 allocation: List[List[int]],
                 config: Dict={'SOLVER': 'GLPK'}) -> None:
        """
        Creates an auction. Here, allocation is the initial amount of each
        good that each bidder owns.
        """
        super().__init__("Combinatorial Exchange", bidders, goods)
        self.bids = [None for _ in self.bidders]
        self.trades = [[0 for _ in self.goods] for _ in self.bidders]
        self.payments = [0 for _ in self.bidders]
        self.allocation = allocation
        self.initial_allocation = allocation
        self.terminated = False
        self.config = config

    def does(self, bidder: Bidder, action: Bid) -> None:
        """
        Executes the given action for the given bidder.
        Here, an action is a bid expressed in TBBL (or 'noop').
        It is legal as long as it is a valid bid tree and all the goods
        it refers to are goods of the current auction.
        """
        if action != 'noop':
            bidder = self.get_bidder_idx(bidder)
            if type(action) == Dict:
                action = Bid.from_dict(action, {good.name: good for good in self.goods})
            self.bids[bidder] = action

    def is_legal(self, action: Tuple[Bidder, Bid]) -> bool:
        """
        Evaluates whether the given action is legal or not.
        Here, an action is a bid expressed in TBBL (or 'noop').
        It is legal as long as it is a valid bid tree and all the goods
        it refers to are goods of the current auction.       
        """
        bidder, bid = action
        if bid == 'noop':
            return True
        if type(bid) == Dict:
            bid = Bid.from_dict(bid, {good.name: good for good in self.goods})
        return bid.has_valid_goods(self.goods)
        

    def next(self) -> None:
        """
        Computes the next state. Here, the Winner Determination problem described on page 27 of the JAAMAS'21
        paper by Mittelman et al. is used.
        """
        prob = pulp.LpProblem("Winner_Determination", pulp.LpMaximize)
        obj = pulp.LpVariable("obj", 0, None, pulp.LpContinuous)
        prob += obj
        # We build the set of trade variables
        trade = [
            pulp.LpVariable.dicts(f"lambda_{i}", range(self.m), None, None, pulp.LpInteger)
            for i in range(self.n)
        ]

        # No agent sells more items than she initially holds (C1)
        for i in range(self.n):
            for j in range(self.m):
                prob += (trade[i][j] + self.initial_allocation[i][j] >= 0)
        # Free disposal is allowed but not to create goods from scratch (C2)
        for j, _ in enumerate(self.goods):
                prob += (pulp.lpSum([trade[i][j] for i in range(self.n)]) <= 0)

        # We add the constraints related to the satisfaction of the bid tree (C3)
        for i, bid in enumerate(self.bids):
            if bid is not None:
                # First, the R1 constraints for any ic node
                for constraint in bid.collect_ic_constraints():
                    prob += constraint
                # Second, the R2 constraints for any leaf node
                node_variables = {
                    good: ([], [])
                    for good in self.goods
                }
                bid.collect_node_variables(node_variables)                
                for j, good in enumerate(self.goods):
                    tab = [sat * q for sat, q in zip(*node_variables[good])]
                    if tab:
                        prob += (pulp.lpSum(tab) <= trade[i][j])
                    else:
                        prob += (0 <= trade[i][j])
                        # This contraint ensures that an agent only sells goods
                        # if they appear as goods to sell in the bid tree

        # Constraint C4 is implicit

        # Individual utilities
        u = pulp.LpVariable.dicts("u", range(self.n), None, None, pulp.LpContinuous)
        for i, bid in enumerate(self.bids):
            if bid is not None:
                l = []
                bid.collect_node_variables_and_values(l)
                prob += (pulp.lpSum([sat * value for sat, value in l]) == u[i])
        
        # Objective variable + constraint
        prob += (pulp.lpSum(u) == obj)
        if self.config['SOLVER'] == 'CPLEX':
            solver = pulp.CPLEX(path=self.config['CPLEX_PATH'], msg=1, keepFiles=1)
        else:
            solver = pulp.GLPK(msg=False)
        prob.solve(solver)
        # print(prob)
        # for var in prob.variables():
        #     d = var.toDict()
        #     print(d)
        assert prob.status == pulp.LpStatusOptimal,\
            "The solver was not able to solve the WDP problem optimally..."
        self.trades = [[trade[i][j].varValue for j in range(self.m)] for i in range(self.n)]
        self.allocation = [[self.allocation[i][j] + self.trades[i][j] for j in range(self.m)]
                           for i in range(self.n)]
        self.bids = [None for _ in self.bidders]
        self.payments = [u[i].varValue for i in range(len(self.bidders))]
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
        auction_state["joint_allocation"] = {
            str(bidder): {
                str(good): self.allocation[i][j]
                for j, good in enumerate(self.goods)
                if self.allocation[i][j]
            }
            for i, bidder in enumerate(self.bidders)
            }
        auction_state["joint_payment"] = {
            str(bidder): self.payments[j]
            for j, bidder in enumerate(self.bidders)
            if self.payments[j]
            }
        auction_state["propositions"] = {
            "terminated": self.terminated
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
        string += 'Current bids:\n'
        string += '\n'.join(
            str(bidder) + ':\n' +
            self.bids[i].__str__()
            for i, bidder in enumerate(self.bidders)
            ) + '\n'
        if self.is_terminated():            
            string += 'Current allocation:\n'
            string += '\n'.join(
                str(bidder) + ' → {' + ', '.join(f'{good} × [{self.initial_allocation[i][j]} + {self.trades[i][j]} → {self.allocation[i][j]}]' for j, good in enumerate(self.goods)) + '}'
                for i, bidder in enumerate(self.bidders)
            ) + '\n'
            string += 'Payments:\n'
            string += '\n'.join(str(bidder) + (' pays ' if self.payments[i] > 0 else ' receives ') + f'€ {abs(self.payments[i])}'
                                for i, bidder in enumerate(self.bidders))
        else:
            string += 'Current (initial) allocation:\n'
            string += '\n'.join(
                str(bidder) + ' → {' + ', '.join(f'{good} × {self.initial_allocation[i][j]}' for j, good in enumerate(self.goods)) + '}'
                for i, bidder in enumerate(self.bidders)
            ) + '\n'

        return string

    def __str__(self):
        return f'{self.name} <[{", ".join(str(bidder) for bidder in self.bidders)}], ' + \
            f'[{", ".join(str(good) for good in self.goods)}]>'
