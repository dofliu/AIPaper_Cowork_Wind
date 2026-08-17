# Dataset and preprocessing

> **Draft — not approved.** English is the submission language; see
> `docs/manuscript/README.md` for the three constraints this text must respect.
> Every quantity below is traceable to an artefact in this repository; the
> provenance column at the end of each subsection names it.

## 1. Dataset

We evaluate on **CARE to Compare v6**, a public benchmark of supervisory
control and data acquisition (SCADA) records from three European wind farms,
distributed under CC BY-SA 4.0. The archive used in this work is
5,503,439,673 bytes with SHA-256
`ca61379e98956d891041ad45c885109bd8a14199fde0688d0184a11c2d4194f1`; the hash is
verified programmatically at the start of every run rather than checked by
hand, so a silently substituted archive cannot enter the pipeline.

The release contains **95 labelled cases drawn from 36 turbines** across three
farms, spanning 2022-01-01 to 2024-02-06 at a 10-minute sampling interval.
Each case is a contiguous excerpt of roughly 55,000 rows.

| Wind farm | Cases | Rows | Columns | Data-dictionary entries |
|---|---|---|---|---|
| A | 22 | 1,196,747 | 86 | 54 |
| B | 15 | 859,065 | 257 | 63 |
| C | 58 | 3,187,136 | 957 | 238 |

Case labels in the v6 metadata are 45 anomaly and 50 normal. **The originating
publication reports 44 anomaly and 51 normal**; the discrepancy is a version
difference between the released archive and the paper, not a labelling
decision of ours, and we report the v6 figures because they are the ones our
runs consume.

Channels are renamed rather than anonymised, and each farm ships a
`feature_description.csv` giving name, statistic type, description, unit,
and angle/counter flags. Fault windows are given per case in `event_info.csv`
as `event_start` / `event_end` together with a free-text fault description;
these windows are the sole source of the earliness measurements in
Section [Evaluation protocol]. Files are semicolon-delimited, the train/test
split is a **per-row column** rather than a directory partition, and missing
values are empty fields — the archive uses no `-999`-style sentinel codes.

*Provenance: `scripts/care_v6_manifest.py` (gates G1–G6), `manifest_out/`.*

## 2. Case selection: 91 cases, not 95

Thirty of the 36 turbines appear in more than one case. Of the 108 same-turbine
case pairs, **five have genuinely overlapping evaluation windows**, which would
let a fault window from one case enter another case's false-alarm statistics.
We therefore exclude cases 32, 56, 72 and 87 outright, and **truncate case 93**
by dropping evaluation timestamps at or after `2023-08-24T13:00:00` — the moment
case 33's evaluation window opens on the same Farm C turbine, where the two
cases carry opposite labels and overlap by 0.12 days.

All experiments consequently use **91 cases (45 anomaly, 46 normal)**.

The truncation is applied in code, by
`evaluate_experiment.py --trim-case`, driven from the `experiment.trim_cases`
key of the pipeline configuration, and the applied trims are recorded in
`evaluation.json` under `trimmed_cases`. We state this explicitly because for a
period the truncation existed only as a comment in the configuration file and
was applied by nothing — a silent no-op that would have let the overlapping
window contribute false alarms while every artefact still looked correct.

*Provenance: `scripts/care_v6_split_audit.py`, `split_audit_out/`.*

## 3. Signal selection

The calibration layer operates on a frozen anomaly score, so the only signals
it needs are those consumed by the base scorer plus the wind speed used to
define operating regimes. We map each farm's renamed channels onto six
canonical signals using the shipped data dictionaries, and record the mapping,
its declared units and every operator override in a per-farm *signal map*
artefact:

| Canonical signal | Farm A | Farm B | Farm C |
|---|---|---|---|
| Active power | `power_30_avg` | `power_62_avg` | `power_6_avg` |
| Wind speed | `wind_speed_3_avg` | `wind_speed_61_avg` | `wind_speed_236_avg` |
| Rotor speed | `sensor_52_avg` | `sensor_25_avg` | mean(`sensor_144`–`147`) |
| Main-bearing temperature | **not available** | mean(`sensor_51`, `sensor_52`) | mean(`sensor_194`–`198`) |
| Pitch angle | `sensor_5_avg` | `sensor_10_avg` | mean(`sensor_103`–`105`) |
| Ambient temperature | `sensor_0_avg` | `sensor_8_avg` | `sensor_7_avg` |

Five properties of this mapping are consequences of the data rather than of our
design, and each changes what the paper may claim.

### 3.1 Active power is per-unit, not kilowatts

The data dictionaries declare `active_power` in kW, but the values in all three
farms lie in `[0, ~1.0]`:

| Farm | p01 | p50 | p99 |
|---|---|---|---|
| A | −0.009 | 0.113 | 0.976 |
| B | −0.004 | 0.276 | 1.029 |
| C | −0.004 | 0.230 | 1.012 |

The signal is normalised, consistently across farms, and remains a valid
feature; the declared unit in our signal maps is therefore `p.u.` We flag this
because a reader reproducing the work from the dictionary alone would
reasonably assume kilowatts.

### 3.2 Farm A has no main-bearing measurement

Farm A's dictionary contains gearbox high-speed-shaft and generator DE/NDE
bearing temperatures only — different components, not alternative
measurements of the same one. Farm A's signal map therefore declares the
main-bearing channel `not_available` with an explicit reason and ratification
record, rather than leaving it silently absent.

