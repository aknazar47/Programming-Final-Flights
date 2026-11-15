"""Compare full-data file reads and independently reproduce the airline ranking."""

import json
import platform
import sqlite3
from contextlib import closing
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from analysis import open_database, query_sql
from pipeline import frame_bytes, optimize_chunk, read_flights

DEVELOPMENT_MONTHS = list(range(1, 9))
HOLDOUT_MONTHS = list(range(9, 13))
RATE_TOLERANCE_PP = 1e-10
# Use unsigned 64-bit sums so fingerprints combine the same way across chunks.
HASH_MODULUS = 2**64
MONTHLY_COUNTS = ["rows", "cancelled", "diverted", "eligible", "late"]
AIRLINE_INPUT = ["AIRLINE", "CANCELLED", "DIVERTED", "ARRIVAL_DELAY"]
COUNT_COLUMNS = ["scheduled_flights", "cancelled_flights", "eligible_arrivals", "delayed_arrivals"]
RATE_COLUMNS = ["late_rate_pct", "cancellation_rate_pct"]
METHODS = {
    "baseline_csv": "CSV with standard Pandas dtypes (baseline)",
    "optimized_csv": "CSV with categorical and downcast dtypes",
    "optimized_parquet": "Optimized Parquet (Zstandard)",
}
PARQUET_DTYPES = {pa.int8(): pd.Int8Dtype(), pa.int16(): pd.Int16Dtype()}


def parquet_chunks(path, chunksize, columns=None):
    with pq.ParquetFile(path) as parquet_file:
        for batch in parquet_file.iter_batches(batch_size=chunksize, columns=columns):
            yield batch.to_pandas(
                types_mapper=PARQUET_DTYPES.get,
                strings_to_categorical=True,
            )


def benchmark_chunks(method, csv_path, parquet_path, chunksize):
    if method == "optimized_parquet":
        for frame in parquet_chunks(parquet_path, chunksize):
            yield frame
        return

    with read_flights(csv_path, chunksize) as reader:
        for frame in reader:
            if method == "optimized_csv":
                frame = optimize_chunk(frame)
            yield frame


def eligible_arrivals(frame):
    operated = (frame["CANCELLED"] == 0) & (frame["DIVERTED"] == 0)
    has_arrival_delay = frame["ARRIVAL_DELAY"].notna()
    return operated & has_arrival_delay


def row_hashes(frame):
    """Put CSV and Parquet values in matching dtypes before hashing each row."""
    columns = {}
    for name in frame.columns:
        column = frame[name]
        if pd.api.types.is_numeric_dtype(column):
            columns[name] = column.astype("float64")
        else:
            columns[name] = column.astype("object")
    comparable = pd.DataFrame(columns)
    return pd.util.hash_pandas_object(comparable, index=False).to_numpy()


def record_quality(frame, monthly):
    """Accumulate monthly counts and fingerprints that ignore row order."""
    hashes = row_hashes(frame)
    eligible = eligible_arrivals(frame)
    metrics = pd.DataFrame({
        "rows": 1,
        "cancelled": frame["CANCELLED"].eq(1),
        "diverted": frame["DIVERTED"].eq(1),
        "eligible": eligible,
        "late": eligible & frame["ARRIVAL_DELAY"].ge(15).fillna(False),
    }, index=frame.index)
    monthly_totals = metrics.groupby(frame["MONTH"]).sum()
    for month, totals in monthly_totals.iterrows():
        month = int(month)
        month_mask = (frame["MONTH"] == month).to_numpy(dtype=bool)
        month_hashes = hashes[month_mask]
        if month not in monthly:
            monthly[month] = dict.fromkeys(MONTHLY_COUNTS + ["hash_sum", "hash_xor"], 0)
        summary = monthly[month]
        for name in MONTHLY_COUNTS:
            summary[name] += int(totals[name])

        # Sum and XOR let us combine row hashes without storing past chunks.
        chunk_sum = int(month_hashes.sum(dtype="uint64"))
        chunk_xor = int(np.bitwise_xor.reduce(month_hashes, initial=np.uint64(0)))
        summary["hash_sum"] = (summary["hash_sum"] + chunk_sum) % HASH_MODULUS
        summary["hash_xor"] ^= chunk_xor


