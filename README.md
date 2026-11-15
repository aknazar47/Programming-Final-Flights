# Flight Delays and Cancellations

Aknazar Altynbassov, Daniyar Mussin, and Yerzhan Tugralin  
Programming for Data Analysis and Database · Big Data Analysis  
Topic 4 · Cluster 1

The project analyzes arrival delays and cancellations by airline, origin airport, month, and scheduled local departure hour. It processes the full 2015 flight file in Pandas chunks, builds a normalized SQLite database and a compressed Parquet file, and uses SQL window functions to rank airlines and airports. Seaborn visualizes the SQL results.

## Run from a console

Use Python 3.12 (tested with Python 3.12.14). Download [2015 Flight Delays and Cancellations](https://www.kaggle.com/datasets/usdot/flight-delays) and extract `flights.csv`, `airlines.csv`, and `airports.csv` into a `data/` directory next to `main.py`. The uncompressed flights file alone is about 592 MB. Allow about 2 GB of additional free space for the database, Parquet, and temporary files. A rebuild alongside existing outputs needs extra space.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py all
```

On macOS or Linux, use `python3 -m venv .venv` and replace `.\.venv\Scripts\python.exe` with `.venv/bin/python` in the next two commands. If the CSV files are already extracted elsewhere, pass their directory with `--data-dir` before the command. For example, with Python and dependencies available in the current environment:

```powershell
python main.py --data-dir "$env:USERPROFILE\Downloads\archive" all
```

`all` builds the data, exports all SQL results and figures, and runs both comparisons. The build alone took about four minutes in the recorded run. Allow several more minutes for the queries and benchmarks. To repeat only one step, use `build`, `analyze`, or `benchmark`. Run `python main.py` for the interactive console menu. After building, choose **3** to explore a query or **5** to see audit totals. For a machine with less memory, use `--chunk-size 100000`. For a single benchmark trial, use `--repeats 1`. The submitted figures and timings use 200,000 rows per chunk and three benchmark trials.

## Data and outputs

| File or directory | Contents |
| --- | --- |
| `main.py` | Console menu and command-line entry points |
| `pipeline.py` | Chunked ETL, data quality audit, SQLite schema and Parquet writer |
| `analysis.py`, `sql/`, `figures.py` | Ten SQLite queries, Pandas exports and three Seaborn figures |
| `benchmarks.py` | Three processing methods and independent Pandas airline ranking |
| `results/` | Query tables, audit snapshot, benchmark JSON, charts, and ER diagram from the verified run |
| `submission/` | Written report and editable PowerPoint presentation |
| `work/` | Rebuildable `flights.sqlite`, `flights.parquet` and `audit.json` |

For a code walkthrough, start in `main.py` with the menu and follow `build_data()` into `pipeline.py`. Each loop iteration reads one flight chunk, checks and converts its columns, and writes the records. Then open `sql/02_airline_ranking.sql` to see the counts, rates, and `RANK()` in order. In `benchmarks.py`, `pandas_airline_ranking()` follows the same calculation with `groupby()`, `merge()`, and `rank()`. It adds the counts across chunks before calculating each airline’s rates.

The large input and generated database and Parquet files are excluded from version control. `results/audit.json` preserves the submitted run's source SHA-256 fingerprints, data-quality counts, and integrity checks. A new build writes the corresponding audit to `work/audit.json`.

## Definitions and decisions

- **Late arrival rate** is the percentage of noncancelled, nondiverted flights with a recorded arrival delay that arrived at least 15 minutes late. The threshold follows the [U.S. Bureau of Transportation Statistics](https://www.transtats.bts.gov/TableInfo.asp?QO_fu146_anzr=b0-gvzr&V0s1_b0yB=EGJ).
- **Cancellation rate** is cancellations divided by all scheduled flights in the group. Negative delay values represent early operations and are preserved. Missing delays stay missing.
- **Airport ranking** uses origin airport codes and requires at least 10,000 eligible arrivals per code. Numeric airport codes absent from `airports.csv` retain their own key and null metadata. The file shows a code-format break in October, so airport results are by source code and their named-airport coverage varies by month.
- **Time of day** means scheduled departure hour in the origin's local time. A source clock value of `2400` falls into hour `00` on its recorded service date for grouping. The heatmap suppresses cells below 1,000 eligible arrivals. The full results include those cells and counts.
- **Ranks** use descending unrounded late-arrival rates. SQL `RANK` gives ties the same rank with gaps. `ROW_NUMBER` picks one deterministic monthly airline leader among airlines with at least 5,000 eligible arrivals that month. The rolling rates combine numerator and denominator counts over the current and preceding two months, with shorter windows in January and February.

## SQL and benchmarking

SQLite stores one fact row per source record and separates the carrier, airport and cancellation-reason descriptions into keyed lookup tables. The fact table stores the service date, from which SQL derives the calendar group. Origin and destination reference the same airport table independently. See the [3NF ER diagram](results/er_diagram.png).

| Query | What to look for |
| --- | --- |
| 01 Overview | Scheduled, cancelled, diverted, eligible and late flight totals |
| 02 Airline ranking | Carrier join and `RANK` by late-arrival rate |
| 03 Airport ranking | Airport join, `HAVING` volume filter and `RANK` |
| 04 Monthly rates | Monthly rates and denominator-weighted rolling window |
| 05 Hourly rates | Local scheduled departure hour, delay and cancellation rates |
| 06 Month and hour | Two-way aggregation behind the heatmap |
| 07 Cancellation reasons | Monthly cancellation composition with reason lookup |
| 08 Monthly airline leaders | `ROW_NUMBER` partitioned by month |
| 09 Route rates | Origin and destination joins and a minimum-volume filter |
| 10 Airport coverage | Missing airport metadata by month |

The three processing approaches are standard-dtype chunked CSV (baseline), categorical/downcast chunked CSV, and Zstandard Parquet read back with narrow integers and categorical text. All three read all 31 columns. The benchmark records median time to produce the frames, the largest deep DataFrame footprint, file size, exact monthly control counts and matching full-row fingerprints. January through August form the development period and September through December form the chronological validation period. The deterministic transformations require no model fitting or learned parameters. Frame footprints exclude parser buffers, temporary allocations, and other process memory. Timings use the local filesystem without clearing the operating system cache.

The airline ranking is calculated independently with a SQLite query and a chunked Pandas group-by over four Parquet columns. Counts and ranks must match exactly and both rate columns must match within `1e-10` percentage points. Timings start with the stores already built and include reading and computing the rankings. They reflect the storage paths as well as the two engines.

## Demonstrate the project

Build the full data before the defense. In the interactive menu, choose **5** to verify 5,819,079 source records and the SQLite checks. Choose **3**, then query **2** or **3**, to demonstrate a live airline or airport `RANK` query. Use query **4** to explain why the rolling rates sum counts before dividing. The benchmark and three figures can be shown directly from `results/` while the live console remains open.

All three members share responsibility for data preparation, database design, SQL, analysis, benchmarking, and the report and defense. Each member should be ready to explain any part of the program.

## Assignment criteria and evidence

| Requirement | Where to verify it |
| --- | --- |
| Technical 1–4 · Functions, data structures, branching and iteration | `main.py` and the analysis modules use separate functions, lists and dictionaries, `if`/`elif`/`else`, and loops over chunks and menu choices. |
| Technical 5–8 · Files, exceptions, interface and modularity | The interactive menu reads the inputs and writes SQLite, Parquet, CSV, PNG and JSON. It handles invalid input and missing files. `main.py` imports the processing, analysis, plotting and benchmark modules. |
| Technical 9 · Baseline and two approaches | `results/benchmarks.json` records three trials per approach, frame memory, file size and exact monthly controls plus row fingerprints, including the chronological September–December validation period. |
| Technical 10 · Relational database and SQL | `work/flights.sqlite` is generated from the three inputs. The schema diagram and ten SQL queries cover lookup joins, `GROUP BY`, `HAVING`, CTEs, `RANK`, `ROW_NUMBER`, and rolling aggregates. Pandas exports each result. |
| Technical 11 and Cluster 1 · Large data and memory | `results/audit.json` records 5,819,079 input rows, the 200,000-row chunk size, before-and-after dtype memory, null and key checks, and SQLite integrity. `results/benchmarks.json` compares CSV and Parquet size and read time. |
| Cluster 1 · Cross-engine verification and visual analysis | `results/airline_ranking.csv` and `results/airline_ranking_pandas.csv` contain the independently computed rankings. `results/benchmarks.json` records equality and timings. Three Seaborn figures visualize SQL results. |
| Submission files | The source, pinned `requirements.txt`, dataset link, README, written report, and editable PowerPoint are included in the project. The report and presentation state the shared contributions of all three named members. |
