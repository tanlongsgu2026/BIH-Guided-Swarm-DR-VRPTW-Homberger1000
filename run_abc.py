from src.experiment import main

if __name__ == "__main__":
    import sys
    if "--algorithms" not in sys.argv:
        sys.argv += ["--algorithms", "ABC"]
    if "--out" not in sys.argv:
        sys.argv += ["--out", "results/abc_summary.csv"]
    main()
