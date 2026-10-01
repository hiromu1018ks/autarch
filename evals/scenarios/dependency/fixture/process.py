"""Turn the weekly CSV export into a summary report (stdlib only today)."""

import csv


def summarize(rows):
    return sum(1 for _ in rows)


if __name__ == "__main__":
    with open("export.csv", newline="") as handle:
        print("rows:", summarize(csv.reader(handle)))
