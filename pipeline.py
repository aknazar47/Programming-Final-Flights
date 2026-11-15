"""Chunked ingestion and data quality audit for the 2015 flight records."""

from collections import Counter
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


INPUT_NAMES = ("flights.csv", "airlines.csv", "airports.csv")
CHUNK_SIZE = 200_000
SOURCE_COLUMNS = (
    "YEAR", "MONTH", "DAY", "DAY_OF_WEEK", "AIRLINE", "FLIGHT_NUMBER",
    "TAIL_NUMBER", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT",
    "SCHEDULED_DEPARTURE", "DEPARTURE_TIME", "DEPARTURE_DELAY", "TAXI_OUT",
    "WHEELS_OFF", "SCHEDULED_TIME", "ELAPSED_TIME", "AIR_TIME", "DISTANCE",
    "WHEELS_ON", "TAXI_IN", "SCHEDULED_ARRIVAL", "ARRIVAL_TIME",
    "ARRIVAL_DELAY", "DIVERTED", "CANCELLED", "CANCELLATION_REASON",
    "AIR_SYSTEM_DELAY", "SECURITY_DELAY", "AIRLINE_DELAY",
    "LATE_AIRCRAFT_DELAY", "WEATHER_DELAY",
)
TEXT_COLUMNS = (
    "AIRLINE", "TAIL_NUMBER", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT",
    "CANCELLATION_REASON",
)
SMALL_INTEGER_COLUMNS = ("MONTH", "DAY", "DAY_OF_WEEK", "DIVERTED", "CANCELLED")
NUMERIC_COLUMNS = [name for name in SOURCE_COLUMNS if name not in TEXT_COLUMNS]
TIME_COLUMNS = (
    "SCHEDULED_DEPARTURE", "DEPARTURE_TIME", "WHEELS_OFF", "WHEELS_ON",
    "SCHEDULED_ARRIVAL", "ARRIVAL_TIME",
)
FLIGHT_COLUMN_NAMES = {
    "AIRLINE": "airline_code",
    "ORIGIN_AIRPORT": "origin_code",
    "DESTINATION_AIRPORT": "destination_code",
    "CANCELLATION_REASON": "cancellation_reason_code",
}
FLIGHT_SOURCE_COLUMNS = SOURCE_COLUMNS[4:]
CANCELLATION_REASONS = (
    ("A", "Air carrier"), ("B", "Weather"),
    ("C", "National Air System"), ("D", "Security"),
)


def parquet_schema():
    """Use the same column types in every Parquet chunk."""
    fields = []
    for name in SOURCE_COLUMNS:
        if name in TEXT_COLUMNS:
            dtype = pa.string()
        elif name in SMALL_INTEGER_COLUMNS:
            dtype = pa.int8()
        else:
            dtype = pa.int16()
        fields.append((name, dtype))
    return pa.schema(fields)


PARQUET_SCHEMA = parquet_schema()


def read_flights(csv_path, chunksize=CHUNK_SIZE):
    """Use inferred numeric dtypes and preserve identifiers such as 10135."""
    return pd.read_csv(
        csv_path,
        chunksize=chunksize,
        dtype=dict.fromkeys(TEXT_COLUMNS, "object"),
        keep_default_na=False,
        na_values=[""],
    )


def frame_bytes(frame):
    """Return the deep memory footprint of this DataFrame in bytes."""
    return int(frame.memory_usage(index=True, deep=True).sum())


def optimize_chunk(frame):
    """Downcast the integral flight fields and encode repeated text as categories."""
    optimized = {}
    for name in SOURCE_COLUMNS:
        column = frame[name]
        if name in TEXT_COLUMNS:
            optimized[name] = column.astype("category")
        else:
            values = pd.to_numeric(column, errors="raise")
            dtype = "Int8" if name in SMALL_INTEGER_COLUMNS else "Int16"
            bounds = np.iinfo(dtype.lower())
            if values.min() < bounds.min or values.max() > bounds.max:
                raise ValueError(f"{name} exceeds the range of {dtype}.")
            # Nullable integer conversion rejects fractions and keeps missing values.
            optimized[name] = values.astype(dtype)
    return pd.DataFrame(optimized, index=frame.index)


