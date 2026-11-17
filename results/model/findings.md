# Model results (generated)

## Ten trading minutes after the filing

Eligible events (moved at least 0.5 daily s.d. by the decision): 169; out of sample: 56 across 3 weekly folds. Base rate of continuation: 49.7%.

| model | events | auc | brier | brier_skill | log_loss | decisions | coverage | hit_rate | mean_gross_bps | mean_net_bps | t_net | t_net_days |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base rate | 56 | 0.500 | 0.2503 | -0.001 | 0.6937 | 0 | 0% |  |  |  |  |  |
| reaction size only | 56 | 0.471 | 0.2580 | -0.032 | 0.7091 | 28 | 50% | 42.9% | -94.0 | -124.0 | -0.80 | -1.29 |
| logistic, all features | 56 | 0.499 | 0.2720 | -0.088 | 0.8691 | 40 | 71% | 47.5% | -133.3 | -162.3 | -1.53 | 0.09 |
| gradient boosting | 56 | 0.503 | 0.2692 | -0.077 | 0.7319 | 44 | 79% | 50.0% | -48.2 | -77.3 | -0.69 | -0.56 |
| always with the move | 56 |  |  |  |  | 56 | 100% | 50.0% | 11.5 | -17.7 | -0.19 | 0.46 |
| always against the move | 56 |  |  |  |  | 56 | 100% | 50.0% | -11.5 | -40.8 | -0.45 | -1.00 |

t_net counts every trade; t_net_days counts each trading day once.

Reliability of the live model's out-of-sample probabilities (logistic, all features):

| bin | predicted | observed | events |
|---:|---:|---:|---:|
| 0 | 0.295 | 0.364 | 11 |
| 1 | 0.426 | 0.455 | 11 |
| 2 | 0.498 | 0.818 | 11 |
| 3 | 0.549 | 0.545 | 11 |
| 4 | 0.714 | 0.333 | 12 |

## Right after the regular open, for filings released before it

Eligible events (moved at least 0.5 daily s.d. by the decision): 526; out of sample: 374 across 4 weekly folds. Base rate of continuation: 52.3%.

| model | events | auc | brier | brier_skill | log_loss | decisions | coverage | hit_rate | mean_gross_bps | mean_net_bps | t_net | t_net_days |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base rate | 374 | 0.500 | 0.2511 | -0.011 | 0.6953 | 0 | 0% |  |  |  |  |  |
| reaction size only | 374 | 0.493 | 0.2528 | -0.018 | 0.6989 | 55 | 15% | 40.0% | -80.7 | -90.7 | -1.69 | -0.64 |
| logistic, all features | 374 | 0.470 | 0.2798 | -0.126 | 0.7651 | 266 | 71% | 45.5% | -19.3 | -29.3 | -1.35 | -1.49 |
| gradient boosting | 374 | 0.535 | 0.2652 | -0.068 | 0.7309 | 299 | 80% | 55.2% | 50.8 | 40.8 | 2.06 | 1.53 |
| always with the move | 374 |  |  |  |  | 374 | 100% | 54.0% | 55.9 | 45.9 | 2.60 | 0.19 |
| always against the move | 374 |  |  |  |  | 374 | 100% | 46.0% | -55.9 | -65.9 | -3.74 | -0.81 |

t_net counts every trade; t_net_days counts each trading day once.

Reliability of the live model's out-of-sample probabilities (gradient boosting):

| bin | predicted | observed | events |
|---:|---:|---:|---:|
| 0 | 0.327 | 0.467 | 75 |
| 1 | 0.461 | 0.533 | 75 |
| 2 | 0.561 | 0.581 | 74 |
| 3 | 0.666 | 0.560 | 75 |
| 4 | 0.789 | 0.560 | 75 |

### Stress test: go with the opening move, every event, hold to the close

t_days counts each trading day once (events on the same day are not independent).

