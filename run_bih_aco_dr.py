from src.experiment import main

if __name__ == "__main__":
    import sys
    if "--algorithms" not in sys.argv:
        sys.argv += ["--algorithms", "BIH-ACO-DR"]
    if "--out" not in sys.argv:
        sys.argv += ["--out", "results/bih_aco_dr_summary.csv"]
    main()
