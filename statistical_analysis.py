"""Daily regression, correlation and paired time-of-day tests for flight outcomes."""

from pathlib import Path
from contextlib import closing
import json
import platform

import numpy as np
import pandas as pd
import scipy
from scipy import stats
import statsmodels
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

from analysis import open_database, read_query
from statistical_figures import write_statistical_figures


HAC_LAGS = 7
SENSITIVITY_LAGS = 14
ALPHA = 0.05
BOOTSTRAP_REPEATS = 2000
BLOCK_DAYS = 7
RANDOM_SEED = 2015
COUNT_COLUMNS = ["scheduled_flights", "cancelled_flights", "eligible_arrivals", "delayed_arrivals"]


def read_daily_statistics(work_dir):
    """Aggregate all source flights in SQLite and reconcile the four core totals."""
    sql_path = Path(__file__).resolve().parent / "sql" / "statistics_daily.sql"
    with closing(open_database(work_dir)) as connection:
        daily = pd.read_sql_query(sql_path.read_text(encoding="utf-8"), connection)
    overview = read_query(work_dir, "overview")
    for column in COUNT_COLUMNS:
        if int(daily[column].sum()) != int(overview[column].sum()):
            raise ValueError(f"Statistical daily totals disagree with the overview for {column}.")
    daily["flight_date"] = pd.to_datetime(daily["flight_date"], errors="raise")
    expected_dates = pd.date_range(daily["flight_date"].min(), daily["flight_date"].max())
    if len(daily) < 30 or not daily["flight_date"].equals(pd.Series(expected_dates, name="flight_date")):
        raise ValueError("Statistical inference needs at least 30 consecutive daily records.")
    daily["late_rate_pct"] = 100.0 * daily["delayed_arrivals"] / daily["eligible_arrivals"].replace(0, np.nan)
    daily["cancellation_rate_pct"] = 100.0 * daily["cancelled_flights"] / daily["scheduled_flights"]
    daily["volume_thousands"] = daily["scheduled_flights"] / 1000.0
    daily["month"] = daily["flight_date"].dt.month
    daily["weekday_number"] = daily["flight_date"].dt.dayofweek
    daily["weekday"] = daily["flight_date"].dt.day_name()
    return daily


