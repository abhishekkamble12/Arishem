"""
Print one Markdown row per concurrency level from Locust's CSVs.

    python loadtest/summarize.py baseline [threaded ...]
"""

import csv
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def rows(label: str):
    for path in glob.glob(os.path.join(HERE, "results", f"{label}_u*_stats.csv")):
        users = int(re.search(r"_u(\d+)_stats\.csv$", path).group(1))
        with open(path, newline="", encoding="utf-8") as fh:
            stats = next(r for r in csv.DictReader(fh) if r["Name"] == "POST /app/ai/query")
        yield users, stats


def main(labels):
    print("| Run | Users | Requests | Failures | Req/s | p50 ms | p95 ms | p99 ms |")
    print("|---|---|---|---|---|---|---|---|")
    for label in labels:
        for users, s in sorted(rows(label)):
            print(f"| {label} | {users} | {s['Request Count']} | {s['Failure Count']} | "
                  f"{float(s['Requests/s']):.2f} | {s['50%']} | {s['95%']} | {s['99%']} |")


if __name__ == "__main__":
    main(sys.argv[1:] or ["baseline"])
