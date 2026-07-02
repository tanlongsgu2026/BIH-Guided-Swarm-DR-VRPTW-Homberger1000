from src.experiment import main

if __name__ == "__main__":
    import sys
    if "--algorithms" not in sys.argv:
        sys.argv += ["--algorithms", "BIH-GWO-DR"]
    if "--out" not in sys.argv:
        sys.argv += ["--out", "results/bih_gwo_dr_summary.csv"]
    main()