def correlation_interval(x, y):
    """A reproducible circular seven-day block bootstrap preserves local dependence."""
    rng = np.random.default_rng(RANDOM_SEED)
    n = len(x)
    correlations = []
    for _ in range(BOOTSTRAP_REPEATS):
        starts = rng.integers(0, n, size=(n + BLOCK_DAYS - 1) // BLOCK_DAYS)
        indices = ((starts[:, None] + np.arange(BLOCK_DAYS)) % n).ravel()[:n]
        correlations.append(np.corrcoef(x[indices], y[indices])[0, 1])
    return np.quantile(correlations, [0.025, 0.975])


def daily_regression(daily, name, predictor, outcome):
    """Fit an equal-day OLS line with HAC inference and calendar sensitivity checks."""
    sample = daily.dropna(subset=[predictor, outcome]).copy()
    if len(sample) != len(daily) or sample[predictor].nunique() < 2:
        raise ValueError(f"The {name} model needs a complete, varying daily predictor.")
    design = sm.add_constant(sample[[predictor]], has_constant="add")
    model = sm.OLS(sample[outcome], design)
    fitted = model.fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS, "use_correction": True}, use_t=True)
    sensitivity = model.fit(cov_type="HAC", cov_kwds={"maxlags": SENSITIVITY_LAGS, "use_correction": True}, use_t=True)
    calendar = pd.get_dummies(sample[["month", "weekday_number"]].astype("category"), drop_first=True, dtype=float)
    adjusted_design = sm.add_constant(pd.concat([sample[[predictor]], calendar], axis=1), has_constant="add")
    adjusted = sm.OLS(sample[outcome], adjusted_design).fit(
        cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS, "use_correction": True}, use_t=True,
    )
    x = sample[predictor].to_numpy(dtype=float)
    y = sample[outcome].to_numpy(dtype=float)
    ci = fitted.conf_int().loc[predictor]
    sensitivity_ci = sensitivity.conf_int().loc[predictor]
    adjusted_ci = adjusted.conf_int().loc[predictor]
    correlation_ci = correlation_interval(x, y)
    result = {
        "model": name, "predictor": predictor, "outcome": outcome, "days": len(sample),
        "intercept": float(fitted.params["const"]), "slope": float(fitted.params[predictor]),
        "slope_ci_low": float(ci.iloc[0]), "slope_ci_high": float(ci.iloc[1]),
        "p_value": float(fitted.pvalues[predictor]), "r_squared": float(fitted.rsquared),
        "pearson_r": float(stats.pearsonr(x, y).statistic),
        "spearman_r": float(stats.spearmanr(x, y).statistic),
        "pearson_ci_low": float(correlation_ci[0]), "pearson_ci_high": float(correlation_ci[1]),
        "slope_ci_low_hac14": float(sensitivity_ci.iloc[0]),
        "slope_ci_high_hac14": float(sensitivity_ci.iloc[1]),
        "calendar_adjusted_slope": float(adjusted.params[predictor]),
        "calendar_adjusted_ci_low": float(adjusted_ci.iloc[0]),
        "calendar_adjusted_ci_high": float(adjusted_ci.iloc[1]),
        "calendar_adjusted_r_squared": float(adjusted.rsquared),
        "residual_lag1_correlation": float(pd.Series(fitted.resid).autocorr(lag=1)),
    }
    grid = pd.DataFrame({predictor: np.linspace(x.min(), x.max(), 100)})
    prediction = fitted.get_prediction(sm.add_constant(grid, has_constant="add")).summary_frame(alpha=ALPHA)
    lines = pd.DataFrame({
        "model": name, "x": grid[predictor], "predicted": prediction["mean"],
        "ci_low": prediction["mean_ci_lower"], "ci_high": prediction["mean_ci_upper"],
    })
    return result, lines


def paired_time_tests(daily):
    """Two-sided tests of equal-day evening-minus-morning rate differences."""
    results = []
    for name, numerator, denominator in (
        ("late_arrival", "late", "eligible"),
        ("cancellation", "cancelled", "scheduled"),
    ):
        morning = 100.0 * daily[f"morning_{numerator}"] / daily[f"morning_{denominator}"].replace(0, np.nan)
        evening = 100.0 * daily[f"evening_{numerator}"] / daily[f"evening_{denominator}"].replace(0, np.nan)
        difference = evening - morning
        if difference.isna().any():
            raise ValueError(f"Every day must have morning and evening observations for {name}.")
        model = sm.OLS(difference.to_numpy(), np.ones((len(difference), 1)))
        fitted = model.fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS, "use_correction": True}, use_t=True)
        sensitivity = model.fit(cov_type="HAC", cov_kwds={"maxlags": SENSITIVITY_LAGS, "use_correction": True}, use_t=True)
        ci = fitted.conf_int()[0]
        ci14 = sensitivity.conf_int()[0]
        results.append({
            "test": name, "days": len(difference), "morning_mean_pct": float(morning.mean()),
            "evening_mean_pct": float(evening.mean()), "effect_pp": float(fitted.params[0]),
            "ci_low": float(ci[0]), "ci_high": float(ci[1]), "p_value": float(fitted.pvalues[0]),
            "ci_low_hac14": float(ci14[0]), "ci_high_hac14": float(ci14[1]),
            "morning_pooled_pct": float(100.0 * daily[f"morning_{numerator}"].sum() / daily[f"morning_{denominator}"].sum()),
            "evening_pooled_pct": float(100.0 * daily[f"evening_{numerator}"].sum() / daily[f"evening_{denominator}"].sum()),
        })
    return pd.DataFrame(results)