def time_file_read(method, csv_path, parquet_path, chunksize, validate):
    elapsed = 0.0
    peak_frame = 0
    rows = 0
    monthly = {}
    chunks = benchmark_chunks(method, csv_path, parquet_path, chunksize)
    with closing(chunks):
        while True:
            # Time reading and dtype conversion. Check quality after the timer stops.
            start = perf_counter()
            frame = next(chunks, None)
            elapsed += perf_counter() - start
            if frame is None:
                break
            rows += len(frame)
            peak_frame = max(peak_frame, frame_bytes(frame))
            if validate:
                record_quality(frame, monthly)
            del frame
    return elapsed, peak_frame, rows, monthly


def check_monthly_quality(method, baseline, current):
    if baseline.keys() != current.keys():
        raise ValueError(f"{method} has different months from the CSV baseline")
    for month, expected in baseline.items():
        observed = current[month]
        for name in MONTHLY_COUNTS:
            if observed[name] != expected[name]:
                raise ValueError(f"{method} has a different {name} count for month {month}")
        if observed["hash_sum"] != expected["hash_sum"] or observed["hash_xor"] != expected["hash_xor"]:
            raise ValueError(f"{method} has different row fingerprints for month {month}")


def compare_formats(data_dir, work_dir, chunksize, repeats):
    csv_path = Path(data_dir) / "flights.csv"
    parquet_path = Path(work_dir) / "flights.parquet"
    method_ids = list(METHODS)
    records = {method: {"trials_seconds": [], "max_frame_bytes": 0} for method in method_ids}
    quality = {}
    for trial in range(repeats):
        # Rotate the order so each approach can run first in a three-trial run.
        offset = trial % len(method_ids)
        trial_order = method_ids[offset:] + method_ids[:offset]
        for method in trial_order:
            elapsed, peak, rows, monthly = time_file_read(
                method, csv_path, parquet_path, chunksize, validate=trial == 0
            )
            record = records[method]
            record["trials_seconds"].append(elapsed)
            record["max_frame_bytes"] = max(record["max_frame_bytes"], peak)
            if trial == 0:
                quality[method] = monthly
                record["rows"] = rows
            elif record["rows"] != rows:
                raise ValueError(f"Row count changed between {method} benchmark trials")
            print(f"Format trial {trial + 1}/{repeats} · {method}: {elapsed:.2f} s", flush=True)

    reference = quality["baseline_csv"]
    development = [month for month in DEVELOPMENT_MONTHS if month in reference]
    holdout = [month for month in HOLDOUT_MONTHS if month in reference]
    result = []
    for method, record in records.items():
        check_monthly_quality(method, reference, quality[method])
        input_path = csv_path
        if method == "optimized_parquet":
            input_path = parquet_path

        # Passing the check above means every observed month matched.
        result.append({
            "id": method,
            "label": METHODS[method],
            "file_bytes": input_path.stat().st_size,
            "median_seconds": median(record["trials_seconds"]),
            "monthly_aggregate_match": True,
            "row_fingerprints_match": True,
            "development_match": bool(development),
            "holdout_match": bool(holdout),
            "trials_seconds": record["trials_seconds"],
            "max_frame_bytes": record["max_frame_bytes"],
            "rows": record["rows"],
        })
    return {
        "methods": result,
        "development_months": development,
        "holdout_months": holdout,
        "holdout_rows": sum(reference[m]["rows"] for m in holdout),
        "reference_monthly_controls": reference,
    }


