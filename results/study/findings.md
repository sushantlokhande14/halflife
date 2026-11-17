# Study results (generated)

Window: 2026-10-06 to 2026-11-16. S&P 500 8-K filings measured: 920; placebo moments: 1502.
Minutes are trading minutes after the last price before the filing. t50/t90: first time the
path reaches 50%/90% of the move at the settling close (informative events only, median, 90% bootstrap interval).

## By category

| category | events | informative | informative_share | median_abs_move_informative_bps | t50_median | t50_low | t50_high | t90_median | done_by_10min | pre_event_share | next_day_continues |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| earnings | 456 | 211 | 46.3% | 625 | 130 | 90 | 156 | 250 | 1% | -0% | 53% |
| financing | 7 | 2 | 28.6% | 678 | 355 | 58 | 652 | 531 | 0% | -8% | 50% |
| vote | 16 | 2 | 12.5% | 775 | 404 | 230 | 578 | 652 | 1% | -0% | 50% |
| disclosure | 74 | 9 | 12.2% | 478 | 102 | 20 | 438 | 168 | 1% | -5% | 56% |
| deal | 78 | 8 | 10.3% | 709 | 483 | 169 | 521 | 536 | 0% | 1% | 75% |
| other | 165 | 12 | 7.3% | 342 | 391 | 176 | 451 | 462 | 0% | -1% | 42% |
| placebo | 1502 | 96 | 6.4% | 380 | 323 | 290 | 390 | 474 | -0% | -0% | 38% |
| leadership | 109 | 3 | 2.8% | 385 | 568 | 100 | 576 | 636 | 5% | -7% | 33% |
| governance | 8 | 0 | 0.0% |  |  |  |  |  |  |  |  |
| misc | 7 | 0 | 0.0% |  |  |  |  |  |  |  |  |

## Earnings, by when the filing landed

| session | events | informative | informative_share | median_abs_move_informative_bps | t50_median | t50_low | t50_high | t90_median | done_by_10min | done_by_60min | done_before_open | opening_jump | pre_event_share | overshoot_share | next_day_continues |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| closed | 2 | 0 | 0.0% |  |  |  |  |  |  |  |  |  |  |  |  |
| post | 196 | 93 | 47.4% | 667 | 464 | 262 | 538 | 568 | 1% | 6% | 37% | 23% | -2% | 35% | 59% |
| pre | 249 | 116 | 46.6% | 580 | 89 | 83 | 119 | 166 | 1% | 19% | 20% | 25% | -0% | 39% | 47% |
| regular | 9 | 2 | 22.2% | 407 | 115 | 2 | 228 | 210 | 13% | 35% |  |  | 32% | 0% | 100% |

done_before_open: share of the move priced in before the regular open; opening_jump: share added by the
first two minutes of the regular session. Both are medians over informative events filed before the open.

## Latency: what is left at each reaction time

remaining: median share of an informative earnings move still ahead. follow: mean return to the settling close
from trading in the direction of the move so far (all events, before costs).

### Earnings

| latency_minutes | remaining_median | remaining_low | remaining_high | follow_mean_bps | follow_low_bps | follow_high_bps | follow_events |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 100% | 100% | 100% | -38.6 | -87.0 | 8.2 | 441 |
| 4 | 100% | 100% | 100% | -65.7 | -109.4 | -21.8 | 443 |
| 6 | 100% | 100% | 100% | -49.0 | -91.6 | -2.7 | 447 |
| 10 | 99% | 99% | 100% | -26.5 | -71.4 | 15.5 | 447 |
| 16 | 98% | 94% | 99% | -10.4 | -53.9 | 31.4 | 451 |
| 30 | 96% | 92% | 98% | -24.4 | -68.0 | 17.4 | 450 |
| 60 | 86% | 82% | 93% | -39.5 | -80.5 | 0.7 | 452 |
| 120 | 75% | 61% | 81% | -19.6 | -58.2 | 18.8 | 454 |
| 240 | 34% | 30% | 40% | -4.7 | -36.1 | 26.2 | 453 |

### All filings

| latency_minutes | remaining_median | remaining_low | remaining_high | follow_mean_bps | follow_low_bps | follow_high_bps | follow_events |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 100% | 100% | 100% | -25.2 | -53.0 | 0.6 | 856 |
| 4 | 100% | 100% | 100% | -40.1 | -65.9 | -14.6 | 868 |
| 6 | 100% | 100% | 100% | -30.5 | -57.5 | -5.3 | 872 |
| 10 | 99% | 99% | 100% | -19.9 | -43.7 | 4.5 | 876 |
| 16 | 98% | 96% | 99% | -6.4 | -29.8 | 18.0 | 883 |
| 30 | 96% | 95% | 99% | -20.1 | -44.5 | 2.6 | 885 |
| 60 | 90% | 86% | 94% | -22.0 | -45.2 | 0.5 | 890 |
| 120 | 77% | 69% | 84% | -11.6 | -32.9 | 9.2 | 891 |
| 240 | 37% | 33% | 44% | -4.7 | -22.3 | 12.6 | 905 |

## The one FOMC statement in the window (illustration, n = 1)

| date | move_to_close_bps | first_half_minutes | largest_excursion_bps | largest_excursion_minutes |
|---|---:|---:|---:|---:|
| 2026-10-28 | 14 | 36 | 24 | 44 |