def write_statistical_report(daily, regressions, tests, results_dir):
    """Write the results in language suitable for the project defense."""
    lines = [
        "# Statistical analysis of flight delays and cancellations", "",
        f"The analysis covers {int(daily['scheduled_flights'].sum()):,} scheduled flights across {len(daily)} consecutive dates.",
        "The statistical unit is one recorded service date. Every date has equal weight in the regression and paired tests.", "",
        "## Methods and assumptions", "",
        "The two regressions examine daily mean departure versus arrival delay and daily scheduled volume versus late-arrival percentage. Departure and arrival means use the same completed, nondiverted flights with both delays recorded. Negative delay minutes are retained.",
        "Regression lines use ordinary least squares. Standard errors, two-sided tests and 95% pointwise confidence intervals use heteroskedasticity and autocorrelation consistent (HAC) covariance with 7 daily lags. CSV outputs include a 14-lag sensitivity check and month/weekday-adjusted regression coefficients.",
        "Morning means scheduled local departures from 05:00 through 11:59. Evening means 17:00 through 23:59. Each date contributes its evening-minus-morning percentage-point difference. The hypotheses test whether the average daily difference is zero.",
        "The four primary null hypotheses specify zero slope for each regression and zero mean difference for each of the two time-of-day comparisons. Holm correction controls their familywise error rate at 0.05. Reported 95% intervals are individual intervals, so significance decisions use the Holm-adjusted p-values.",
        "Pearson r describes linear correlation and Spearman rho describes rank association. Pearson confidence intervals use a circular 7-day moving-block bootstrap with 2,000 draws and seed 2015. Correlation p-values are omitted because independent-day assumptions would be inappropriate. Regression slope tests use HAC inference.", "",
        "## Regression and correlation results", "",
    ]
    for row in regressions.itertuples():
        units = "daily mean arrival-delay minutes per minute of daily mean departure delay"
        if row.model == "volume_late":
            units = "late-arrival percentage points per 1,000 scheduled flights"
        lines.extend([
            f"### {row.model.replace('_', ' ').title()}", "",
            f"Slope {row.slope:.3f} {units}, with 95% HAC interval [{row.slope_ci_low:.3f}, {row.slope_ci_high:.3f}]. R-squared {row.r_squared:.3f}. Raw p {row.p_value:.3g}, Holm-adjusted p {row.p_holm:.3g}.",
            f"Pearson r {row.pearson_r:.3f} with block-bootstrap interval [{row.pearson_ci_low:.3f}, {row.pearson_ci_high:.3f}]. Spearman rho {row.spearman_r:.3f}.",
            f"After adjustment for month and weekday, the slope is {row.calendar_adjusted_slope:.3f}, with HAC interval [{row.calendar_adjusted_ci_low:.3f}, {row.calendar_adjusted_ci_high:.3f}]. This sensitivity model is observational and can still reflect unmeasured route, carrier, or weather differences.", "",
        ])
        lines.extend([
            f"The fitted line accounts for {100.0 * row.r_squared:.1f}% of the variation in the daily outcome in this dataset. This is an in-sample description of daily aggregates.", "",
        ])
    lines.extend(["## Morning and evening hypothesis tests", ""])
    for row in tests.itertuples():
        decision = "The zero-difference hypothesis is rejected after Holm correction."
        if not row.reject_holm:
            decision = "The test does not reject the zero-difference hypothesis at the chosen Holm-adjusted threshold."
        lines.extend([
            f"### {row.test.replace('_', ' ').title()}", "",
            f"Average daily morning rate {row.morning_mean_pct:.3f}%, evening rate {row.evening_mean_pct:.3f}%. Evening minus morning {row.effect_pp:.3f} percentage points, with 95% HAC interval [{row.ci_low:.3f}, {row.ci_high:.3f}]. Raw p {row.p_value:.3g}, Holm-adjusted p {row.p_holm:.3g}. {decision}",
            f"The separately pooled flight-weighted rates are {row.morning_pooled_pct:.3f}% and {row.evening_pooled_pct:.3f}%. Their difference can differ from the equal-day test estimate.", "",
        ])
    lines.extend([
        "## Interpretation and limits", "",
        "The recorded 2015 rates are exact summaries of the supplied records. Inferential intervals and p-values refer to a model of comparable operating days and depend on that model's assumptions. Daily aggregation and HAC covariance address some dependence, while uncertainty beyond the chosen lag can remain. The 14-lag columns help assess that choice.",
        "These are exploratory tests motivated by the project's existing descriptive findings. Independent data would be needed for a confirmatory follow-up.",
        "The block-bootstrap correlation intervals are approximate. Resampled week-long blocks must represent comparable operating periods, and seasonal changes can affect interval coverage.",
        "These analyses show associations. Causal claims need stronger controls or a different study design. A small p-value does not establish a large effect, forecast accuracy, or the probability that a hypothesis is true. Neither regression predicts an individual flight's outcome. Flight volume and delay can both respond to seasonal patterns.",
        "October's unmatched numeric airport codes remain included because these calculations do not require airport names. The 05:00-11:59 and 17:00-23:59 contrast leaves other departure hours out of that particular comparison.",
        "No model training or predictive holdout is used here. All observed dates contribute to the descriptive regressions and paired tests.", "",
        "## Method references", "",
        "- [Statsmodels robust covariance and HAC](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.get_robustcov_results.html)",
        "- [Statsmodels Holm multiple-test adjustment](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html)",
        "- [SciPy Pearson correlation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.pearsonr.html)", "",
    ])
    (results_dir / "statistical_report.md").write_text("\n".join(lines), encoding="utf-8")


