# BIH-Guided Swarm Optimization with Destroy-and-Repair for Homberger1000 VRPTW

Dự án thực nghiệm VRPTW trên bộ dữ liệu `homberger_1000_customer_instances.zip`.
Bản này dùng để chạy riêng từng thuật toán, vì vậy **không có `run_all.py`**.

## 1. Chính sách bắt buộc: BIH-first

Tất cả các file chạy đều tuân theo nguyên tắc **BIH chạy trước**.

```text
Đọc instance Homberger1000
        ↓
Chạy BIH trước để tạo nghiệm nền khả thi
        ↓
Lưu kết quả BIH vào file CSV
        ↓
Đưa nghiệm BIH cho thuật toán được chọn
        ↓
ACO / GWO / ABC / BIH-ACO-DR / BIH-GWO-DR / BIH-ABC-DR cải tiến từ nghiệm BIH
        ↓
Kiểm tra nghiệm khả thi
        ↓
Xuất kết quả ra thư mục results/
```

Nghĩa là ACO, GWO, ABC và các biến thể Destroy-and-Repair **không xây nghiệm từ đầu**. Chúng luôn nhận nghiệm BIH làm nghiệm khởi tạo bắt buộc.


## 2. Cấu hình chính thức để lấy kết quả

Bản này đã chỉnh theo cấu hình thực nghiệm chính thức:

```text
ACO cơ bản: 20 ants
GWO cơ bản: 20 wolves
ABC cơ bản: 20 bees
BIH-ACO-DR: 10 ants trong mỗi lần repair
BIH-GWO-DR: 10 wolves trong mỗi lần repair
BIH-ABC-DR: 10 bees trong mỗi lần repair
Runtime mặc định/BT: 90 giây/instance/thuật toán
Seed mặc định khuyến nghị: 2026
```

Có thể dùng `--runtime-limit 30` hoặc `--runtime-limit 60` để chạy thử nhanh. Theo cấu hình BT của đề tài, giữ `--runtime-limit 90`.

## 3. Thứ tự chạy các file

### Bước 1: Cài thư viện

Chỉ cần làm một lần sau khi giải nén dự án:

```powershell
python -m pip install -r requirements.txt
```

### Bước 2: Chạy BIH nền

Nên chạy file này trước để có mốc so sánh chính:

```powershell
python run_bih.py --seed 2026
```

Kết quả xuất ra:

```text
results/bih_summary.csv
```

Lưu ý: `run_bih.py` chỉ chạy BIH. File này dùng để lấy nghiệm nền và kiểm tra bộ dữ liệu đọc đúng chưa.

### Bước 3: Chạy các thuật toán bầy đàn cơ bản

Sau khi đã kiểm tra BIH chạy ổn, có thể chạy từng thuật toán cơ bản:

```powershell
python run_standard_aco.py --runtime-limit 90 --seed 2026
python run_gwo.py --runtime-limit 90 --seed 2026
python run_abc.py --runtime-limit 90 --seed 2026
```

Kết quả xuất ra:

```text
results/aco_summary.csv
results/gwo_summary.csv
results/abc_summary.csv
```

Quan trọng: Dù chạy `run_standard_aco.py`, `run_gwo.py` hay `run_abc.py`, chương trình vẫn tự động chạy BIH trước bên trong. Vì vậy mỗi file kết quả sẽ có ít nhất 2 nhóm dòng:

```text
BIH
ACO hoặc GWO hoặc ABC
```

### Bước 4: Chạy các thuật toán cải tiến Destroy-and-Repair

Đây là các chương trình chính theo hướng cải tiến:

```powershell
python run_bih_aco_dr.py --runtime-limit 90 --seed 2026
python run_bih_gwo_dr.py --runtime-limit 90 --seed 2026
python run_bih_abc_dr.py --runtime-limit 90 --seed 2026
```

Kết quả xuất ra:

```text
results/bih_aco_dr_summary.csv
results/bih_gwo_dr_summary.csv
results/bih_abc_dr_summary.csv
```

Mỗi chương trình cải tiến chạy theo thứ tự bên trong như sau:

```text
BIH chạy trước
        ↓
Tính điểm tuyến yếu
        ↓
Destroy: phá một phần tuyến yếu hoặc khách hàng khó chèn
        ↓
Repair bằng ACO/GWO/ABC
        ↓
Regret-2 insertion
        ↓
Local search
        ↓
Route elimination
        ↓
Nhận nghiệm mới nếu tốt hơn theo thứ tự: số xe → quãng đường → thời gian
```

## 4. Ý nghĩa từng file chạy

