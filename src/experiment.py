from __future__ import annotations
import argparse, csv, json, time
from pathlib import Path
from typing import Callable, List
from src.vrptw_core import evaluate_solution, list_instance_names, read_instance_from_zip
from src.bih import multi_start_bih
from src.standard_swarm import standard_aco, standard_gwo, standard_abc
from src.destroy_repair import bih_swarm_dr

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ZIP = ROOT / "data" / "homberger_1000_customer_instances.zip"
DEFAULT_RESULTS = ROOT / "results"


def select_instances(zip_path: Path, max_instances: int | None = None, pattern: str | None = None) -> List[str]:
    names = list_instance_names(zip_path)
    if pattern:
        p = pattern.lower()
        names = [n for n in names if p in n.lower()]
    if max_instances:
        names = names[:max_instances]
    return names


def save_routes(path: Path, instance_name: str, algorithm: str, routes: List[List[int]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["instance", "algorithm", "route_id", "sequence"])
        for k, r in enumerate(routes, start=1):
            writer.writerow([instance_name, algorithm, k, "0-" + "-".join(map(str, r)) + "-0"])


def run_algorithm(inst, algorithm: str, runtime_limit: float, seed: int, bih_initial=None):
    if algorithm == "BIH":
        return bih_initial if bih_initial is not None else multi_start_bih(inst)
    if algorithm == "ACO":
        return standard_aco(inst, runtime_limit, seed, bih_initial=bih_initial)
    if algorithm == "GWO":
        return standard_gwo(inst, runtime_limit, seed, bih_initial=bih_initial)
    if algorithm == "ABC":
        return standard_abc(inst, runtime_limit, seed, bih_initial=bih_initial)
    if algorithm in {"BIH-ACO-DR", "BIH-GWO-DR", "BIH-ABC-DR"}:
        initial = bih_initial if bih_initial is not None else multi_start_bih(inst)
        engine = algorithm.split("-")[1].lower()
        return bih_swarm_dr(inst, initial, engine=engine, runtime_limit=runtime_limit, seed=seed)
    raise ValueError(f"Unsupported algorithm: {algorithm}")


def main():
    parser = argparse.ArgumentParser(description="Run one assigned BIH-guided swarm optimization experiment on Homberger1000 VRPTW.")
    parser.add_argument("--zip", default=str(DEFAULT_ZIP), help="Path to homberger_1000_customer_instances.zip")
    parser.add_argument("--algorithms", nargs="+", default=["BIH"], help="Algorithms to run. Student version defaults to BIH only; use wrapper scripts for each assigned algorithm.")
    parser.add_argument("--runtime-limit", type=float, default=90.0, help="Seconds per instance for each stochastic algorithm; default BT setting is 90")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--max-instances", type=int, default=None)
    parser.add_argument("--pattern", default=None, help="Optional instance-name filter, e.g. C1_10 or R1")
    parser.add_argument("--out", default=str(DEFAULT_RESULTS / "summary.csv"))
    parser.add_argument("--save-routes", action="store_true")
    args = parser.parse_args()

    # Mandatory BIH-first policy: every experiment computes BIH before any swarm method.
    # If the user asks for only ACO/GWO/ABC/DR, BIH is automatically inserted as the first row
    # so that every stochastic method is initialized and compared against the same BIH baseline.
    seen = set()
    ordered_algorithms = []
    for alg in ["BIH"] + list(args.algorithms):
        if alg not in seen:
            ordered_algorithms.append(alg)
            seen.add(alg)
    args.algorithms = ordered_algorithms

    zip_path = Path(args.zip)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    instances = select_instances(zip_path, args.max_instances, args.pattern)
    rows = []

    for idx, member in enumerate(instances, start=1):
        inst = read_instance_from_zip(zip_path, member)
        print(f"[{idx}/{len(instances)}] {inst.name}")
        print("  Running mandatory BIH baseline first...")
        t_bih = time.time()
        bih_initial = multi_start_bih(inst)
        bih_runtime = time.time() - t_bih
        for alg in args.algorithms:
            t0 = time.time()
            routes = run_algorithm(inst, alg, runtime_limit=args.runtime_limit, seed=args.seed, bih_initial=bih_initial)
            runtime = bih_runtime if alg == "BIH" else time.time() - t0
            ev = evaluate_solution(inst, routes)
            row = {
                "instance": inst.name,
                "algorithm": alg,
                "feasible": ev["feasible"],
                "vehicles": ev["vehicles"],
                "distance": round(float(ev["distance"]), 3),
                "travel_time": round(float(ev["travel_time"]), 3),
                "served": ev["served"],
                "runtime_sec": round(runtime, 3),
                "seed": args.seed,
                "bih_first": True,
            }
            print("  ", row)
            rows.append(row)
            if args.save_routes:
                save_routes(DEFAULT_RESULTS / "routes" / f"{inst.name}_{alg}.csv", inst.name, alg, routes)

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    print(f"Saved summary: {out_path}")


if __name__ == "__main__":
    main()
