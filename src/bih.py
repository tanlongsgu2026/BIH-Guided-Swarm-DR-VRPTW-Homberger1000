import numpy as np
import math, json, time, argparse, zipfile, re, csv
from pathlib import Path
from typing import List

from src.vrptw_core import (
    Instance,
    best_feasible_insertion,
    evaluate_solution,
    is_better,
    remove_empty_routes,
    route_schedule,
    parse_instance_text
)


# ==========================================
# KHỐI TƯƠNG THÍCH NGƯỢC (BACKWARD COMPATIBILITY)
# Giữ nguyên bản để experiment.py có thể import mà không báo lỗi
# ==========================================
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


# ==========================================
# LÕI THUẬT TOÁN ĐỘC LẬP (TỐC ĐỘ GỐC NUMPY)
# Dùng để chạy trực tiếp sinh file JSON
# ==========================================
class FastVRPTWState:
    def __init__(self, route):
        self.route = np.array(route)
        self.size = len(self.route)
        self.arr_time = np.zeros(self.size)
        self.dep_time = np.zeros(self.size)
        self.load = np.zeros(self.size)

    def update_states(self, time_matrix, ready_time, service_time, demand, due_time):
        self.size = len(self.route)
        self.arr_time = np.zeros(self.size)
        self.dep_time = np.zeros(self.size)
        self.start_time = np.zeros(self.size)
        self.wait_time = np.zeros(self.size)
        self.slack = np.zeros(self.size)
        self.load = np.zeros(self.size)
        current_time = 0.0
        current_load = 0.0

        for i in range(self.size):
            node = self.route[i]
            if i > 0:
                current_time = self.dep_time[i - 1] + time_matrix[self.route[i - 1], node]
            self.arr_time[i] = current_time
            self.wait_time[i] = max(0.0, ready_time[node] - current_time)
            self.start_time[i] = current_time + self.wait_time[i]
            self.dep_time[i] = self.start_time[i] + service_time[node]
            current_load += demand[node]
            self.load[i] = current_load

        self.slack[-1] = due_time[self.route[-1]] - self.start_time[-1]
        for i in range(self.size - 2, -1, -1):
            node = self.route[i]
            shift_here = due_time[node] - self.start_time[i]
            shift_next = self.wait_time[i + 1] + self.slack[i + 1]
            self.slack[i] = min(shift_here, shift_next)


def find_best_insertion(job, states, dist_matrix, time_matrix, ready_time, due_time, service_time, demand, capacity,
                        alpha, beta):
    best_cost = np.inf
    best_route_idx, best_insert_pos = -1, -1

    for r_idx, state in enumerate(states):
        if state.load[-1] + demand[job] > capacity: continue
        i_nodes, j_nodes = state.route[:-1], state.route[1:]

        delta_dist = dist_matrix[i_nodes, job] + dist_matrix[job, j_nodes] - dist_matrix[i_nodes, j_nodes]
        arr_job = state.dep_time[:-1] + time_matrix[i_nodes, job]
        start_job = np.maximum(arr_job, ready_time[job])
        dep_job = start_job + service_time[job]

        new_arr_j = dep_job + time_matrix[job, j_nodes]
        delay_arr_j = np.maximum(0.0, new_arr_j - state.arr_time[1:])

        valid_mask = (arr_job <= due_time[job]) & (delay_arr_j <= (state.wait_time[1:] + state.slack[1:]))
        if not np.any(valid_mask): continue

        time_shift = np.maximum(0.0, delay_arr_j - state.wait_time[1:])
        total_costs = alpha * delta_dist + beta * time_shift
        total_costs[~valid_mask] = np.inf

        min_pos = np.argmin(total_costs)
        if total_costs[min_pos] < best_cost:
            best_cost = total_costs[min_pos]
            best_route_idx, best_insert_pos = r_idx, min_pos + 1

    return best_route_idx, best_insert_pos


def multi_seed_bih(dist_matrix, time_matrix, ready_time, due_time, service_time, demand, capacity, alpha=1.0, beta=1.0):
    customers = list(range(1, len(demand)))
    seeds = {
        "earliest_due": sorted(customers, key=lambda i: (due_time[i], ready_time[i], i)),
        "earliest_ready": sorted(customers, key=lambda i: (ready_time[i], due_time[i], i)),
        "farthest": sorted(customers, key=lambda i: (-dist_matrix[0, i], due_time[i], i)),
        "largest_demand": sorted(customers, key=lambda i: (-demand[i], due_time[i], i)),
        "nearest": sorted(customers, key=lambda i: (dist_matrix[0, i], due_time[i], i))
    }
    min_veh, min_dist, best_solution = np.inf, np.inf, None

    for _, order in seeds.items():
        states = []
        for job in order:
            r_idx, pos = find_best_insertion(job, states, dist_matrix, time_matrix, ready_time, due_time, service_time,
                                             demand, capacity, alpha, beta)
            if r_idx == -1:
                new_state = FastVRPTWState([0, job, 0])
                new_state.update_states(time_matrix, ready_time, service_time, demand, due_time)
                states.append(new_state)
            else:
                states[r_idx].route = np.insert(states[r_idx].route, pos, job)
                states[r_idx].update_states(time_matrix, ready_time, service_time, demand, due_time)

        sol = [s.route.tolist() for s in states]
        num_veh = len(sol)
        dist = sum(dist_matrix[r[i], r[i + 1]] for r in sol for i in range(len(r) - 1))

        if num_veh < min_veh or (num_veh == min_veh and dist < min_dist):
            min_veh, min_dist, best_solution = num_veh, dist, sol

    return best_solution, min_veh, min_dist


