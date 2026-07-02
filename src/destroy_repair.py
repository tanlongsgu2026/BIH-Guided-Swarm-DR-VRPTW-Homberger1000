from __future__ import annotations
from typing import Dict, List, Tuple
import random
import math
import time
from src.vrptw_core import Instance, copy_routes, evaluate_solution, insertion_delta, is_better, objective_tuple, remove_empty_routes, route_schedule


def route_waiting(inst: Instance, route: List[int]) -> float:
    waiting = 0.0
    prev = 0
    t = inst.depot.ready
    for cid in route:
        c = inst.customers[cid]
        arr = t + inst.dist(prev, cid)
        waiting += max(0.0, c.ready - arr)
        t = max(arr, c.ready) + c.service
        prev = cid
    return waiting


def weak_route_score(inst: Instance, route: List[int]) -> float:
    """Score weak routes. Higher value means the route is more likely to be destroyed.

    Components follow the proposed BIH-SO-DR idea: low load, long distance per
    customer, high waiting time, and small route size are treated as signs that a
    route may be eliminated or restructured.
    """
    if not route:
        return -1e9
    feasible, dist, load, duration, starts = route_schedule(inst, route)
    load_ratio = load / max(inst.capacity, 1.0)
    distance_per_customer = dist / max(len(route), 1)
    waiting = route_waiting(inst, route)
    small_route = 1.0 / max(len(route), 1)
    return (
        0.35 * (1.0 - load_ratio)
        + 0.30 * (distance_per_customer / 1000.0)
        + 0.20 * (waiting / 1000.0)
        + 0.15 * small_route
    )


def relatedness(inst: Instance, i: int, j: int) -> float:
    ci, cj = inst.customers[i], inst.customers[j]
    return (
        inst.dist(i, j)
        + 0.20 * abs(ci.ready - cj.ready)
        + 0.20 * abs(ci.due - cj.due)
        + 2.00 * abs(ci.demand - cj.demand)
    )


def removal_cost(inst: Instance, route: List[int], pos: int) -> float:
    cid = route[pos]
    prev_id = 0 if pos == 0 else route[pos - 1]
    next_id = 0 if pos == len(route) - 1 else route[pos + 1]
    return inst.dist(prev_id, cid) + inst.dist(cid, next_id) - inst.dist(prev_id, next_id)


def destroy(inst: Instance, routes: List[List[int]], rng: random.Random, ratio: float, mode: str = "mixed") -> Tuple[List[List[int]], List[int], str]:
    """Destroy part of a solution.

    The function supports random, worst-cost, related, and route removal. Route
    removal is allowed to remove an entire weak route when that route is small
    enough. This gives the algorithm a real chance to reduce the number of
    vehicles, which is essential for lexicographic VRPTW evaluation.
    """
    routes2 = copy_routes(routes)
    n = len(inst.customer_ids)
    n_remove = max(5, int(n * ratio))
    n_remove = min(max(5, n_remove), 20)
    removed: List[int] = []

    modes = ["random", "worst", "related", "route"] if mode == "mixed" else [mode]
    chosen = rng.choice(modes)

    if chosen == "route" and routes2:
        ranked = sorted(range(len(routes2)), key=lambda r: weak_route_score(inst, routes2[r]), reverse=True)
        target = ranked[0]
        # Try full weak-route removal first. If it is too large, remove the weakest subset.
        take = routes2[target][:]
        if len(take) <= max(n_remove, 35):
            removed.extend(take)
            routes2[target] = []
        else:
            by_cost = sorted(range(len(take)), key=lambda p: removal_cost(inst, take, p), reverse=True)
            for p in sorted(by_cost[:n_remove], reverse=True):
                removed.append(routes2[target].pop(p))

    elif chosen == "worst":
        candidates = []
        for r_idx, route in enumerate(routes2):
            for pos, cid in enumerate(route):
                candidates.append((removal_cost(inst, route, pos), r_idx, cid))
        for _, r_idx, cid in sorted(candidates, reverse=True):
            if len(removed) >= n_remove:
                break
            if r_idx < len(routes2) and cid in routes2[r_idx]:
                routes2[r_idx].remove(cid)
                removed.append(cid)

    elif chosen == "related":
        all_ids = [cid for r in routes2 for cid in r]
        if all_ids:
            seed = rng.choice(all_ids)
            rel = sorted(all_ids, key=lambda cid: relatedness(inst, seed, cid))
            for cid in rel[:n_remove]:
                for r in routes2:
                    if cid in r:
                        r.remove(cid)
                        removed.append(cid)
                        break

    else:
        all_pairs = [(r_idx, cid) for r_idx, r in enumerate(routes2) for cid in r]
        rng.shuffle(all_pairs)
        for r_idx, cid in all_pairs[:n_remove]:
            if r_idx < len(routes2) and cid in routes2[r_idx]:
                routes2[r_idx].remove(cid)
                removed.append(cid)

    return remove_empty_routes(routes2), list(dict.fromkeys(removed)), chosen