def pandas_airline_ranking(parquet_path, airline_csv, chunksize):
    lookup = pd.read_csv(airline_csv)
    lookup = lookup.rename(columns={"IATA_CODE": "airline_code", "AIRLINE": "airline_name"})
    chunk_totals = []
    for frame in parquet_chunks(parquet_path, chunksize, columns=AIRLINE_INPUT):
        eligible = eligible_arrivals(frame)
        counts = pd.DataFrame({
            "airline_code": frame["AIRLINE"].astype("object"),
            "scheduled_flights": 1,
            "cancelled_flights": frame["CANCELLED"].eq(1),
            "eligible_arrivals": eligible,
            "delayed_arrivals": eligible & frame["ARRIVAL_DELAY"].ge(15).fillna(False),
        })
        airline_totals = counts.groupby("airline_code", sort=False)[COUNT_COLUMNS].sum()
        chunk_totals.append(airline_totals)

    # Add the counts across chunks before computing each airline's percentages.
    combined = pd.concat(chunk_totals)
    result = combined.groupby(level="airline_code").sum().reset_index()
    result = result.merge(lookup, on="airline_code", how="left", validate="one_to_one")
    eligible_count = result["eligible_arrivals"].replace(0, np.nan)
    result["late_rate_pct"] = 100.0 * result["delayed_arrivals"] / eligible_count
    result["cancellation_rate_pct"] = 100.0 * result["cancelled_flights"] / result["scheduled_flights"]
    # Pandas' min method gives the same tied ranks and gaps as SQL RANK().
    result["delay_rank"] = result["late_rate_pct"].rank(method="min", ascending=False)
    columns = ["airline_code", "airline_name", *COUNT_COLUMNS, *RATE_COLUMNS, "delay_rank"]
    result = result.sort_values(["delay_rank", "airline_code"])
    return result[columns].reset_index(drop=True)


def check_airline_rankings(sql_result, pandas_result):
    exact_columns = ["airline_code", "airline_name", *COUNT_COLUMNS, "delay_rank"]
    pd.testing.assert_frame_equal(
        sql_result[exact_columns], pandas_result[exact_columns],
        check_dtype=False, check_exact=True,
    )
    sql_rates = sql_result[RATE_COLUMNS].to_numpy(dtype=float, na_value=np.nan)
    pandas_rates = pandas_result[RATE_COLUMNS].to_numpy(dtype=float, na_value=np.nan)
    np.testing.assert_allclose(sql_rates, pandas_rates, atol=RATE_TOLERANCE_PP, rtol=0, equal_nan=True)


def compare_airline_engines(data_dir, work_dir, results_dir, chunksize, repeats):
    work_dir = Path(work_dir)
    airline_csv = Path(data_dir) / "airlines.csv"
    parquet_path = work_dir / "flights.parquet"
    sql_times = []
    pandas_times = []
    sql = query_sql("airline_ranking")
    for trial in range(repeats):
        with closing(open_database(work_dir)) as connection:
            if trial % 2 == 0:
                order = ("sql", "pandas")
            else:
                order = ("pandas", "sql")
            for engine in order:
                start = perf_counter()
                if engine == "sql":
                    sql_result = pd.read_sql_query(sql, connection)
                    sql_times.append(perf_counter() - start)
                else:
                    pandas_result = pandas_airline_ranking(parquet_path, airline_csv, chunksize)
                    pandas_times.append(perf_counter() - start)
        check_airline_rankings(sql_result, pandas_result)
        print(f"Engine trial {trial + 1}/{repeats} · SQL {sql_times[-1]:.2f} s · Pandas {pandas_times[-1]:.2f} s", flush=True)

    diff = (sql_result[RATE_COLUMNS] - pandas_result[RATE_COLUMNS]).abs().stack()
    pandas_result.to_csv(Path(results_dir) / "airline_ranking_pandas.csv", index=False)
    return {
        "sql_median_seconds": median(sql_times),
        "pandas_median_seconds": median(pandas_times),
        "sql_trials_seconds": sql_times,
        "pandas_trials_seconds": pandas_times,
        "group_count": len(sql_result),
        "counts_and_ranks_match": True,
        "rates_match": True,
        "max_rate_diff_pp": float(diff.max()) if not diff.empty else 0.0,
        "tolerance_pp": RATE_TOLERANCE_PP,
    }


def run_benchmarks(data_dir, work_dir, results_dir, chunksize=200_000, repeats=3):
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    results = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pandas": pd.__version__,
            "pyarrow": pa.__version__,
            "sqlite": sqlite3.sqlite_version,
        },
        "chunk_size": chunksize,
        "repeats": repeats,
        "formats": compare_formats(data_dir, work_dir, chunksize, repeats),
        "airline_engines": compare_airline_engines(data_dir, work_dir, results_dir, chunksize, repeats),
    }
    (results_dir / "benchmarks.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results
