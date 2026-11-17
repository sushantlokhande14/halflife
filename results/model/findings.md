# Model results (generated)

## Ten trading minutes after the filing

Eligible events (moved at least 0.5 daily s.d. by the decision): 171; out of sample: 58 across 3 weekly folds. Base rate of continuation: 49.7%.

| model | events | auc | brier | brier_skill | log_loss | decisions | coverage | hit_rate | mean_gross_bps | mean_net_bps | t_net |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base rate | 58 | 0.500 | 0.2510 | -0.005 | 0.6951 | 0 | 0% |  |  |  |  |
| reaction size only | 58 | 0.433 | 0.2571 | -0.030 | 0.7074 | 23 | 40% | 39.1% | -190.2 | -220.2 | -1.39 |
| logistic, all features | 58 | 0.470 | 0.2754 | -0.103 | 0.8700 | 36 | 62% | 44.4% | -152.8 | -182.3 | -2.02 |
| gradient boosting | 58 | 0.507 | 0.2661 | -0.066 | 0.7260 | 46 | 79% | 52.2% | -29.2 | -58.3 | -0.55 |
| always with the move | 58 |  |  |  |  | 58 | 100% | 48.3% | 1.1 | -28.2 | -0.32 |
| always against the move | 58 |  |  |  |  | 58 | 100% | 51.7% | -1.1 | -30.5 | -0.35 |

Reliability of the main model's out-of-sample probabilities:

| bin | predicted | observed | events |
|---:|---:|---:|---:|
| 0 | 0.309 | 0.333 | 12 |
| 1 | 0.409 | 0.727 | 11 |
| 2 | 0.488 | 0.750 | 12 |
| 3 | 0.543 | 0.182 | 11 |
| 4 | 0.731 | 0.417 | 12 |

## Right after the regular open, for filings released before it

Eligible events (moved at least 0.5 daily s.d. by the decision): 541; out of sample: 386 across 4 weekly folds. Base rate of continuation: 51.8%.

| model | events | auc | brier | brier_skill | log_loss | decisions | coverage | hit_rate | mean_gross_bps | mean_net_bps | t_net |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base rate | 386 | 0.500 | 0.2537 | -0.023 | 0.7005 | 0 | 0% |  |  |  |  |
| reaction size only | 386 | 0.487 | 0.2544 | -0.025 | 0.7018 | 70 | 18% | 45.7% | -58.6 | -68.6 | -1.58 |
| logistic, all features | 386 | 0.474 | 0.2841 | -0.145 | 0.7812 | 287 | 74% | 47.0% | -12.3 | -22.3 | -1.09 |
| gradient boosting | 386 | 0.509 | 0.2724 | -0.098 | 0.7467 | 296 | 77% | 51.7% | 26.0 | 16.0 | 0.78 |
| always with the move | 386 |  |  |  |  | 386 | 100% | 54.4% | 57.7 | 47.7 | 2.78 |
| always against the move | 386 |  |  |  |  | 386 | 100% | 45.6% | -57.7 | -67.7 | -3.94 |

Reliability of the main model's out-of-sample probabilities:

| bin | predicted | observed | events |
|---:|---:|---:|---:|
| 0 | 0.255 | 0.623 | 77 |
| 1 | 0.425 | 0.519 | 77 |
| 2 | 0.509 | 0.603 | 78 |
| 3 | 0.591 | 0.434 | 76 |
| 4 | 0.727 | 0.538 | 78 |

### Stress test: go with the opening move, every event, hold to the close

t_days counts each trading day once (events on the same day are not independent).

| slice | events | days | hit_rate | mean_net_bps | net_low_bps | net_high_bps | median_net_bps | trimmed_mean_net_bps | t_events | t_days |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all events | 541 | 29 | 51.8% | 18.6 | -4.7 | 41.9 | -1.3 | 17.7 | 1.34 | -0.70 |
| week of Oct 05 | 19 | 4 | 47.4% | -28.6 | -91.6 | 33.0 | -15.3 | -28.6 | -0.73 | -2.26 |
| week of Oct 12 | 44 | 4 | 47.7% | -23.0 | -88.0 | 40.8 | -24.3 | -29.8 | -0.59 | -0.31 |
| week of Oct 19 | 90 | 5 | 44.4% | -72.9 | -126.2 | -24.1 | -20.8 | -55.1 | -2.36 | -2.89 |
| week of Oct 26 | 171 | 5 | 54.4% | 54.8 | 14.0 | 96.9 | 1.5 | 43.3 | 2.17 | 1.45 |
| week of Nov 02 | 175 | 5 | 57.7% | 64.4 | 19.3 | 109.3 | 27.3 | 69.1 | 2.39 | 1.25 |
| week of Nov 09 | 33 | 5 | 30.3% | -91.8 | -166.6 | -21.4 | -51.4 | -83.6 | -2.04 | -1.85 |
| week of Nov 16 | 9 | 1 | 66.7% | 64.0 | -15.2 | 153.6 | 54.2 | 64.0 | 1.15 |  |
| filed after the close | 292 | 26 | 52.1% | 25.8 | -2.8 | 54.2 | 0.6 | 24.2 | 1.49 | 0.42 |
| filed before the open | 245 | 27 | 51.4% | 12.5 | -24.1 | 49.9 | -4.5 | 12.5 | 0.56 | -0.88 |
| earnings | 355 | 27 | 53.8% | 29.4 | -4.7 | 62.0 | 4.8 | 30.2 | 1.49 | 0.52 |
| other filings | 186 | 29 | 47.8% | -1.9 | -25.5 | 21.1 | -18.4 | -1.5 | -0.13 | -0.47 |
| opening move 2+ daily s.d. | 147 | 23 | 48.3% | -10.6 | -65.0 | 43.4 | -17.5 | -3.2 | -0.32 | 0.01 |
| opening move 0.5-2 daily s.d. | 394 | 29 | 53.0% | 29.5 | 5.6 | 52.9 | 2.7 | 23.4 | 2.05 | -0.15 |
| all events, 20 bps cost | 541 | 29 | 51.8% | 8.6 | -14.1 | 31.7 | -11.3 | 7.7 | 0.62 | -1.20 |
| all events, 30 bps cost | 541 | 29 | 51.8% | -1.4 | -24.1 | 21.6 | -21.3 | -2.3 | -0.10 | -1.71 |
