"""Plot daily regressions, paired time-of-day comparisons and weekday rates."""

from pathlib import Path

import seaborn as sns

from figures import GRID, INK, MUTED, RUST, TEAL, save_figure

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


def style_axis(ax):
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK)
    sns.despine(ax=ax)


def p_value_text(value):
    if value < 0.001:
        return "p < 0.001"
    return f"p = {value:.3f}"


def plot_regressions(daily, regressions, regression_lines, path):
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 6.0))
    fig.subplots_adjust(left=0.075, right=0.97, bottom=0.25, top=0.78, wspace=0.30)
    panels = [
        (
            "departure_arrival", "mean_departure_delay", "mean_arrival_delay",
            "Departure delay and arrival delay", "Daily mean departure delay (minutes)",
            "Daily mean arrival delay (minutes)", TEAL,
        ),
        (
            "volume_late", "volume_thousands", "late_rate_pct",
            "Scheduled traffic and late arrivals", "Scheduled flights per day (thousands)",
            "Daily late-arrival rate", RUST,
        ),
    ]
    for ax, panel in zip(axes, panels):
        model, predictor, outcome, title, xlabel, ylabel, color = panel
        observations = daily[[predictor, outcome]].dropna()
        fitted = regression_lines.loc[regression_lines["model"] == model].sort_values("x")
        summary = regressions.loc[regressions["model"] == model].iloc[0]
        sns.scatterplot(
            data=observations, x=predictor, y=outcome, color=color,
            s=23, alpha=0.48, linewidth=0, label="Daily value", ax=ax,
        )
        ax.fill_between(
            fitted["x"], fitted["ci_low"], fitted["ci_high"],
            color=color, alpha=0.18, label="95% CI for mean",
        )
        ax.plot(fitted["x"], fitted["predicted"], color=color, linewidth=2, label="OLS fit")
        ax.set_title(title, loc="left", fontweight="bold", color=INK, pad=12)
        ax.set(xlabel=xlabel, ylabel=ylabel)
        if outcome == "late_rate_pct":
            ax.yaxis.set_major_formatter(PercentFormatter(xmax=100))
        ax.legend(loc="best", frameon=True, facecolor="white", edgecolor="white", fontsize=8)
        style_axis(ax)
        position = ax.get_position()
        fig.text(
            position.x0, 0.13,
            f"{len(observations)} dates    Pearson r = {summary['pearson_r']:.3f}    "
            f"R² = {summary['r_squared']:.3f}\n"
            f"Holm-adjusted slope {p_value_text(summary['p_holm'])}",
            ha="left", va="center", color=INK, fontsize=10, linespacing=1.5,
        )
    fig.text(0.075, 0.96, "Relationships between daily flight measures", fontsize=20,
             fontweight="bold", color=INK, va="top")
    fig.text(0.075, 0.89, "Each point represents one service date.", fontsize=11,
             color=MUTED, va="top")
    fig.text(
        0.075, 0.035,
        "Bands show pointwise 95% confidence intervals for the fitted daily mean, "
        "using HAC standard errors with 7 lags.",
        fontsize=9, color=MUTED, va="bottom",
    )
    save_figure(fig, path)