| slice | events | days | hit_rate | mean_net_bps | net_low_bps | net_high_bps | median_net_bps | trimmed_mean_net_bps | t_events | t_days |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all events | 526 | 29 | 52.3% | 17.5 | -6.6 | 40.5 | -0.4 | 16.6 | 1.23 | -0.75 |
| week of Oct 05 | 20 | 4 | 60.0% | -17.5 | -78.5 | 41.9 | 6.9 | -16.8 | -0.46 | -1.51 |
| week of Oct 12 | 40 | 4 | 52.5% | -21.9 | -91.7 | 48.9 | -8.6 | -29.4 | -0.51 | -0.37 |
| week of Oct 19 | 90 | 5 | 44.4% | -72.6 | -125.5 | -23.6 | -20.8 | -54.8 | -2.34 | -2.81 |
| week of Oct 26 | 164 | 5 | 54.3% | 57.0 | 14.4 | 101.4 | 1.1 | 45.2 | 2.17 | 0.93 |
| week of Nov 02 | 170 | 5 | 57.1% | 59.2 | 13.6 | 105.4 | 22.5 | 63.4 | 2.14 | 1.20 |
| week of Nov 09 | 33 | 5 | 30.3% | -91.8 | -167.0 | -22.1 | -51.4 | -83.6 | -2.04 | -1.85 |
| week of Nov 16 | 9 | 1 | 66.7% | 64.0 | -13.1 | 156.9 | 54.2 | 64.0 | 1.15 |  |
| outside the two busiest weeks | 192 | 19 | 46.4% | -53.2 | -85.3 | -22.6 | -18.8 | -44.1 | -2.75 | -2.46 |
| filed after the close | 282 | 26 | 52.8% | 25.4 | -4.6 | 54.2 | 0.8 | 23.7 | 1.42 | 0.43 |
| filed before the open | 239 | 27 | 51.5% | 10.4 | -27.4 | 48.5 | -6.5 | 10.6 | 0.45 | -0.95 |
| earnings | 352 | 27 | 53.7% | 28.2 | -4.2 | 60.0 | 4.5 | 28.9 | 1.42 | 0.52 |
| other filings | 174 | 29 | 49.4% | -4.2 | -29.4 | 19.9 | -12.2 | -3.9 | -0.28 | -0.56 |
| opening move 2+ daily s.d. | 145 | 23 | 48.3% | -12.4 | -67.0 | 42.7 | -17.5 | -5.0 | -0.37 | -0.01 |
| opening move 0.5-2 daily s.d. | 381 | 29 | 53.8% | 28.8 | 4.1 | 53.1 | 4.5 | 22.3 | 1.94 | -0.18 |
| all events, 20 bps cost | 526 | 29 | 52.3% | 7.5 | -16.5 | 30.8 | -10.4 | 6.6 | 0.53 | -1.25 |
| all events, 30 bps cost | 526 | 29 | 52.3% | -2.5 | -25.9 | 20.4 | -20.4 | -3.4 | -0.18 | -1.75 |

### Stress test: gradient boosting at neighbouring settings (walk-forward, out of sample)

| max_depth | learning_rate | rounds | used | auc | decisions | mean_net_bps | t_net | t_net_days |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 0.03 | 100 | False | 0.545 | 268 | 41.1 | 2.01 | 2.02 |
| 2 | 0.03 | 150 | False | 0.541 | 282 | 44.4 | 2.26 | 2.10 |
| 2 | 0.03 | 200 | False | 0.535 | 289 | 45.7 | 2.28 | 1.84 |
| 2 | 0.05 | 100 | False | 0.538 | 287 | 43.4 | 2.20 | 1.87 |
| 2 | 0.05 | 150 | True | 0.535 | 299 | 40.8 | 2.06 | 1.53 |
| 2 | 0.05 | 200 | False | 0.530 | 307 | 33.8 | 1.75 | 1.39 |
| 2 | 0.10 | 100 | False | 0.526 | 315 | 41.4 | 2.23 | 2.11 |
| 2 | 0.10 | 150 | False | 0.518 | 321 | 30.6 | 1.60 | 1.49 |
| 2 | 0.10 | 200 | False | 0.511 | 328 | 16.7 | 0.85 | 0.19 |
| 3 | 0.03 | 100 | False | 0.528 | 291 | 43.8 | 2.16 | 2.20 |
| 3 | 0.03 | 150 | False | 0.523 | 306 | 43.2 | 2.21 | 1.83 |
| 3 | 0.03 | 200 | False | 0.525 | 320 | 41.7 | 2.13 | 1.97 |
| 3 | 0.05 | 100 | False | 0.528 | 305 | 49.3 | 2.50 | 2.29 |
| 3 | 0.05 | 150 | False | 0.521 | 321 | 35.7 | 1.82 | 1.74 |
| 3 | 0.05 | 200 | False | 0.528 | 327 | 39.5 | 2.04 | 1.62 |
| 3 | 0.10 | 100 | False | 0.515 | 323 | 31.9 | 1.68 | 1.54 |
| 3 | 0.10 | 150 | False | 0.518 | 330 | 20.3 | 1.07 | 0.26 |
| 3 | 0.10 | 200 | False | 0.517 | 342 | 16.7 | 0.89 | -0.06 |

### Where gradient boosting's out-of-sample money came from

| slice | trades | with_the_move_share | mean_net_bps | t_net |
|---|---:|---:|---:|---:|
| week of Oct 26 | 132 | 65% | 52.3 | 1.89 |
| week of Nov 02 | 128 | 61% | 38.1 | 1.11 |
| week of Nov 09 | 30 | 73% | 5.5 | 0.11 |
| week of Nov 16 | 9 | 78% | 26.4 | 0.44 |
| with the move | 193 | 100% | 73.7 | 3.36 |
| against the move | 106 | 0% | -19.2 | -0.50 |