**This bounds the claim.** The main-bearing base scorer is evaluated on
**Farm B and Farm C only**, and main-bearing faults occurring on Farm A are
outside what that scorer can see. A regression test pins this limitation to
the code, so that if the channel ever becomes detectable the test fails and
the limitation statement is known to be stale.

### 3.3 The first power channel we selected was a model output

Farm A's dictionary offers two kW channels:

```
power_29   "Possible grid active power"   — an availability quantity (IEC 61400-26)
power_30   "Grid power"                   — the measurement
```

"Possible power" is what the turbine *could* have produced at the prevailing
wind speed, computed from wind speed and the power curve. A degrading turbine
leaves **no trace** in it — which is precisely the signal degradation we intend
to detect. Our channel resolver now requires a measured channel and refuses to
resolve, with a stated reason, when only a capability channel is available.

### 3.4 Main-bearing channels carry fault codes, on two farms, with different failure modes

More than 1% of Farm C's `sensor_194`/`sensor_195` rows are pinned at the
constant 850.0. Averaged with the three genuine ~46 °C channels this yields a
main-bearing temperature of **363 °C**, which a Mahalanobis scorer converts
into a very large distance — a false alarm produced without any error being
raised.

We therefore apply physical-range filtering **per channel, before averaging**,
with the policy and the rejected-row counts recorded in each farm's scorer
summary. After filtering, Farm C's main-bearing p99 is 53.957.

| Farm | Channel | Rows rejected | Share of farm rows |
|---|---|---|---|
| B | `sensor_52_avg` | 4,012 | 0.47% |
| B | `sensor_51_avg` | 464 | 0.05% |
| C | `sensor_194_avg` | 67,896 | 2.13% |
| C | `sensor_195_avg` | 67,871 | 2.13% |

**The two farms fail differently, and the difference is worth reporting.**
Farm C's two channels fail almost simultaneously (67,896 against 67,871, a
difference of 25 rows), consistent with a shared acquisition path; Farm B's two
channels fail independently of one another (4,012 against 464, a factor of 8.6).

This has a consequence the paper must disclose: because filtering precedes
averaging, rows where `sensor_52` is rejected but `sensor_51` is not carry a
**single-channel** main-bearing temperature rather than a two-channel mean.
This is deliberate — one failed channel should not disqualify its healthy
partner — and it affects roughly 0.47% of Farm B rows, which is negligible in
magnitude. It is nevertheless a reason the paper **cannot** state that the
main-bearing temperature is uniformly a two-channel average.

Farm A rejects zero rows, which is consistent rather than suspicious: its only
fault-coded signal would have been the main bearing, which it does not have.
We verified separately that the range filter was enabled and all five ranges
loaded, because "nothing was rejected" and "nothing was filtered" are
indistinguishable in the output.

All five Farm C channels are genuine main-bearing measurements and none are
discarded: on clean rows the cross-group correlation is 0.945–0.948, and the
median of 50.7 °C against 46 °C is physically ordered (inner race hotter than
housing), both far above the 28 °C ambient.

### 3.5 Two Farm C rotor-speed channels are excluded

Farm C offers four rotor-speed candidates:

```
sensor_144/145  "Rotor speed 1/2"                     p50 = 9.79   mutual r = 1.0000
sensor_146/147  "Rotor speed gearbox main shaft 1/2"  p50 = 80     mutual r = 0.2073, negative values occur
```

Channels 146/147 nominally measure the same shaft yet are almost uncorrelated
with each other and are of the wrong magnitude; averaging all four would move
the median from 9.8 to 46.6. They are excluded by operator declaration, with
the exclusion and its justification recorded in the farm's signal-map report.

### 3.6 Unit declarations differ in form but not in substance

Temperature is declared `degC` on Farms A/B and `Celsius` on Farm C; rotor
speed is `rpm` on A/B and `1/min` on C. We confirmed equivalence numerically
rather than lexically, and a dedicated cross-farm consistency check runs before
scoring. Farm A/B dictionaries additionally contain a **corrupted degree sign**
— the stored bytes are the UTF-8 encoding of U+FFFD, so the original character
is unrecoverable from the file. Those entries are marked
`UNREADABLE_IN_SOURCE` and resolved by explicit unit override.

Farm C rotor speed reads −5.5 when the turbine is stopped; this is a sensor
offset rather than a fault code, and the admissible range extends to −6.0 to
accommodate it.

*Provenance: `scripts/care_v6_signal_map_builder.py`, `scripts/physical_ranges.py`,
`scripts/check_unit_consistency.py`, `scripts/inspect_channels.py`,
`scripts/check_power_channel.py`; artefacts in `signal_map_out/`,
`scores_MD_2022_run*/scorer_summary_<farm>.json`.*

## 4. Reproducibility

Score streams are produced twice per farm from independent runs. For the
Mahalanobis base scorer the agreement requirement is **bit-identical**; the
per-column rejection counts of run 1 and run 2 match exactly on all three
farms. Physical ranges and gate thresholds have a single definition shared by
the scorer and the checkers, so that no two tools can disagree about what
counts as a plausible reading.

---

### Open items blocking this section from being final

1. Numbers for Farm-level results await the Phase 5 pipeline run; this section
   describes only the data and its preparation.
2. The compatibility-gate definitions are not yet ratified, so no sentence here
   may be upgraded to "the gate was passed".
3. The second base scorer is not implemented, so the D5 two-scorer claim is not
   yet supported.