def plot_time_of_day(tests, path):
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 6.0))
    fig.subplots_adjust(left=0.075, right=0.97, bottom=0.30, top=0.78, wspace=0.30)
    panels = [("late_arrival", "Late arrivals"), ("cancellation", "Cancellations")]
    for ax, (test_id, title) in zip(axes, panels):
        summary = tests.loc[tests["test"] == test_id].iloc[0]
        means = [summary["morning_mean_pct"], summary["evening_mean_pct"]]
        bars = ax.bar([0, 1], means, width=0.55, color=[TEAL, RUST])
        ax.bar_label(bars, fmt="%.2f%%", padding=5, fontsize=11, color=INK)
        ax.set_xticks([0, 1], ["Morning\n05:00–11:59", "Evening\n17:00–23:59"])
        ax.set_title(title, loc="left", fontweight="bold", color=INK, pad=12)
        ax.set(ylabel="Mean daily rate", ylim=(0, max(means) * 1.22 + 0.1))
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=100))
        style_axis(ax)
        position = ax.get_position()
        fig.text(
            position.x0, 0.145,
            f"Evening − morning = {summary['effect_pp']:+.2f} percentage points\n"
            f"95% CI [{summary['ci_low']:+.2f}, {summary['ci_high']:+.2f}] pp\n"
            f"Holm-adjusted {p_value_text(summary['p_holm'])}",
            ha="left", va="center", color=INK, fontsize=10, linespacing=1.5,
        )
    fig.text(0.075, 0.96, "Morning and evening flight outcomes", fontsize=20,
             fontweight="bold", color=INK, va="top")
    fig.text(0.075, 0.89, "Each paired service date receives equal weight.", fontsize=11,
             color=MUTED, va="top")
    fig.text(
        0.075, 0.035,
        "Differences use paired daily rates and HAC standard errors with 7 lags. "
        "Holm adjustment covers all four primary tests.",
        fontsize=9, color=MUTED, va="bottom",
    )
    save_figure(fig, path)


def plot_weekday(daily, path):
    count_columns = ["scheduled_flights", "cancelled_flights", "eligible_arrivals", "delayed_arrivals"]
    weekday = daily.groupby(["weekday_number", "weekday"], as_index=False)[count_columns].sum()
    weekday = weekday.sort_values("weekday_number")
    eligible = weekday["eligible_arrivals"].replace(0, float("nan"))
    scheduled = weekday["scheduled_flights"].replace(0, float("nan"))
    weekday["late_rate_pct"] = 100.0 * weekday["delayed_arrivals"] / eligible
    weekday["cancellation_rate_pct"] = 100.0 * weekday["cancelled_flights"] / scheduled
    weekday["day_label"] = weekday["weekday"].str[:3]
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.6))
    fig.subplots_adjust(left=0.075, right=0.97, bottom=0.22, top=0.78, wspace=0.30)
    panels = [("late_rate_pct", "Late arrivals", TEAL), ("cancellation_rate_pct", "Cancellations", RUST)]
    for ax, (rate, title, color) in zip(axes, panels):
        sns.barplot(
            data=weekday, x="day_label", y=rate, color=color, saturation=1,
            errorbar=None, order=weekday["day_label"].tolist(), ax=ax,
        )
        ax.bar_label(ax.containers[0], fmt="%.2f%%", padding=4, fontsize=9, color=INK)
        ax.set_title(title, loc="left", fontweight="bold", color=INK, pad=12)
        ax.set(xlabel="Service-date weekday", ylabel="Pooled flight rate",
               ylim=(0, weekday[rate].max() * 1.20 + 0.1))
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=100))
        style_axis(ax)
    fig.text(0.075, 0.96, "Flight outcomes by weekday", fontsize=20,
             fontweight="bold", color=INK, va="top")
    fig.text(0.075, 0.89, "Descriptive rates pooled from all service dates in 2015.", fontsize=11,
             color=MUTED, va="top")
    fig.text(
        0.075, 0.055,
        "Each weekday rate uses summed flight counts. Late arrivals use eligible arrivals. "
        "Cancellations use all scheduled flights.",
        fontsize=9, color=MUTED, va="bottom",
    )
    save_figure(fig, path)


def write_statistical_figures(daily, regressions, regression_lines, tests, results_dir):
    """Save three statistical figures without changing the original SQL charts."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    with sns.axes_style("white"), sns.plotting_context("notebook"):
        plot_regressions(daily, regressions, regression_lines, results_dir / "statistics_regression.png")
        plot_time_of_day(tests, results_dir / "statistics_time_of_day.png")
        plot_weekday(daily, results_dir / "statistics_weekday.png")