| File | Thứ tự xử lý bên trong | File kết quả |
|---|---|---|
| `run_bih.py` | BIH | `results/bih_summary.csv` |
| `run_standard_aco.py` | BIH → ACO cải tiến từ BIH | `results/aco_summary.csv` |
| `run_gwo.py` | BIH → GWO cải tiến từ BIH | `results/gwo_summary.csv` |
| `run_abc.py` | BIH → ABC cải tiến từ BIH | `results/abc_summary.csv` |
| `run_bih_aco_dr.py` | BIH → Destroy-and-Repair bằng ACO → Local Search | `results/bih_aco_dr_summary.csv` |
| `run_bih_gwo_dr.py` | BIH → Destroy-and-Repair bằng GWO → Local Search | `results/bih_gwo_dr_summary.csv` |
| `run_bih_abc_dr.py` | BIH → Destroy-and-Repair bằng ABC → Local Search | `results/bih_abc_dr_summary.csv` |

## 5. Chạy thử nhanh trước khi chạy toàn bộ

Nên chạy thử 1 instance trước:

```powershell
python run_bih_aco_dr.py --max-instances 1 --runtime-limit 10 --seed 2026
```

Nếu chạy đúng, màn hình sẽ hiện dạng:

```text
[1/1] C1_10_1
  Running mandatory BIH baseline first...
  {'instance': 'C1_10_1', 'algorithm': 'BIH', ...}
  {'instance': 'C1_10_1', 'algorithm': 'BIH-ACO-DR', ...}
Saved summary: results/bih_aco_dr_summary.csv
```

## 6. Chạy toàn bộ 60 instance

Mặc định, nếu không dùng `--max-instances`, chương trình sẽ đọc toàn bộ instance trong file:

```text
data/homberger_1000_customer_instances.zip
```

Bộ dữ liệu Homberger1000 hiện có 60 instance.

Ví dụ chạy toàn bộ BIH-ACO-DR:

```powershell
python run_bih_aco_dr.py --runtime-limit 90 --seed 2026 --save-routes
```

Ví dụ chạy toàn bộ BIH-GWO-DR:

```powershell
python run_bih_gwo_dr.py --runtime-limit 90 --seed 2026 --save-routes
```

Ví dụ chạy toàn bộ BIH-ABC-DR:

```powershell
python run_bih_abc_dr.py --runtime-limit 90 --seed 2026 --save-routes
```

## 7. Chạy theo nhóm instance

Có thể dùng `--pattern` để chạy riêng từng nhóm:

```powershell
python run_bih_aco_dr.py --pattern C1 --runtime-limit 90 --seed 2026 --out results/bih_aco_dr_C1.csv
python run_bih_aco_dr.py --pattern C2 --runtime-limit 90 --seed 2026 --out results/bih_aco_dr_C2.csv
python run_bih_aco_dr.py --pattern R1 --runtime-limit 90 --seed 2026 --out results/bih_aco_dr_R1.csv
python run_bih_aco_dr.py --pattern R2 --runtime-limit 90 --seed 2026 --out results/bih_aco_dr_R2.csv
python run_bih_aco_dr.py --pattern RC1 --runtime-limit 90 --seed 2026 --out results/bih_aco_dr_RC1.csv
python run_bih_aco_dr.py --pattern RC2 --runtime-limit 90 --seed 2026 --out results/bih_aco_dr_RC2.csv
```

Có thể thay `run_bih_aco_dr.py` bằng `run_bih_gwo_dr.py` hoặc `run_bih_abc_dr.py` nếu muốn chạy GWO-DR hoặc ABC-DR.

## 8. Vẽ biểu đồ sau khi có kết quả

Sau khi các file CSV đã được tạo trong thư mục `results/`, chạy:

```powershell
python plot_results.py
```

Biểu đồ sẽ được lưu trong thư mục `results/plots/`.

## 9. Cấu trúc thư mục

```text
BIH-Guided-Swarm-DR-VRPTW-Homberger1000/
├── data/
│   └── homberger_1000_customer_instances.zip
├── src/
│   ├── vrptw_core.py
│   ├── bih.py
│   ├── standard_swarm.py
│   ├── destroy_repair.py
│   └── experiment.py
├── results/
├── run_bih.py
├── run_standard_aco.py
├── run_gwo.py
├── run_abc.py
├── run_bih_aco_dr.py
├── run_bih_gwo_dr.py
├── run_bih_abc_dr.py
├── plot_results.py
├── requirements.txt
└── README.md
```

## 9. Lưu ý khi đẩy lên GitHub

Dự án này không có `run_all.py` để tránh chạy nhầm toàn bộ thí nghiệm trên một máy.

Lệnh đẩy lên GitHub:

```powershell
git init
git add .
git commit -m "Initial BIH-guided swarm DR experiments"
git branch -M main
git remote add origin https://github.com/<USER>/<REPO>.git
git push -u origin main
```
