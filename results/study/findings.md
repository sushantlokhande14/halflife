# Study results (generated)

Window: 2026-10-06 to 2026-11-16. S&P 500 8-K filings measured: 882; placebo moments: 1497.
Minutes are trading minutes after the last price before the filing. t50/t90: first time the
path reaches 50%/90% of the move at the settling close (informative events only, median, 90% bootstrap interval).

## By category

| category | events | informative | informative_share | median_abs_move_informative_bps | t50_median | t50_low | t50_high | t90_median | done_by_10min | pre_event_share | next_day_continues |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| earnings | 453 | 209 | 46.1% | 625 | 130 | 90 | 156 | 250 | 1% | -0% | 53% |
| financing | 7 | 2 | 28.6% | 678 | 355 | 58 | 652 | 531 | 0% | -8% | 50% |
| vote | 14 | 2 | 14.3% | 775 | 404 | 230 | 578 | 652 | 1% | -0% | 50% |
| disclosure | 73 | 9 | 12.3% | 478 | 102 | 20 | 438 | 168 | 1% | -5% | 56% |
| deal | 77 | 8 | 10.4% | 709 | 483 | 169 | 521 | 536 | 0% | 1% | 75% |
| other | 135 | 8 | 5.9% | 416 | 391 | 95 | 535 | 461 | 0% | -2% | 25% |
| placebo | 1497 | 80 | 5.3% | 402 | 336 | 300 | 385 | 492 | -0% | -0% | 30% |
| leadership | 108 | 3 | 2.8% | 385 | 568 | 100 | 576 | 636 | 5% | -7% | 33% |
| governance | 8 | 0 | 0.0% |  |  |  |  |  |  |  |  |
| misc | 7 | 0 | 0.0% |  |  |  |  |  |  |  |  |

## Earnings, by when the filing landed

| session | events | informative | informative_share | median_abs_move_informative_bps | t50_median | t50_low | t50_high | t90_median | done_by_10min | done_by_60min | done_before_open | opening_jump | pre_event_share | overshoot_share | next_day_continues |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| closed | 2 | 0 | 0.0% |  |  |  |  |  |  |  |  |  |  |  |  |
| post | 194 | 91 | 46.9% | 667 | 464 | 262 | 538 | 568 | 1% | 6% | 37% | 23% | -2% | 36% | 59% |
| pre | 248 | 116 | 46.8% | 580 | 89 | 83 | 118 | 166 | 1% | 19% | 20% | 25% | -0% | 39% | 47% |
| regular | 9 | 2 | 22.2% | 407 | 115 | 2 | 228 | 210 | 13% | 35% |  |  | 32% | 0% | 100% |

done_before_open: share of the move priced in before the regular open; opening_jump: share added by the
first two minutes of the regular session. Both are medians over informative events filed before the open.

## Latency: what is left at each reaction time

remaining: median share of an informative earnings move still ahead. follow: mean return to the settling close
from trading in the direction of the move so far (all events, before costs).

### Earnings

| latency_minutes | remaining_median | remaining_low | remaining_high | follow_mean_bps | follow_low_bps | follow_high_bps | follow_events |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 100% | 100% | 100% | -40.6 | -88.4 | 7.6 | 438 |
| 4 | 100% | 100% | 100% | -62.8 | -108.2 | -17.8 | 440 |
| 6 | 100% | 100% | 100% | -49.1 | -93.7 | -0.9 | 445 |
| 10 | 99% | 99% | 100% | -28.1 | -72.2 | 16.4 | 444 |
| 16 | 98% | 94% | 99% | -7.8 | -51.0 | 36.1 | 448 |
| 30 | 95% | 91% | 98% | -26.7 | -70.0 | 15.9 | 447 |
| 60 | 86% | 82% | 92% | -35.1 | -75.7 | 5.7 | 449 |
| 120 | 75% | 62% | 81% | -18.7 | -57.0 | 18.3 | 451 |
| 240 | 34% | 29% | 40% | -1.6 | -31.4 | 28.0 | 450 |

### All filings

| latency_minutes | remaining_median | remaining_low | remaining_high | follow_mean_bps | follow_low_bps | follow_high_bps | follow_events |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 100% | 100% | 100% | -24.6 | -51.8 | 1.8 | 819 |
| 4 | 100% | 100% | 100% | -36.8 | -63.2 | -10.3 | 831 |
| 6 | 100% | 100% | 100% | -27.9 | -53.9 | -1.4 | 836 |
| 10 | 99% | 99% | 100% | -19.1 | -44.0 | 6.3 | 839 |
| 16 | 98% | 96% | 100% | -7.9 | -34.5 | 16.3 | 846 |
| 30 | 96% | 93% | 99% | -24.3 | -48.4 | -0.9 | 848 |
| 60 | 90% | 84% | 94% | -21.2 | -44.3 | 1.5 | 852 |
| 120 | 77% | 69% | 83% | -13.4 | -36.3 | 9.8 | 853 |
| 240 | 36% | 32% | 43% | -5.1 | -23.2 | 13.3 | 867 |

## The one FOMC statement in the window (illustration, n = 1)

| date | move_to_close_bps | first_half_minutes | largest_excursion_bps | largest_excursion_minutes |
|---|---:|---:|---:|---:|
| 2026-10-28 | 14 | 36 | 24 | 44 |
