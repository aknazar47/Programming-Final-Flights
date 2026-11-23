# Statistical analysis of flight delays and cancellations

The analysis covers 5,819,079 scheduled flights across 365 consecutive dates.
The statistical unit is one recorded service date. Every date has equal weight in the regression and paired tests.

## Methods and assumptions

The two regressions examine daily mean departure versus arrival delay and daily scheduled volume versus late-arrival percentage. Departure and arrival means use the same completed, nondiverted flights with both delays recorded. Negative delay minutes are retained.
Regression lines use ordinary least squares. Standard errors, two-sided tests and 95% pointwise confidence intervals use heteroskedasticity and autocorrelation consistent (HAC) covariance with 7 daily lags. CSV outputs include a 14-lag sensitivity check and month/weekday-adjusted regression coefficients.
Morning means scheduled local departures from 05:00 through 11:59. Evening means 17:00 through 23:59. Each date contributes its evening-minus-morning percentage-point difference. The hypotheses test whether the average daily difference is zero.
The four primary null hypotheses specify zero slope for each regression and zero mean difference for each of the two time-of-day comparisons. Holm correction controls their familywise error rate at 0.05. Reported 95% intervals are individual intervals, so significance decisions use the Holm-adjusted p-values.
Pearson r describes linear correlation and Spearman rho describes rank association. Pearson confidence intervals use a circular 7-day moving-block bootstrap with 2,000 draws and seed 2015. Correlation p-values are omitted because independent-day assumptions would be inappropriate. Regression slope tests use HAC inference.

## Regression and correlation results

### Departure Arrival

Slope 1.200 daily mean arrival-delay minutes per minute of daily mean departure delay, with 95% HAC interval [1.149, 1.252]. R-squared 0.975. Raw p 4.87e-154, Holm-adjusted p 1.95e-153.
Pearson r 0.987 with block-bootstrap interval [0.985, 0.990]. Spearman rho 0.984.
After adjustment for month and weekday, the slope is 1.207, with HAC interval [1.169, 1.245]. This sensitivity model is observational and can still reflect unmeasured route, carrier, or weather differences.

The fitted line accounts for 97.5% of the variation in the daily outcome in this dataset. This is an in-sample description of daily aggregates.

### Volume Late

Slope 1.560 late-arrival percentage points per 1,000 scheduled flights, with 95% HAC interval [1.134, 1.985]. R-squared 0.079. Raw p 3.25e-12, Holm-adjusted p 6.51e-12.
Pearson r 0.281 with block-bootstrap interval [0.199, 0.380]. Spearman rho 0.344.
After adjustment for month and weekday, the slope is 2.413, with HAC interval [0.903, 3.922]. This sensitivity model is observational and can still reflect unmeasured route, carrier, or weather differences.

The fitted line accounts for 7.9% of the variation in the daily outcome in this dataset. This is an in-sample description of daily aggregates.

## Morning and evening hypothesis tests

### Late Arrival

Average daily morning rate 12.834%, evening rate 24.683%. Evening minus morning 11.848 percentage points, with 95% HAC interval [10.315, 13.382]. Raw p 9.95e-41, Holm-adjusted p 2.99e-40. The zero-difference hypothesis is rejected after Holm correction.
The separately pooled flight-weighted rates are 12.797% and 25.132%. Their difference can differ from the equal-day test estimate.

### Cancellation

Average daily morning rate 1.426%, evening rate 1.861%. Evening minus morning 0.435 percentage points, with 95% HAC interval [0.267, 0.602]. Raw p 5.26e-07, Holm-adjusted p 5.26e-07. The zero-difference hypothesis is rejected after Holm correction.
The separately pooled flight-weighted rates are 1.410% and 1.852%. Their difference can differ from the equal-day test estimate.

## Interpretation and limits

The recorded 2015 rates are exact summaries of the supplied records. Inferential intervals and p-values refer to a model of comparable operating days and depend on that model's assumptions. Daily aggregation and HAC covariance address some dependence, while uncertainty beyond the chosen lag can remain. The 14-lag columns help assess that choice.
These are exploratory tests motivated by the project's existing descriptive findings. Independent data would be needed for a confirmatory follow-up.
The block-bootstrap correlation intervals are approximate. Resampled week-long blocks must represent comparable operating periods, and seasonal changes can affect interval coverage.
These analyses show associations. Causal claims need stronger controls or a different study design. A small p-value does not establish a large effect, forecast accuracy, or the probability that a hypothesis is true. Neither regression predicts an individual flight's outcome. Flight volume and delay can both respond to seasonal patterns.
October's unmatched numeric airport codes remain included because these calculations do not require airport names. The 05:00-11:59 and 17:00-23:59 contrast leaves other departure hours out of that particular comparison.
No model training or predictive holdout is used here. All observed dates contribute to the descriptive regressions and paired tests.

## Method references

- [Statsmodels robust covariance and HAC](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.get_robustcov_results.html)
- [Statsmodels Holm multiple-test adjustment](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html)
- [SciPy Pearson correlation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.pearsonr.html)
