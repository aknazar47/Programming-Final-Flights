"""Run the project SQL in SQLite and export the results with Pandas."""

from pathlib import Path
import sqlite3

import pandas as pd


SQL_DIR = Path(__file__).resolve().parent / "sql"
QUERIES = {
    "overview": "Yearly flight totals and data coverage",
    "airline_ranking": "Airline ranking by late-arrival rate",
    "airport_ranking": "Origin airport ranking by late-arrival rate",
    "monthly_rates": "Monthly rates and weighted three-month rolling rates",
    "hourly_rates": "Rates by scheduled local departure hour",
    "month_hour": "Month-by-hour rates",
    "cancellation_reasons": "Cancellation reasons by month",
    "monthly_airline_leaders": "Highest late-arrival rate airline in each month",
    "route_rates": "Late-arrival rates on high-volume routes",
    "airport_coverage": "Airport metadata coverage by month",
}


def query_sql(name):
    """Read the numbered SQL file for a result."""
    query_names = list(QUERIES)
    number = query_names.index(name) + 1
    sql_file = SQL_DIR / f"{number:02d}_{name}.sql"
    return sql_file.read_text(encoding="utf-8")


def open_database(work_dir):
    """Open an existing database in read-only mode."""
    database = (Path(work_dir) / "flights.sqlite").resolve()
    if not database.is_file():
        raise FileNotFoundError(f"{database} is missing. Build the dataset first.")
    database_url = database.as_uri() + "?mode=ro"
    return sqlite3.connect(database_url, uri=True)


def read_query(work_dir, name):
    """Execute a single registered query and return its Pandas result."""
    connection = open_database(work_dir)
    try:
        return pd.read_sql_query(query_sql(name), connection)
    finally:
        connection.close()


def run_analysis(work_dir, results_dir):
    """Execute the query suite and export one CSV per query."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    tables = {}
    connection = open_database(work_dir)
    try:
        for name in QUERIES:
            table = pd.read_sql_query(query_sql(name), connection)
            csv_file = results_dir / f"{name}.csv"
            table.to_csv(csv_file, index=False)
            tables[name] = table
    finally:
        connection.close()
    return tables