def flight_dates(frame):
    """Construct ISO dates and validate the weekday before dropping date parts."""
    dates = pd.to_datetime(
        {"year": frame["YEAR"], "month": frame["MONTH"], "day": frame["DAY"]},
        errors="raise",
    )
    source_weekday = frame["DAY_OF_WEEK"]
    correct_weekday = source_weekday.eq(dates.dt.dayofweek + 1).fillna(False)
    if dates.isna().any() or not correct_weekday.all():
        raise ValueError("Missing date or inconsistent source day of week.")
    return dates.dt.strftime("%Y-%m-%d")


def dimension_records(path, required):
    """Validate code uniqueness and convert CSV missing values to SQL NULL."""
    frame = pd.read_csv(path, dtype={"IATA_CODE": "object"})
    frame = frame.loc[:, required]
    keys = frame["IATA_CODE"]
    if keys.isna().any() or keys.duplicated().any():
        raise ValueError(f"Missing or repeated lookup codes in {path.name}.")
    records = frame.astype(object).where(frame.notna(), None)
    return set(keys), list(records.itertuples(index=False, name=None))


def create_database(connection, data_dir):
    """Create four 3NF tables with foreign keys and load the supplied lookups."""
    connection.executescript("""
        PRAGMA foreign_keys = ON;
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        PRAGMA temp_store = FILE;
        PRAGMA cache_size = -32768;

        CREATE TABLE airline (
            airline_code TEXT PRIMARY KEY,
            airline_name TEXT
        ) WITHOUT ROWID;

        CREATE TABLE airport (
            airport_code TEXT PRIMARY KEY,
            airport_name TEXT,
            city TEXT,
            state TEXT,
            country TEXT,
            latitude REAL,
            longitude REAL
        ) WITHOUT ROWID;

        CREATE TABLE cancellation_reason (
            reason_code TEXT PRIMARY KEY,
            reason_name TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE flight (
            flight_id INTEGER PRIMARY KEY,
            flight_date TEXT NOT NULL,
            airline_code TEXT NOT NULL REFERENCES airline(airline_code),
            flight_number INTEGER NOT NULL,
            tail_number TEXT,
            origin_code TEXT NOT NULL REFERENCES airport(airport_code),
            destination_code TEXT NOT NULL REFERENCES airport(airport_code),
            scheduled_departure INTEGER,
            departure_time INTEGER,
            departure_delay INTEGER,
            taxi_out INTEGER,
            wheels_off INTEGER,
            scheduled_time INTEGER,
            elapsed_time INTEGER,
            air_time INTEGER,
            distance INTEGER,
            wheels_on INTEGER,
            taxi_in INTEGER,
            scheduled_arrival INTEGER,
            arrival_time INTEGER,
            arrival_delay INTEGER,
            diverted INTEGER NOT NULL CHECK (diverted IN (0, 1)),
            cancelled INTEGER NOT NULL CHECK (cancelled IN (0, 1)),
            cancellation_reason_code TEXT REFERENCES cancellation_reason(reason_code),
            air_system_delay INTEGER,
            security_delay INTEGER,
            airline_delay INTEGER,
            late_aircraft_delay INTEGER,
            weather_delay INTEGER
        );
    """)
    airline_codes, airlines = dimension_records(
        data_dir / "airlines.csv", ["IATA_CODE", "AIRLINE"]
    )
    airport_codes, airports = dimension_records(
        data_dir / "airports.csv",
        ["IATA_CODE", "AIRPORT", "CITY", "STATE", "COUNTRY", "LATITUDE", "LONGITUDE"],
    )
    connection.executemany("INSERT INTO airline VALUES (?, ?)", airlines)
    connection.executemany(
        "INSERT INTO airport VALUES (?, ?, ?, ?, ?, ?, ?)", airports
    )
    connection.executemany(
        "INSERT INTO cancellation_reason VALUES (?, ?)", CANCELLATION_REASONS
    )
    return airline_codes, airport_codes


