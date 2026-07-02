"""Core utilities for Gehring-Homberger/Solomon style VRPTW instances.

This project uses the benchmark coordinates directly. The distance and travel time
are Euclidean values computed from coordinates, which is the standard setting for
these text instances.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
import math
import re
import zipfile


@dataclass(frozen=True)
class Customer:
    cid: int
    x: float
    y: float
    demand: float
    ready: float
    due: float
    service: float


@dataclass
class Instance:
    name: str
    vehicle_number: int
    capacity: float
    customers: Dict[int, Customer]

    @property
    def depot(self) -> Customer:
        return self.customers[0]

    @property
    def customer_ids(self) -> List[int]:
        return [cid for cid in sorted(self.customers) if cid != 0]

    def dist(self, i: int, j: int) -> float:
        a, b = self.customers[i], self.customers[j]
        return math.hypot(a.x - b.x, a.y - b.y)


def parse_instance_text(text: str, fallback_name: str) -> Instance:
    lines = text.replace("\r", "").split("\n")
    name = lines[0].strip() or fallback_name

    vehicle_number, capacity = 0, 0.0
    for k, line in enumerate(lines):
        if line.strip().upper() == "VEHICLE":
            # Next numeric line after the header contains number and capacity.
            for m in range(k + 1, min(k + 6, len(lines))):
                nums = re.findall(r"[-+]?\d+(?:\.\d+)?", lines[m])
                if len(nums) >= 2:
                    vehicle_number = int(float(nums[0]))
                    capacity = float(nums[1])
                    break
            break

    customers: Dict[int, Customer] = {}
    for line in lines:
        parts = line.split()
        if len(parts) >= 7 and parts[0].lstrip("+-").isdigit():
            cid = int(parts[0])
            customers[cid] = Customer(
                cid=cid,
                x=float(parts[1]),
                y=float(parts[2]),
                demand=float(parts[3]),
                ready=float(parts[4]),
                due=float(parts[5]),
                service=float(parts[6]),
            )
    if not customers or 0 not in customers:
        raise ValueError(f"Cannot parse customers in {fallback_name}")
    return Instance(name=name, vehicle_number=vehicle_number, capacity=capacity, customers=customers)


def list_instance_names(zip_path: str | Path) -> List[str]:
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
    return sorted(names, key=lambda s: s.lower())


def read_instance_from_zip(zip_path: str | Path, member_name: str) -> Instance:
    with zipfile.ZipFile(zip_path) as zf:
        raw = zf.read(member_name).decode("utf-8", errors="replace")
    return parse_instance_text(raw, Path(member_name).stem)


def route_schedule(inst: Instance, route: List[int]) -> Tuple[bool, float, float, float, List[float]]:
    """Return feasibility, distance, load, duration, arrival/start times.

    route contains only customer ids, not depot. The vehicle starts and ends at depot 0.
    """
    time = inst.depot.ready
    distance = 0.0
    load = 0.0
    prev = 0
    starts: List[float] = []
    feasible = True

    for cid in route:
        c = inst.customers[cid]
        travel = inst.dist(prev, cid)
        distance += travel
        arrival = time + travel
        start = max(arrival, c.ready)
        if start > c.due + 1e-9:
            feasible = False
        load += c.demand
        if load > inst.capacity + 1e-9:
            feasible = False
        starts.append(start)
        time = start + c.service
        prev = cid

    distance += inst.dist(prev, 0)
    return_arrival = time + inst.dist(prev, 0)
    if return_arrival > inst.depot.due + 1e-9:
        feasible = False
    return feasible, distance, load, return_arrival - inst.depot.ready, starts


def evaluate_solution(inst: Instance, routes: List[List[int]]) -> Dict[str, float | bool | int]:
    seen: List[int] = [cid for r in routes for cid in r]
    feasible_routes = [route_schedule(inst, r)[0] for r in routes]
    all_customers = set(inst.customer_ids)
    seen_set = set(seen)
    feasible = (
        all(feasible_routes)
        and len(seen) == len(seen_set)
        and seen_set == all_customers
        and len(routes) <= inst.vehicle_number
    )
    total_distance = sum(route_schedule(inst, r)[1] for r in routes)
    total_time = sum(route_schedule(inst, r)[3] for r in routes)
    return {
        "feasible": feasible,
        "vehicles": len([r for r in routes if r]),
        "distance": total_distance,
        "travel_time": total_time,
        "served": len(seen_set),
    }


def objective_tuple(inst: Instance, routes: List[List[int]]) -> Tuple[int, float, float, int]:
    ev = evaluate_solution(inst, routes)
    penalty = 0 if ev["feasible"] else 10**9
    return (int(ev["vehicles"]) + penalty, float(ev["distance"]), float(ev["travel_time"]), penalty)


def is_better(inst: Instance, a: List[List[int]], b: List[List[int]] | None) -> bool:
    if b is None:
        return True
    return objective_tuple(inst, a) < objective_tuple(inst, b)


def copy_routes(routes: List[List[int]]) -> List[List[int]]:
    return [list(r) for r in routes]


def insertion_delta(inst: Instance, route: List[int], cid: int, pos: int) -> float:
    prev_id = 0 if pos == 0 else route[pos - 1]
    next_id = 0 if pos == len(route) else route[pos]
    return inst.dist(prev_id, cid) + inst.dist(cid, next_id) - inst.dist(prev_id, next_id)


def best_feasible_insertion(inst: Instance, routes: List[List[int]], cid: int) -> Tuple[float, int, int] | None:
    best = None
    for r_idx, route in enumerate(routes):
        for pos in range(len(route) + 1):
            new_route = route[:pos] + [cid] + route[pos:]
            if route_schedule(inst, new_route)[0]:
                delta = insertion_delta(inst, route, cid, pos)
                cand = (delta, r_idx, pos)
                if best is None or cand < best:
                    best = cand
    return best


def remove_empty_routes(routes: List[List[int]]) -> List[List[int]]:
    return [r for r in routes if r]
