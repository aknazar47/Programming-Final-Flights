"""Create three Seaborn figures from the SQL result tables."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import pandas as pd
import seaborn as sns


INK = "#000000"
MUTED = "#444444"
TEAL = "#087E83"
RUST = "#AA4C38"
GRID = "#E2E9EC"
MIN_HEATMAP_ELIGIBLE = 1000


def save_figure(fig, path):
    """Write a PNG and release the figure even if saving fails."""
    try:
        fig.savefig(path, dpi=180, facecolor="white")
    finally:
        plt.close(fig)


def add_figure_text(fig, title, note):
    fig.text(0.045, 0.96, title, color=INK, fontsize=19, fontweight="bold", va="top")
    fig.text(0.045, 0.04, note, color=MUTED, fontsize=9, va="bottom")


def plot_rankings(tables, path):
    airlines = tables["airline_ranking"]
    airports = tables["airport_ranking"]
    airlines = airlines.loc[airlines["delay_rank"] <= 8].copy()
    airports = airports.loc[airports["delay_rank"] <= 8].copy()
    airlines["label"] = airlines["airline_code"] + "  " + airlines["airline_name"]
    airports["label"] = airports["airport_code"] + "  " + airports["city"].fillna("Unmapped")

    highest = 0
    for ranking in (airlines, airports):
        if not ranking.empty:
            highest = max(highest, ranking["late_rate_pct"].max())
    label_space = max(4, highest * 0.16)
    x_limit = max(10, highest + label_space)
    fig, axes = plt.subplots(1, 2, figsize=(14.4, 5.6))
    fig.subplots_adjust(left=0.24, right=0.96, top=0.80, bottom=0.19, wspace=0.58)
    panels = [
        (axes[0], airlines, "Airline ranking"),
        (axes[1], airports, "Origin airport ranking"),
    ]
    for ax, frame, label in panels:
        if frame.empty:
            ax.text(0.5, 0.5, "No qualifying groups", transform=ax.transAxes, ha="center")
            ax.set_yticks([])
        else:
            sns.barplot(
                data=frame, x="late_rate_pct", y="label", order=frame["label"].tolist(),
                color=TEAL, saturation=1, errorbar=None, ax=ax,
            )
            ax.bar_label(ax.containers[0], fmt="%.1f%%", padding=5, fontsize=9, color=INK)
        ax.set_title(label, loc="left", color=INK, fontweight="bold", pad=10)
        ax.set(xlabel="Late-arrival rate", ylabel="", xlim=(0, x_limit))
        ax.xaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
        ax.xaxis.grid(True, color=GRID, linewidth=0.8)
        ax.yaxis.grid(False)
        ax.set_axisbelow(True)
        sns.despine(ax=ax, left=True)
    add_figure_text(
        fig,
        "Highest late-arrival rates by airline and origin airport",
        "Ranks 1–8, including ties. Airport ranking requires at least 10,000 eligible arrivals "
        "from the origin. Late arrivals are at least 15 minutes behind schedule.",
    )
    save_figure(fig, path)


def plot_monthly(monthly, path):
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.0))
    fig.subplots_adjust(left=0.075, right=0.96, top=0.76, bottom=0.19, wspace=0.27)
    data = monthly.copy()
    months = pd.PeriodIndex(data["month"], freq="M")
    data["month_label"] = months.strftime("%b")
    panels = [
        (axes[0], "late_rate_pct", "rolling_late_rate_pct", "Late arrivals", TEAL),
        (axes[1], "cancellation_rate_pct", "rolling_cancellation_rate_pct", "Cancellations", RUST),
    ]
    for ax, rate, rolling, label, color in panels:
        sns.lineplot(
            data=data, x="month_label", y=rate, marker="o", color=color,
            linewidth=2.3, label="Monthly rate", ax=ax,
        )
        sns.lineplot(
            data=data, x="month_label", y=rolling, color=MUTED, linestyle="--",
            linewidth=1.8, label="3-month rolling rate", ax=ax,
        )
        ax.set_title(label, loc="left", color=INK, fontweight="bold", pad=10)
        ax.set(xlabel="Flight month", ylabel="")
        peak = data[[rate, rolling]].max().max()
        upper_limit = 1
        if pd.notna(peak) and peak > 0:
            upper_limit = peak * 1.18
        ax.set_ylim(bottom=0, top=upper_limit)
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=100))
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        ax.legend(loc="upper right", frameon=False, fontsize=9)
        sns.despine(ax=ax, left=True)
    add_figure_text(
        fig,
        "Monthly late-arrival and cancellation rates",
        "Rolling rates pool flight counts across up to three months. "
        "Late-arrival rates use eligible arrivals. Cancellation rates use all scheduled flights.",
    )
    save_figure(fig, path)


def plot_month_hour(by_month_hour, path):
    months = sorted(by_month_hour["month"].unique())
    hours = list(range(24))
    rates = by_month_hour.pivot(index="month", columns="departure_hour", values="late_rate_pct")
    rates = rates.reindex(index=months, columns=hours)
    eligible = by_month_hour.pivot(
        index="month", columns="departure_hour", values="eligible_arrivals"
    )
    eligible = eligible.reindex(index=months, columns=hours)
    # Seaborn leaves missing values blank so low-volume cells appear gray.
    rates = rates.where(eligible >= MIN_HEATMAP_ELIGIBLE)
    peak = rates.max().max()
    upper_limit = 10
    if pd.notna(peak):
        upper_limit = max(upper_limit, peak)

    fig, ax = plt.subplots(figsize=(13.2, 6.0))
    fig.subplots_adjust(left=0.08, right=0.92, top=0.84, bottom=0.20)
    ax.set_facecolor(GRID)
    if rates.empty:
        ax.text(0.5, 0.5, "No scheduled departure hours available", ha="center", va="center")
        ax.set_xticks([])
        ax.set_yticks([])
    else:
        sns.heatmap(
            rates, cmap="YlGnBu", vmin=0, vmax=upper_limit, ax=ax,
            linewidths=0.65, linecolor="white",
            cbar_kws={"label": "Late-arrival rate", "format": PercentFormatter(xmax=100)},
            xticklabels=[f"{hour:02d}" for hour in hours],
            yticklabels=pd.PeriodIndex(months, freq="M").strftime("%b"),
        )
        ax.tick_params(axis="x", labelrotation=0, length=0)
        ax.tick_params(axis="y", labelrotation=0, length=0)
    ax.set(xlabel="Scheduled local departure hour (24-hour clock)", ylabel="Flight month")
    add_figure_text(
        fig,
        "Late-arrival rates by month and scheduled departure hour",
        "Gray cells have fewer than 1,000 eligible arrivals. All observed hours are available in the SQL result tables.",
    )
    save_figure(fig, path)


def write_figures(tables, results_dir):
    """Save the ranking bars, monthly trends, and month-by-hour heatmap."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    with sns.axes_style("white"), sns.plotting_context("notebook"):
        plot_rankings(tables, results_dir / "rankings.png")
        plot_monthly(tables["monthly_rates"], results_dir / "monthly_rates.png")
        plot_month_hour(tables["month_hour"], results_dir / "month_hour.png")