def insert_flights(connection, frame, dates):
    """Write a normalized fact row per input row, preserving nullable values."""
    fields = ["flight_date"] + [
        FLIGHT_COLUMN_NAMES.get(name, name.lower()) for name in FLIGHT_SOURCE_COLUMNS
    ]
    placeholders = ", ".join("?" for _ in fields)
    statement = f"INSERT INTO flight ({', '.join(fields)}) VALUES ({placeholders})"
    records = frame.loc[:, list(FLIGHT_SOURCE_COLUMNS)].astype(object)
    records = records.where(records.notna(), None)
    records.insert(0, "flight_date", dates)
    connection.executemany(statement, records.itertuples(index=False, name=None))


def parquet_table(frame):
    """Convert a Pandas chunk to the file's column types without its row index."""
    table = pa.Table.from_pandas(frame, schema=PARQUET_SCHEMA, preserve_index=False)
    return table.replace_schema_metadata(None)


def update_counts(frame, dates, audit, known_airports):
    """Accumulate full-data quality, completeness and flight outcome counts."""
    audit["rows"] += len(frame)
    audit["chunks"] += 1
    date_min, date_max = dates.min(), dates.max()
    audit["date_min"] = min(audit["date_min"] or date_min, date_min)
    audit["date_max"] = max(audit["date_max"] or date_max, date_max)
    audit["null_counts"].update(frame.isna().sum().astype(int).to_dict())
    for name in NUMERIC_COLUMNS:
        column = frame[name]
        if column.notna().any():
            low, high = int(column.min()), int(column.max())
            previous = audit["numeric_ranges"].get(name, [low, high])
            audit["numeric_ranges"][name] = [
                min(previous[0], low), max(previous[1], high)
            ]

    cancelled = frame["CANCELLED"].eq(1)
    diverted = frame["DIVERTED"].eq(1)
    completed = frame["CANCELLED"].eq(0) & frame["DIVERTED"].eq(0)
    arrival_delay = frame["ARRIVAL_DELAY"]
    departure_delay = frame["DEPARTURE_DELAY"]
    has_reason = frame["CANCELLATION_REASON"].notna()
    has_arrival_delay = arrival_delay.notna()
    eligible = completed & has_arrival_delay
    audit["status"].update({
        "cancelled": int(cancelled.sum()),
        "diverted": int(diverted.sum()),
        "completed": int(completed.sum()),
        "delay_eligible": int(eligible.sum()),
        "delayed_15": int((eligible & arrival_delay.ge(15)).sum()),
        "departure_delay_observed": int(departure_delay.notna().sum()),
        "negative_arrival_delays": int(arrival_delay.lt(0).sum()),
        "negative_departure_delays": int(departure_delay.lt(0).sum()),
    })
    anomalies = audit["anomalies"]
    anomalies["cancelled_and_diverted"] += int((cancelled & diverted).sum())
    anomalies["completed_missing_arrival_delay"] += int((completed & ~has_arrival_delay).sum())
    anomalies["cancelled_missing_reason"] += int((cancelled & ~has_reason).sum())
    anomalies["noncancelled_with_reason"] += int((~cancelled & has_reason).sum())
    anomalies["cancelled_with_arrival_delay"] += int((cancelled & has_arrival_delay).sum())
    anomalies["diverted_with_arrival_delay"] += int((diverted & has_arrival_delay).sum())
    for name in TIME_COLUMNS:
        hhmm = frame[name]
        is_midnight = hhmm.eq(2400)
        standard = hhmm.between(0, 2359) & hhmm.mod(100).lt(60)
        anomalies["hhmm_2400"][name] += int(is_midnight.sum())
        anomalies["hhmm_invalid_nonnull"][name] += int(
            (hhmm.notna() & ~(standard | is_midnight)).sum()
        )

    airports = audit["airports"]
    origin = frame["ORIGIN_AIRPORT"]
    destination = frame["DESTINATION_AIRPORT"]
    airports["observed_codes"].update(origin.dropna().unique())
    airports["observed_codes"].update(destination.dropna().unique())
    unmatched_origin = origin.notna() & ~origin.isin(known_airports)
    unmatched_destination = destination.notna() & ~destination.isin(known_airports)
    any_unmatched = unmatched_origin | unmatched_destination
    airports["rows_unmatched_origin"] += int(unmatched_origin.sum())
    airports["rows_unmatched_destination"] += int(unmatched_destination.sum())
    airports["rows_any_unmatched"] += int(any_unmatched.sum())
    airports["unmatched_rows_by_month"].update(
        dates[any_unmatched].str[:7].value_counts().astype(int).to_dict()
    )


