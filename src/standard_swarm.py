from __future__ import annotations
from typing import List
import random, time
from src.vrptw_core import Instance, is_better, remove_empty_routes, route_schedule, best_feasible_insertion
from src.bih import order_customers
from src.destroy_repair import regret_repair, local_search


def decode_order(inst: Instance, order: List[int]) -> List[List[int]]:
    """Fast decoder for baseline swarm algorithms.

    It tries to append a customer to the best feasible existing route; if no route can
    accept the customer, a new route is opened. This is intentionally faster and
    weaker than BIH, so ACO/GWO/ABC can be used as baseline comparisons.
    """
    routes: List[List[int]] = []
    for cid in order:
        best = None
        for r_idx, route in enumerate(routes):
            new_route = route + [cid]
            if route_schedule(inst, new_route)[0]:
                delta = inst.dist(route[-1] if route else 0, cid) + inst.dist(cid, 0) - inst.dist(route[-1] if route else 0, 0)
                cand = (delta, r_idx)
                if best is None or cand < best:
                    best = cand
        if best is None:
            routes.append([cid])
        else:
            _, r = best
            routes[r].append(cid)
    return remove_empty_routes(routes)


def standard_aco(inst: Instance, runtime_limit: float, seed: int, ants: int = 20, bih_initial: List[List[int]] | None = None) -> List[List[int]]:
    rng = random.Random(seed)
    end = time.time() + runtime_limit
    base = order_customers(inst, "earliest_due")
    constructive_best = decode_order(inst, base)
    best = bih_initial if bih_initial is not None else constructive_best
    # BIH-first baseline ACO: BIH is always used as the mandatory initial incumbent.
    while time.time() < end:
        for _ in range(max(1, ants)):
            order = base[:]
            swaps = max(1, int(len(order) * rng.uniform(0.01, 0.08)))
            for _ in range(swaps):
                i = rng.randrange(len(order))
                window = min(len(order) - 1, i + rng.randrange(1, 25))
                j = rng.randrange(i, window + 1)
                order[i], order[j] = order[j], order[i]
            sol = decode_order(inst, order)
            if is_better(inst, sol, best):
                best = sol
    return best

def standard_gwo(inst: Instance, runtime_limit: float, seed: int, wolves: int = 20, bih_initial: List[List[int]] | None = None) -> List[List[int]]:
    rng = random.Random(seed)
    end = time.time() + runtime_limit
    base = order_customers(inst, "earliest_due")
    constructive_best = decode_order(inst, base)
    best = bih_initial if bih_initial is not None else constructive_best
    while time.time() < end:
        for _ in range(max(1, wolves)):
            order = base[:]
            swaps = max(1, int(len(order) * rng.uniform(0.03, 0.25)))
            for _ in range(swaps):
                i, j = rng.randrange(len(order)), rng.randrange(len(order))
                order[i], order[j] = order[j], order[i]
            sol = decode_order(inst, order)
            if is_better(inst, sol, best):
                best = sol
    return best


def standard_abc(inst: Instance, runtime_limit: float, seed: int, bees: int = 20, bih_initial: List[List[int]] | None = None) -> List[List[int]]:
    rng = random.Random(seed)
    end = time.time() + runtime_limit
    base = order_customers(inst, "earliest_due")
    constructive_best = decode_order(inst, base)
    best = bih_initial if bih_initial is not None else constructive_best
    while time.time() < end:
        for _ in range(max(1, bees)):
            # Bee baseline: nectar score is mostly due-date urgency plus a small random term.
            order = sorted(
                inst.customer_ids,
                key=lambda cid: (
                    inst.customers[cid].due
                    + rng.uniform(-50, 50)
                    - 0.5 * inst.customers[cid].demand
                ),
            )
            sol = decode_order(inst, order)
            if is_better(inst, sol, best):
                best = sol
    return best
