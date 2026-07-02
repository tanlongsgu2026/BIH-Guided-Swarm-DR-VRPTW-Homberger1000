from pathlib import Path
import argparse
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=str(ROOT / "results" / "summary.csv"))
    parser.add_argument("--outdir", default=str(ROOT / "results"))
    args = parser.parse_args()
    df = pd.read_csv(args.csv)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    for metric in ["vehicles", "distance", "travel_time", "runtime_sec"]:
        avg = df.groupby("algorithm", as_index=False)[metric].mean().sort_values(metric)
        plt.figure(figsize=(10, 5))
        plt.bar(avg["algorithm"], avg[metric])
        plt.xticks(rotation=30, ha="right")
        plt.ylabel(metric)
        plt.title(f"Average {metric} by algorithm")
        plt.tight_layout()
        path = outdir / f"avg_{metric}.png"
        plt.savefig(path, dpi=200)
        plt.close()
        print("Saved", path)

if __name__ == "__main__":
    main()