def validate_database(connection, audit):
    """Reconcile database counts, verify keys and profile repeated flight keys."""
    connection.execute("CREATE INDEX flight_date_idx ON flight (flight_date)")
    connection.commit()
    quick_check = connection.execute("PRAGMA quick_check").fetchall()
    fk_violations = sum(1 for _ in connection.execute("PRAGMA foreign_key_check"))
    rows, cancelled, diverted = connection.execute(
        "SELECT COUNT(*), SUM(cancelled), SUM(diverted) FROM flight"
    ).fetchone()
    source_totals = audit["rows"], audit["status"]["cancelled"], audit["status"]["diverted"]
    if quick_check != [("ok",)] or fk_violations or (rows, cancelled, diverted) != source_totals:
        raise RuntimeError("SQLite validation failed: integrity, keys or totals.")

    # A carrier can reuse a flight number. The route and scheduled local departure
    # are part of this diagnostic key. Preserve source rows even when it repeats.
    duplicates = connection.execute("""
        SELECT COUNT(*), COALESCE(SUM(group_size - 1), 0)
        FROM (
            SELECT COUNT(*) AS group_size
            FROM flight
            GROUP BY flight_date, airline_code, flight_number,
                     origin_code, destination_code, scheduled_departure
            HAVING COUNT(*) > 1
        )
    """).fetchone()
    audit["anomalies"]["repeated_flight_key_groups"] = duplicates[0]
    audit["anomalies"]["rows_beyond_first_per_repeated_key"] = duplicates[1]
    return {
        "quick_check": quick_check[0][0],
        "foreign_key_violations": fk_violations,
        "flight_rows": rows,
        "airline_rows": connection.execute("SELECT COUNT(*) FROM airline").fetchone()[0],
        "airport_rows": connection.execute("SELECT COUNT(*) FROM airport").fetchone()[0],
        "cancellation_reason_rows": connection.execute(
            "SELECT COUNT(*) FROM cancellation_reason"
        ).fetchone()[0],
    }


def source_manifest(data_dir):
    """Record fingerprints so a run can be tied to the exact input files."""
    manifest = {}
    for name in INPUT_NAMES:
        path = data_dir / name
        digest = sha256()
        with path.open("rb") as handle:
            block = handle.read(1024 * 1024)
            while block:
                digest.update(block)
                block = handle.read(1024 * 1024)
        manifest[name] = {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}
    return manifest


def publish_outputs(files, work_dir):
    """Keep the previous artifacts if publishing one of the new files fails."""
    backups = []
    published = []
    try:
        for file in files:
            target = work_dir / file.name
            if target.exists():
                backup = file.with_suffix(file.suffix + ".previous")
                target.replace(backup)
                backups.append((target, backup))
            file.replace(target)
            published.append(target)
    except OSError:
        for target in reversed(published):
            target.unlink()
        for target, backup in reversed(backups):
            backup.replace(target)
        raise


def start_audit(chunksize, manifest):
    """Prepare the counters updated as each chunk is processed."""
    return {
        "rows": 0,
        "columns": len(SOURCE_COLUMNS),
        "chunks": 0,
        "chunk_size": chunksize,
        "date_min": None,
        "date_max": None,
        "null_counts": Counter(),
        "numeric_ranges": {},
        "status": Counter(),
        "airports": {
            "lookup_codes": 0,
            "observed_codes": set(),
            "rows_unmatched_origin": 0,
            "rows_unmatched_destination": 0,
            "rows_any_unmatched": 0,
            "unmatched_rows_by_month": Counter(),
        },
        "anomalies": {
            "cancelled_and_diverted": 0,
            "completed_missing_arrival_delay": 0,
            "cancelled_missing_reason": 0,
            "noncancelled_with_reason": 0,
            "cancelled_with_arrival_delay": 0,
            "diverted_with_arrival_delay": 0,
            "hhmm_2400": Counter(),
            "hhmm_invalid_nonnull": Counter(),
        },
        "sources": manifest,
    }


