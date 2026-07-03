from pathlib import Path
import argparse
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    # Trỏ mặc định vào thư mục results thay vì một file cụ thể
    parser.add_argument("--results-dir", default=str(ROOT / "results"))
    parser.add_argument("--outdir", default=str(ROOT / "results" / "plots"))
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    outdir = Path(args.outdir)

    # Tạo thư mục con 'plots' để chứa ảnh, tránh việc ảnh bị trộn lẫn với file csv
    outdir.mkdir(parents=True, exist_ok=True)

    # 1. Quét tìm tất cả các file có đuôi _summary.csv trong thư mục
    csv_files = list(results_dir.glob("*_summary.csv"))

    if not csv_files:
        print(f"Không tìm thấy file *_summary.csv nào trong thư mục {results_dir}")
        return

    # 2. Đọc và gộp tất cả các file CSV lại thành 1 DataFrame duy nhất
    dfs = []
    for file in csv_files:
        print(f"Đang đọc dữ liệu từ: {file.name}")
        try:
            df_temp = pd.read_csv(file)
            dfs.append(df_temp)
        except Exception as e:
            print(f"  -> Lỗi khi đọc file {file.name}: {e}")

    if not dfs:
        print("Không có dữ liệu hợp lệ để vẽ biểu đồ.")
        return

    # Lệnh concat sẽ nối các bảng lại với nhau (theo chiều dọc)
    df = pd.concat(dfs, ignore_index=True)

    # Xóa các dòng trùng lặp (nếu bạn lỡ chạy 1 thuật toán nhiều lần trên cùng 1 instance)
    # Ưu tiên giữ lại kết quả mới nhất (dòng cuối cùng)
    df = df.drop_duplicates(subset=["instance", "algorithm", "seed"], keep="last")

    print(f"\nĐã gộp thành công {len(df)} dòng dữ liệu. Bắt đầu vẽ biểu đồ...")

    # 3. Vẽ biểu đồ
    for metric in ["vehicles", "distance", "travel_time", "runtime_sec"]:
        if metric not in df.columns:
            continue

        avg = df.groupby("algorithm", as_index=False)[metric].mean().sort_values(metric)

        plt.figure(figsize=(10, 5))
        # Có thể tùy chỉnh màu sắc biểu đồ ở đây
        plt.bar(avg["algorithm"], avg[metric], color='skyblue', edgecolor='black')

        plt.xticks(rotation=45, ha="right")
        plt.ylabel(metric)
        plt.title(f"Average {metric} by Algorithm")
        plt.tight_layout()

        path = outdir / f"avg_{metric}.png"
        plt.savefig(path, dpi=200)
        plt.close()
        print("Đã lưu biểu đồ:", path)


if __name__ == "__main__":
    main()