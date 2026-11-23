"""Run or explore the 2015 flight delay and cancellation analysis."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

import pyarrow as pa

from analysis import QUERIES, read_query, run_analysis
from benchmarks import run_benchmarks
from figures import write_figures
from pipeline import CHUNK_SIZE, build
from statistical_analysis import run_statistics

ROOT = Path(__file__).resolve().parent
HANDLED_ERRORS = (
    OSError, ValueError, RuntimeError, AssertionError, sqlite3.Error, pa.ArrowException,
)
MENU_TEXT = """
1. Build the database and Parquet file
2. Analyze and export all SQL results
3. Explore a SQL result
4. Run the benchmarks
5. View the data audit
6. Run regression, correlation and hypothesis tests
0. Exit"""


def positive_integer(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("enter a positive integer")
    return value


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data", help="directory containing the three source CSV files")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "work", help="directory for SQLite, Parquet and the audit")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results", help="directory for result CSVs, figures and benchmarks")
    parser.add_argument("--chunk-size", type=positive_integer, default=CHUNK_SIZE, help="rows per processing chunk (default: %(default)s)")
    parser.add_argument("--repeats", type=positive_integer, default=3, help="benchmark trials per approach (default: %(default)s)")
    parser.add_argument("command", nargs="?", default="menu", choices=("menu", "build", "analyze", "benchmark", "statistics", "all"))
    return parser.parse_args()


def build_data(args):
    audit = build(
        args.data_dir, args.work_dir,
        chunksize=args.chunk_size, on_progress=show_build_progress,
    )
    print(f"Loaded {audit['rows']:,} flights in {audit['chunks']} chunks.")
    print(f"SQLite, Parquet and the full audit are in {args.work_dir.resolve()}.")


def show_build_progress(chunks, rows):
    if chunks == 1 or chunks % 5 == 0:
        print(f"Loaded {rows:,} rows across {chunks} chunks. Validating after ingestion.", flush=True)


def analyze_data(args):
    tables = run_analysis(args.work_dir, args.results_dir)
    write_figures(tables, args.results_dir)
    print(f"Exported {len(tables)} SQL result tables and three Seaborn figures to {args.results_dir.resolve()}.")


def benchmark_data(args):
    run_benchmarks(args.data_dir, args.work_dir, args.results_dir, args.chunk_size, args.repeats)
    print(f"Benchmark and parity results are in {args.results_dir.resolve() / 'benchmarks.json'}.")


def statistical_data(args):
    run_statistics(args.work_dir, args.results_dir)


def show_query(args):
    query_names = list(QUERIES)
    for number, name in enumerate(query_names, start=1):
        print(f"  {number:2}. {QUERIES[name]}")
    answer = input("Query number (0 to return): ").strip()
    try:
        selection = int(answer)
    except ValueError as error:
        raise ValueError(f"Enter a whole number from 0 to {len(query_names)}.") from error
    if selection == 0:
        return
    if not 1 <= selection <= len(query_names):
        raise ValueError(f"Select a query from 1 to {len(query_names)}.")

    query_name = query_names[selection - 1]
    table = read_query(args.work_dir, query_name)
    preview = table.head(15)
    print(preview.to_string(index=False, float_format="{:.3f}".format))
    print(f"Showing {len(preview)} of {len(table)} rows. Use Analyze to export the full result.")


def show_audit(args):
    path = args.work_dir / "audit.json"
    if not path.is_file():
        raise FileNotFoundError(f"Audit missing at {path.resolve()}. Run Build first.")
    audit = json.loads(path.read_text(encoding="utf-8"))
    print(f"{audit['rows']:,} records, {audit['date_min']} to {audit['date_max']}")
    print(json.dumps({"status": audit["status"], "sqlite_checks": audit["sqlite_checks"]}, indent=2))
    print(f"Full audit: {path.resolve()}")


def menu(args):
    print("2015 Flight Delays and Cancellations")
    while True:
        print(MENU_TEXT)
        try:
            choice = input("Choose an operation: ").strip()
            if choice == "0":
                return
            elif choice == "1":
                build_data(args)
            elif choice == "2":
                analyze_data(args)
            elif choice == "3":
                show_query(args)
            elif choice == "4":
                benchmark_data(args)
            elif choice == "5":
                show_audit(args)
            elif choice == "6":
                statistical_data(args)
            else:
                print("Enter a menu number from 0 to 6.")
        except EOFError:
            return
        except HANDLED_ERRORS as error:
            print(f"Operation failed: {error}", file=sys.stderr)


def main():
    args = parse_args()
    actions = {
        "build": build_data,
        "analyze": analyze_data,
        "benchmark": benchmark_data,
        "statistics": statistical_data,
        "menu": menu,
    }
    try:
        if args.command == "all":
            build_data(args)
            analyze_data(args)
            benchmark_data(args)
            statistical_data(args)
        else:
            actions[args.command](args)
    except HANDLED_ERRORS as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