def load_chunks(data_dir, chunksize, connection, writer, audit, on_progress):
    """Read, optimize, audit and write one chunk at a time."""
    airline_codes, airport_codes = create_database(connection, data_dir)
    airport_audit = audit["airports"]
    airport_audit["lookup_codes"] = len(airport_codes)
    inserted_airports = set(airport_codes)
    raw_bytes = []
    optimized_bytes = []

    with read_flights(data_dir / "flights.csv", chunksize) as reader:
        for raw in reader:
            if tuple(raw.columns) != SOURCE_COLUMNS:
                raise ValueError("flights.csv has an unexpected column layout.")
            if raw.empty:
                continue
            raw_bytes.append(frame_bytes(raw))
            frame = optimize_chunk(raw)
            del raw
            optimized_bytes.append(frame_bytes(frame))
            dates = flight_dates(frame)

            unknown_airlines = set(frame["AIRLINE"].dropna().unique()) - airline_codes
            if unknown_airlines:
                raise ValueError(f"Unrecognized airline codes: {sorted(unknown_airlines)}")
            update_counts(frame, dates, audit, airport_codes)

            # Retain unmatched source codes as airport rows with missing metadata.
            new_codes = sorted(airport_audit["observed_codes"] - inserted_airports)
            connection.executemany(
                "INSERT INTO airport (airport_code) VALUES (?)",
                [(code,) for code in new_codes],
            )
            inserted_airports.update(new_codes)
            writer.write_table(parquet_table(frame))
            insert_flights(connection, frame, dates)
            if on_progress is not None:
                on_progress(audit["chunks"], audit["rows"])

    if audit["rows"] == 0:
        raise ValueError("flights.csv contains no flight records.")
    airport_audit["unmatched_codes"] = sorted(inserted_airports - airport_codes)
    airport_audit["observed_codes"] = len(airport_audit["observed_codes"])
    audit["memory"] = {
        "first_chunk_raw_bytes": raw_bytes[0],
        "first_chunk_optimized_bytes": optimized_bytes[0],
        "max_raw_chunk_bytes": max(raw_bytes),
        "max_optimized_chunk_bytes": max(optimized_bytes),
        "mean_raw_chunk_bytes": round(sum(raw_bytes) / len(raw_bytes)),
        "mean_optimized_chunk_bytes": round(sum(optimized_bytes) / len(optimized_bytes)),
    }


def build(data_dir, work_dir, chunksize=CHUNK_SIZE, on_progress=None):
    """Build and validate the SQLite and Parquet artifacts from all three CSVs."""
    data_dir = Path(data_dir)
    work_dir = Path(work_dir)
    if chunksize < 1:
        raise ValueError("Chunk size must be a positive number of rows.")
    for name in INPUT_NAMES:
        if not (data_dir / name).is_file():
            raise FileNotFoundError(f"Required CSV missing: {data_dir / name}")
    work_dir.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    manifest = source_manifest(data_dir)
    audit = start_audit(chunksize, manifest)

    with TemporaryDirectory(prefix=".build-", dir=work_dir) as staging_path:
        staging = Path(staging_path)
        database = staging / "flights.sqlite"
        parquet = staging / "flights.parquet"
        with (
            closing(sqlite3.connect(database)) as connection,
            pq.ParquetWriter(
                parquet, PARQUET_SCHEMA, compression="zstd", use_dictionary=True
            ) as writer,
        ):
            load_chunks(data_dir, chunksize, connection, writer, audit, on_progress)
            audit["sqlite_checks"] = validate_database(connection, audit)
        parquet_metadata = pq.read_metadata(parquet)
        if parquet_metadata.num_rows != audit["rows"]:
            raise RuntimeError("Parquet row count differs from the source.")

        audit["storage"] = {
            "csv_bytes": manifest["flights.csv"]["bytes"],
            "parquet_bytes": parquet.stat().st_size,
            "sqlite_bytes": database.stat().st_size,
            "parquet_row_groups": parquet_metadata.num_row_groups,
            "parquet_rows": parquet_metadata.num_rows,
        }
        audit["elapsed_seconds"] = perf_counter() - started
        audit_path = staging / "audit.json"
        audit_path.write_text(
            json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        publish_outputs((database, parquet, audit_path), work_dir)
    return audit