def candidate_positions(inst: Instance, route: List[int], cid: int, rng: random.Random, nearest_k: int = 5) -> List[int]:
    positions = {0, len(route)}
    if route:
        positions.add(len(route) // 2)
        near = sorted(range(len(route)), key=lambda k: min(inst.dist(route[k], cid), inst.dist(cid, route[k])))[:nearest_k]
        for k in near:
            positions.add(k)
            positions.add(k + 1)
        # Small random sample to avoid missing useful non-nearest positions.
        for _ in range(min(4, len(route))):
            positions.add(rng.randrange(0, len(route) + 1))
    return sorted(p for p in positions if 0 <= p <= len(route))


def feasible_insertions(inst: Instance, routes: List[List[int]], cid: int, rng: random.Random) -> List[Tuple[float, int, int]]:
    out: List[Tuple[float, int, int]] = []
    # Limit insertion checks to promising routes for speed on 1000-customer instances.
    # A route is promising if it has enough remaining capacity and contains at least
    # one customer geographically close to cid, or if it is weak/short enough to be
    # restructured.
    c = inst.customers[cid]
    route_scores = []
    for r_idx, route in enumerate(routes):
        load = sum(inst.customers[x].demand for x in route)
        if load + c.demand > inst.capacity + 1e-9:
            continue
        if route:
            sample = route if len(route) <= 12 else rng.sample(route, 12)
            proximity = min(min(inst.dist(x, cid), inst.dist(cid, x)) for x in sample)
        else:
            proximity = inst.dist(0, cid)
        route_scores.append((proximity - 50.0 * weak_route_score(inst, route), r_idx))
    candidate_route_ids = [r for _, r in sorted(route_scores)[: min(25, len(route_scores))]]
    for r_idx in candidate_route_ids:
        route = routes[r_idx]
        for pos in candidate_positions(inst, route, cid, rng):
            new_route = route[:pos] + [cid] + route[pos:]
            if route_schedule(inst, new_route)[0]:
                out.append((insertion_delta(inst, route, cid, pos), r_idx, pos))
    if route_schedule(inst, [cid])[0]:
        out.append((inst.dist(0, cid) + inst.dist(cid, 0), len(routes), 0))
    out.sort(key=lambda x: x[0])
    return out


def best_feasible_insertions(inst: Instance, routes: List[List[int]], cid: int, rng: random.Random, k: int = 2) -> List[Tuple[float, int, int]]:
    return feasible_insertions(inst, routes, cid, rng)[:k]


def regret2_repair(inst: Instance, routes: List[List[int]], removed: List[int], rng: random.Random, noise: float = 0.0) -> List[List[int]]:
    """True regret-2 insertion.

    At each step, it computes Cost1 and Cost2 for every uninserted customer and
    prioritizes the customer with maximum Cost2-Cost1. This is stronger than pure
    best insertion because it inserts difficult customers before their good slots
    disappear.
    """
    routes2 = copy_routes(routes)
    pending = list(dict.fromkeys(removed))
    while pending:
        selected = None
        for cid in pending:
            ins = best_feasible_insertions(inst, routes2, cid, rng, k=2)
            if not ins:
                continue
            cost1, r1, p1 = ins[0]
            cost2 = ins[1][0] if len(ins) > 1 else cost1 + 1e6
            regret = cost2 - cost1
            score = (regret, -cost1 + rng.random() * noise, cid, r1, p1)
            if selected is None or score > selected:
                selected = score
        if selected is None:
            # Fallback: open singleton feasible routes. If singleton is infeasible,
            # keep it as a visible infeasibility rather than losing the customer.
            for cid in pending:
                routes2.append([cid])
            break
        _, _, cid, r_idx, pos = selected
        if r_idx == len(routes2):
            routes2.append([cid])
        else:
            routes2[r_idx].insert(pos, cid)
        pending.remove(cid)
    return remove_empty_routes(routes2)


# Backward-compatible alias used by older modules.
regret_repair = regret2_repair


def aco_repair(inst: Instance, routes: List[List[int]], removed: List[int], rng: random.Random, ants: int = 10, iterations: int = 1) -> List[List[int]]:
    """ACO repair with a real pheromone matrix on the removed-customer sequence."""
    if not removed:
        return copy_routes(routes)
    nodes = [0] + list(dict.fromkeys(removed))
    tau: Dict[Tuple[int, int], float] = {(i, j): 1.0 for i in nodes for j in removed if i != j}
    best = None
    alpha, beta, rho = 1.0, 3.0, 0.20

    for _ in range(max(1, iterations)):
        ant_solutions = []
        for _a in range(max(1, ants)):
            pending = list(removed)
            order: List[int] = []
            prev = 0
            while pending:
                weights = []
                for cid in pending:
                    c = inst.customers[cid]
                    heuristic = 1.0 / (1.0 + inst.dist(prev, cid) + 0.05 * max(0.0, c.ready - inst.depot.ready))
                    weights.append((tau.get((prev, cid), 1.0) ** alpha) * (heuristic ** beta))
                total = sum(weights)
                if total <= 0:
                    idx = rng.randrange(len(pending))
                else:
                    pick, acc, idx = rng.random() * total, 0.0, 0
                    for k, w in enumerate(weights):
                        acc += w
                        if acc >= pick:
                            idx = k
                            break
                cid = pending.pop(idx)
                order.append(cid)
                prev = cid
            sol = regret2_repair(inst, routes, order, rng, noise=0.01)
            ant_solutions.append((sol, order))
            if is_better(inst, sol, best):
                best = sol
        # Evaporation.
        for key in list(tau):
            tau[key] *= (1.0 - rho)
            if tau[key] < 1e-6:
                tau[key] = 1e-6
        # Deposit pheromone from the best ants.
        ant_solutions.sort(key=lambda so: objective_tuple(inst, so[0]))
        for sol, order in ant_solutions[: max(1, len(ant_solutions) // 3)]:
            ev = evaluate_solution(inst, sol)
            quality = 1.0 / (1.0 + float(ev["vehicles"]) * 10000.0 + float(ev["distance"]))
            prev = 0
            for cid in order:
                tau[(prev, cid)] = tau.get((prev, cid), 1.0) + 1e5 * quality
                prev = cid
    return best if best is not None else regret2_repair(inst, routes, removed, rng)


def perturb_toward(order: List[int], leader: List[int], rng: random.Random, strength: float) -> List[int]:
    child = order[:]
    pos = {cid: i for i, cid in enumerate(child)}
    for cid in leader:
        if rng.random() > strength:
            continue
        target = leader.index(cid)
        cur = pos.get(cid)
        if cur is None or cur == target or target >= len(child):
            continue
        other = child[target]
        child[target], child[cur] = child[cur], child[target]
        pos[cid], pos[other] = target, cur
    return child


def gwo_repair(inst: Instance, routes: List[List[int]], removed: List[int], rng: random.Random, wolves: int = 10, iterations: int = 1) -> List[List[int]]:
    """Permutation GWO repair with alpha, beta, and delta leaders.

    Continuous GWO position updates are mapped to permutation moves: wolves copy
    ordered subsequences and positions from alpha/beta/delta with a decreasing
    control coefficient a.
    """
    if not removed:
        return copy_routes(routes)
    base = sorted(removed, key=lambda cid: (inst.customers[cid].due, inst.dist(0, cid)))
    population: List[List[int]] = []
    for _ in range(max(3, wolves)):
        order = base[:]
        swaps = max(1, int(len(order) * rng.uniform(0.05, 0.30)))
        for _s in range(swaps):
            i, j = rng.randrange(len(order)), rng.randrange(len(order))
            order[i], order[j] = order[j], order[i]
        population.append(order)

    best = None
    for it in range(max(1, iterations)):
        scored = []
        for order in population:
            sol = regret2_repair(inst, routes, order, rng, noise=0.02)
            scored.append((objective_tuple(inst, sol), order, sol))
            if is_better(inst, sol, best):
                best = sol
        scored.sort(key=lambda x: x[0])
        alpha = scored[0][1]
        beta = scored[1][1] if len(scored) > 1 else alpha
        delta = scored[2][1] if len(scored) > 2 else beta
        a = 2.0 * (1.0 - it / max(1, iterations))
        new_pop = [alpha[:], beta[:], delta[:]]
        while len(new_pop) < len(population):
            parent = rng.choice(population)
            child = perturb_toward(parent, alpha, rng, min(0.80, 0.20 + 0.25 * a))
            child = perturb_toward(child, beta, rng, min(0.50, 0.10 + 0.15 * a))
            child = perturb_toward(child, delta, rng, min(0.35, 0.05 + 0.10 * a))
            # Exploration move governed by |A| in GWO spirit.
            swaps = max(1, int(len(child) * rng.uniform(0.01, 0.08) * a))
            for _s in range(swaps):
                i, j = rng.randrange(len(child)), rng.randrange(len(child))
                child[i], child[j] = child[j], child[i]
            new_pop.append(child)
        population = new_pop[: len(population)]
    return best if best is not None else regret2_repair(inst, routes, removed, rng)


def mutate_order(order: List[int], rng: random.Random) -> List[int]:
    child = order[:]
    if len(child) < 2:
        return child
    op = rng.choice(["swap", "reverse", "insert"])
    i, j = sorted([rng.randrange(len(child)), rng.randrange(len(child))])
    if i == j:
        j = min(len(child) - 1, i + 1)
    if op == "swap":
        child[i], child[j] = child[j], child[i]
    elif op == "reverse":
        child[i:j + 1] = reversed(child[i:j + 1])
    else:
        cid = child.pop(j)
        child.insert(i, cid)
    return child


def solution_fitness(inst: Instance, sol: List[List[int]]) -> float:
    obj = objective_tuple(inst, sol)
    return 1.0 / (1.0 + obj[0] * 100000.0 + obj[1])


def abc_repair(inst: Instance, routes: List[List[int]], removed: List[int], rng: random.Random, bees: int = 10, cycles: int = 1, limit: int = 2) -> List[List[int]]:
    """ABC repair with employed, onlooker, and scout bee phases."""
    if not removed:
        return copy_routes(routes)
    base = sorted(removed, key=lambda cid: (inst.customers[cid].due, -inst.customers[cid].demand))
    food_sources: List[List[int]] = []
    for _ in range(max(3, bees)):
        order = base[:]
        for _s in range(max(1, int(len(order) * rng.uniform(0.03, 0.20)))):
            i, j = rng.randrange(len(order)), rng.randrange(len(order))
            order[i], order[j] = order[j], order[i]
        food_sources.append(order)
    trials = [0 for _ in food_sources]
    best = None

    for _cycle in range(max(1, cycles)):
        sols = [regret2_repair(inst, routes, fs, rng, noise=0.03) for fs in food_sources]
        for sol in sols:
            if is_better(inst, sol, best):
                best = sol
        # Employed bee phase.
        for i, fs in enumerate(food_sources):
            cand = mutate_order(fs, rng)
            cand_sol = regret2_repair(inst, routes, cand, rng, noise=0.03)
            if is_better(inst, cand_sol, sols[i]):
                food_sources[i] = cand
                sols[i] = cand_sol
                trials[i] = 0
                if is_better(inst, cand_sol, best):
                    best = cand_sol
            else:
                trials[i] += 1
        # Onlooker bee phase.
        fitnesses = [solution_fitness(inst, sol) for sol in sols]
        total = sum(fitnesses)
        for _ in range(len(food_sources)):
            if total <= 0:
                i = rng.randrange(len(food_sources))
            else:
                pick, acc, i = rng.random() * total, 0.0, 0
                for k, fit in enumerate(fitnesses):
                    acc += fit
                    if acc >= pick:
                        i = k
                        break
            cand = mutate_order(food_sources[i], rng)
            cand_sol = regret2_repair(inst, routes, cand, rng, noise=0.03)
            if is_better(inst, cand_sol, sols[i]):
                food_sources[i] = cand
                sols[i] = cand_sol
                trials[i] = 0
                if is_better(inst, cand_sol, best):
                    best = cand_sol
            else:
                trials[i] += 1
        # Scout bee phase.
        for i, tr in enumerate(trials):
            if tr >= limit:
                scout = base[:]
                rng.shuffle(scout)
                food_sources[i] = scout
                trials[i] = 0
    return best if best is not None else regret2_repair(inst, routes, removed, rng)


def try_route_elimination(inst: Instance, routes: List[List[int]], rng: random.Random, time_budget: float = 0.2) -> List[List[int]]:
    """Try to remove one complete weak route and reinsert all its customers."""
    end = time.time() + max(0.0, time_budget)
    best = copy_routes(routes)
    ranked = sorted(range(len(best)), key=lambda r: weak_route_score(inst, best[r]), reverse=True)
    for r_idx in ranked[: min(6, len(ranked))]:
        if time.time() >= end or r_idx >= len(best):
            break
        removed = best[r_idx][:]
        if not removed or len(removed) > 60:
            continue
        partial = [r[:] for k, r in enumerate(best) if k != r_idx]
        cand = regret2_repair(inst, partial, removed, rng, noise=0.01)
        if is_better(inst, cand, best):
            best = cand
    return remove_empty_routes(best)


def local_search(inst: Instance, routes: List[List[int]], time_limit: float, rng: random.Random) -> List[List[int]]:
    """Sampled local search with relocate, swap, 2-opt, Or-opt, cross-exchange, and route elimination."""
    end = time.time() + max(0.0, time_limit)
    best = copy_routes(routes)
    best = try_route_elimination(inst, best, rng, time_budget=min(0.25, max(0.0, time_limit * 0.25)))
    trials = 0
    ops = ["relocate", "swap", "two_opt", "or_opt", "cross_exchange"]
    while time.time() < end and trials < 40:
        trials += 1
        if not best:
            break
        op = rng.choice(ops)
        cand = None
        if op == "relocate":
            non_empty = [i for i, r in enumerate(best) if r]
            if not non_empty:
                continue
            a = rng.choice(non_empty)
            pos = rng.randrange(len(best[a]))
            cid = best[a][pos]
            temp = copy_routes(best)
            temp[a].pop(pos)
            temp = remove_empty_routes(temp)
            ins = feasible_insertions(inst, temp, cid, rng)
            if ins:
                _, b, q = ins[0]
                cand = copy_routes(temp)
                if b == len(cand):
                    cand.append([cid])
                else:
                    cand[b].insert(q, cid)
        elif op == "swap":
            non_empty = [i for i, r in enumerate(best) if r]
            if len(non_empty) < 1:
                continue
            a, b = rng.choice(non_empty), rng.choice(non_empty)
            if not best[a] or not best[b]:
                continue
            i, j = rng.randrange(len(best[a])), rng.randrange(len(best[b]))
            cand = copy_routes(best)
            cand[a][i], cand[b][j] = cand[b][j], cand[a][i]
            if not (route_schedule(inst, cand[a])[0] and route_schedule(inst, cand[b])[0]):
                cand = None
        elif op == "two_opt":
            candidates = [i for i, r in enumerate(best) if len(r) >= 4]
            if not candidates:
                continue
            r_idx = rng.choice(candidates)
            route = best[r_idx]
            i = rng.randrange(0, len(route) - 2)
            j = rng.randrange(i + 2, len(route))
            cand = copy_routes(best)
            cand[r_idx] = route[:i] + list(reversed(route[i:j])) + route[j:]
            if not route_schedule(inst, cand[r_idx])[0]:
                cand = None
        elif op == "or_opt":
            candidates = [i for i, r in enumerate(best) if len(r) >= 3]
            if not candidates:
                continue
            a = rng.choice(candidates)
            route = best[a]
            length = rng.choice([2, 3]) if len(route) >= 3 else 2
            i = rng.randrange(0, len(route) - length + 1)
            chain = route[i:i + length]
            temp = copy_routes(best)
            del temp[a][i:i + length]
            temp = remove_empty_routes(temp)
            # Insert chain as a block into a sampled feasible place.
            cand_best = None
            for b_idx, r in enumerate(temp):
                for p in candidate_positions(inst, r, chain[0], rng, nearest_k=3):
                    nr = r[:p] + chain + r[p:]
                    if route_schedule(inst, nr)[0]:
                        c2 = copy_routes(temp)
                        c2[b_idx] = nr
                        if cand_best is None or is_better(inst, c2, cand_best):
                            cand_best = c2
            if route_schedule(inst, chain)[0]:
                c2 = copy_routes(temp) + [chain]
                if cand_best is None or is_better(inst, c2, cand_best):
                    cand_best = c2
            cand = cand_best
        else:  # cross_exchange
            idxs = [i for i, r in enumerate(best) if len(r) >= 2]
            if len(idxs) < 2:
                continue
            a, b = rng.sample(idxs, 2)
            ra, rb = best[a], best[b]
            la = rng.choice([1, 2])
            lb = rng.choice([1, 2])
            ia = rng.randrange(0, len(ra) - la + 1)
            ib = rng.randrange(0, len(rb) - lb + 1)
            cand = copy_routes(best)
            seg_a, seg_b = ra[ia:ia + la], rb[ib:ib + lb]
            cand[a] = ra[:ia] + seg_b + ra[ia + la:]
            cand[b] = rb[:ib] + seg_a + rb[ib + lb:]
            if not (route_schedule(inst, cand[a])[0] and route_schedule(inst, cand[b])[0]):
                cand = None
        if cand is not None:
            cand = remove_empty_routes(cand)
            if is_better(inst, cand, best):
                best = cand
                # After a route-count improvement, try another elimination quickly.
                if evaluate_solution(inst, cand)["vehicles"] < evaluate_solution(inst, routes)["vehicles"]:
                    best = try_route_elimination(inst, best, rng, time_budget=0.1)
    return remove_empty_routes(best)


def bih_swarm_dr(inst: Instance, initial_routes: List[List[int]], engine: str, runtime_limit: float, seed: int, destroy_ratio: float = 0.03) -> List[List[int]]:
    # Official experiment setting: DR repair population size = 10 individuals.
    # ACO uses 10 ants, GWO uses 10 wolves, and ABC uses 10 bees inside each repair phase.
    rng = random.Random(seed)
    start = time.time()
    best = copy_routes(initial_routes)
    current = copy_routes(initial_routes)
    no_improve = 0

    while time.time() - start < runtime_limit:
        ratio = destroy_ratio
        if no_improve >= 20:
            ratio = max(ratio, 0.12)
        if no_improve >= 50:
            ratio = max(ratio, 0.20)

        partial, removed, mode = destroy(inst, current, rng, ratio=ratio, mode="mixed")
        if engine == "aco":
            candidate = aco_repair(inst, partial, removed, rng)
        elif engine == "gwo":
            candidate = gwo_repair(inst, partial, removed, rng)
        elif engine == "abc":
            candidate = abc_repair(inst, partial, removed, rng)
        else:
            candidate = regret2_repair(inst, partial, removed, rng)

        remaining = max(0.0, runtime_limit - (time.time() - start))
        candidate = local_search(inst, candidate, min(0.4, remaining), rng)

        if is_better(inst, candidate, best):
            best = candidate
            current = candidate
            no_improve = 0
        else:
            no_improve += 1
            # Diversified acceptance. Do not accept infeasible candidates unless the current solution is also infeasible.
            if evaluate_solution(inst, candidate)["feasible"] and rng.random() < 0.08:
                current = candidate
    return best