# ==========================================
# CƠ CHẾ ĐỌC FILE ZIP VÀ XUẤT JSON + BÁO CÁO CSV (ĐỒNG NHẤT 100%)
# ==========================================
def process_instance(file_name: str, file_content: str, out_dir: Path, seed_value: int = 2026):
    t0 = time.time()
    lines = file_content.replace("\r", "").split("\n")

    capacity = 0.0
    for k, line in enumerate(lines):
        if line.strip().upper() == "VEHICLE":
            for m in range(k + 1, min(k + 6, len(lines))):
                nums = re.findall(r"[-+]?\d+(?:\.\d+)?", lines[m])
                if len(nums) >= 2:
                    capacity = float(nums[1])
                    break
            break

    data_lines = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 7 and parts[0].lstrip("+-").isdigit():
            data_lines.append([float(x) for x in parts])

    data = np.array(data_lines)
    if len(data) == 0:
        print(f"[!] Bỏ qua {file_name}: Không tìm thấy dữ liệu hợp lệ.")
        return None

    coords, demand = data[:, 1:3], data[:, 3]
    ready_time, due_time, service_time = data[:, 4], data[:, 5], data[:, 6]
    num_nodes = len(data)

    dist_matrix = np.zeros((num_nodes, num_nodes))
    for i in range(num_nodes):
        for j in range(num_nodes):
            dist_matrix[i, j] = math.hypot(coords[i, 0] - coords[j, 0], coords[i, 1] - coords[j, 1])

    best_routes, _, _ = multi_seed_bih(dist_matrix, dist_matrix, ready_time, due_time, service_time, demand, capacity,
                                       1.0, 0.0)

    final_routes = [[int(n) for n in r if n != 0] for r in best_routes] if best_routes else []
    runtime = time.time() - t0

    stem_name = Path(file_name).stem

    out_file = out_dir / "routes" / f"{stem_name}_BIH.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(final_routes, f)

    inst = parse_instance_text(file_content, stem_name)
    ev = evaluate_solution(inst, final_routes)

    print(
        f"[+] Hoàn thành {stem_name:<15} | Xe: {ev['vehicles']:<3} | KC: {ev['distance']:<8.2f} | Thời gian: {runtime:.2f}s")

    return {
        "instance": inst.name,
        "algorithm": "BIH",
        "feasible": ev["feasible"],
        "vehicles": ev["vehicles"],
        "distance": round(float(ev["distance"]), 3),
        "travel_time": round(float(ev["travel_time"]), 3),
        "served": ev["served"],
        "runtime_sec": round(runtime, 3),
        "seed": seed_value,
        "bih_first": True,
    }


# ==========================================
# TRÌNH KHỞI CHẠY (HỖ TRỢ CẢ NÚT RUN VÀ LỆNH TERMINAL)
# ==========================================
if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(description="Chạy bộ sinh nghiệm BIH siêu tốc bằng NumPy từ file ZIP.")
    parser.add_argument("--zip", default=str(ROOT / "data" / "homberger_1000_customer_instances.zip"),
                        help="Đường dẫn đến file ZIP")
    parser.add_argument("--out", default=str(ROOT / "results"), help="Thư mục xuất file JSON và CSV")
    parser.add_argument("--seed", type=int, default=2026, help="Seed mặc định của dự án")
    args = parser.parse_args()

    zip_path = Path(args.zip)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not zip_path.exists():
        print(f"[!] LỖI: Không tìm thấy file ZIP tại: {zip_path}")
        exit(1)

    summary_results = []

    with zipfile.ZipFile(zip_path, 'r') as zf:
        files = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        files.sort()

        print(f"🚀 BẮT ĐẦU SẢN XUẤT NGHIỆM BIH TỪ FILE ZIP CHO {len(files)} FILE...")
        print("-" * 60)

        for file_name in files:
            file_content = zf.read(file_name).decode("utf-8", errors="replace")
            res = process_instance(file_name, file_content, out_dir, args.seed)
            if res:
                summary_results.append(res)

    if summary_results:
        csv_path = out_dir / "bih_summary.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            fieldnames = ["instance", "algorithm", "feasible", "vehicles", "distance",
                          "travel_time", "served", "runtime_sec", "seed", "bih_first"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(summary_results)
        print("-" * 60)
        print(f"📊 Đã lưu báo cáo CSV tổng hợp tại: {csv_path}")

    print(f"✅ Hoàn tất! Toàn bộ file JSON đã được lưu tại: {out_dir / 'routes'}")