def run_statistics(work_dir, results_dir):
    """Read full-data daily counts and export statistics, checks and three charts."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    daily = read_daily_statistics(work_dir)
    rows, lines = [], []
    for name, predictor, outcome in (
        ("departure_arrival", "mean_departure_delay", "mean_arrival_delay"),
        ("volume_late", "volume_thousands", "late_rate_pct"),
    ):
        row, line = daily_regression(daily, name, predictor, outcome)
        rows.append(row)
        lines.append(line)
    regressions = pd.DataFrame(rows)
    regression_lines = pd.concat(lines, ignore_index=True)
    tests = paired_time_tests(daily)
    p_values = pd.concat([regressions["p_value"], tests["p_value"]], ignore_index=True)
    rejected, corrected, _, _ = multipletests(p_values, alpha=ALPHA, method="holm")
    regressions["p_holm"], tests["p_holm"] = corrected[:2], corrected[2:]
    regressions["reject_holm"], tests["reject_holm"] = rejected[:2], rejected[2:]
    for name, frame in (
        ("statistics_daily", daily), ("statistics_regressions", regressions),
        ("statistics_regression_lines", regression_lines), ("statistics_hypothesis_tests", tests),
    ):
        frame.to_csv(results_dir / f"{name}.csv", index=False)
    summary = {
        "scheduled_flights": int(daily["scheduled_flights"].sum()), "days": len(daily),
        "date_min": str(daily["flight_date"].min().date()), "date_max": str(daily["flight_date"].max().date()),
        "unit": "one service date, equal-day weighting", "hac_lags": HAC_LAGS,
        "sensitivity_lags": SENSITIVITY_LAGS, "primary_tests": 4, "multiple_testing": "Holm",
        "alpha": ALPHA, "block_bootstrap_days": BLOCK_DAYS, "bootstrap_repeats": BOOTSTRAP_REPEATS,
        "random_seed": RANDOM_SEED, "totals_match_overview": True,
        "regressions": regressions.to_dict(orient="records"), "hypothesis_tests": tests.to_dict(orient="records"),
        "environment": {"python": platform.python_version(), "scipy": scipy.__version__, "statsmodels": statsmodels.__version__},
    }
    (results_dir / "statistics.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_statistical_report(daily, regressions, tests, results_dir)
    write_statistical_figures(daily, regressions, regression_lines, tests, results_dir)
    print(f"Statistical analysis used {len(daily)} dates and {summary['scheduled_flights']:,} scheduled flights.")
    print(regressions[["model", "slope", "r_squared", "pearson_r", "p_holm"]].to_string(index=False))
    print(tests[["test", "effect_pp", "ci_low", "ci_high", "p_holm"]].to_string(index=False))
    print(f"Statistical tables, report and three charts are in {results_dir.resolve()}.")
    return summary
