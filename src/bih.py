from __future__ import annotations
from typing import Callable, List
from src.vrptw_core import Instance, best_feasible_insertion, evaluate_solution, is_better, remove_empty_routes, route_schedule


def order_customers(inst: Instance, strategy: str) -> List[int]:
    ids = inst.customer_ids
    if strategy == "earliest_due":
        return sorted(ids, key=lambda i: (inst.customers[i].due, inst.customers[i].ready, i))
    if strategy == "earliest_ready":
        return sorted(ids, key=lambda i: (inst.customers[i].ready, inst.customers[i].due, i))
    if strategy == "farthest":
        return sorted(ids, key=lambda i: (-inst.dist(0, i), inst.customers[i].due, i))
    if strategy == "largest_demand":
        return sorted(ids, key=lambda i: (-inst.customers[i].demand, inst.customers[i].due, i))
    if strategy == "nearest":
        return sorted(ids, key=lambda i: (inst.dist(0, i), inst.customers[i].due, i))
    raise ValueError(f"Unknown BIH strategy: {strategy}")


def build_solution(inst: Instance, strategy: str = "earliest_due") -> List[List[int]]:
    routes: List[List[int]] = []
    for cid in order_customers(inst, strategy):
        ins = best_feasible_insertion(inst, routes, cid)
        if ins is None:
            # Start a new route if it is feasible.
            if not route_schedule(inst, [cid])[0]:
                raise ValueError(f"Customer {cid} cannot form a feasible route in {inst.name}")
            routes.append([cid])
        else:
            _, r_idx, pos = ins
            routes[r_idx].insert(pos, cid)
    return remove_empty_routes(routes)


def multi_start_bih(inst: Instance) -> List[List[int]]:
    strategies = ["earliest_due", "earliest_ready", "farthest", "largest_demand", "nearest"]
    best = None
    for st in strategies:
        sol = build_solution(inst, st)
        if is_better(inst, sol, best):
            best = sol
    assert best is not None
    return best
