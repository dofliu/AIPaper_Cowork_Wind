#!/usr/bin/env python3
"""
Build the C0 signal map from CARE v6's own data dictionary.

THE FIND
--------
CARE v6 ships `feature_description.csv` in every farm directory:

    sensor_name;statistics_type;description;unit;is_angle;is_counter
    sensor_0;average;Ambient temperature;degC;False;False
    sensor_1;average;Wind absolute direction;deg;True;False

So the channels are not anonymous after all. They are *renamed*, with the
mapping shipped alongside. Every statistical inference about which
`sensor_<n>` is which — the whole premise of
`sensor_identification_profile.py` — is now redundant for any channel this
file names. Ground truth beats a correlation signature every time.

This script reads that dictionary and emits a C0 signal map with the real
units taken from the `unit` column, so nobody has to hand-type six mappings
per farm across three farms.

WHY THE PROFILER STAYS
----------------------
Two uses survive. First, cross-validation: if the profiler's statistical
pick disagrees with the dictionary, one of them is wrong and it is worth
knowing which before trusting either on a channel the dictionary describes
vaguely. Second, coverage: if the dictionary has no entry matching a
required signal, the profiler is still the only way to propose one — and
that proposal must then be marked unratified, as before.

WHAT THIS ANSWERS THAT MATTERS
------------------------------
Whether a **main bearing temperature** channel exists per farm. Base Scorer
2 (the main-bearing SCADA framework) needs it, and D5 requires the claim to
hold on BOTH scorers. If a farm has no such channel, that is a hard fact
about the archive, discoverable here in seconds rather than argued from
correlations.

MATCHING IS REPORTED, NOT ASSUMED
---------------------------------
Descriptions are free text written by three different operators. This
script matches them with explicit keyword rules, reports EVERY candidate it
found per signal with the rule that fired, and refuses to pick when two
candidates tie. A signal with several plausible channels (a farm with four
bearing temperatures, say) is surfaced for a human, not silently resolved.

USAGE
-----
    python3 care_v6_signal_map_builder.py \\
        --workdir    /path/to/extracted_care_v6 \\
        --output-dir ./signal_map_out \\
        [--profiles-dir ./sensor_profile_out]   # enables cross-validation

Outputs, per farm:
    feature_dictionary_<farm>.json  the dictionary parsed, verbatim
    signal_map_<farm>.json          C0-shaped map with real units
    signal_map_report_<farm>.json   every candidate per signal + ties + gaps

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import csv
import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

# Free-text descriptions, so match on ordered rules: the first rule that
# fires wins, and the rule name is recorded in the output.
ACTIVE_POWER_RE = re.compile(r"(?<!re)\bactive power\b")


SIGNAL_RULES = {
    "active_power": [
        ("exact_active_power", lambda d: re.fullmatch(r"\s*active power\s*", d)),
        ("power_output", lambda d: "power" in d and "output" in d),
        # "active power" is a SUBSTRING of "reactive power", which on the real
        # archive tied 12 channels in Farm A and 11 in Farm C by dragging every
        # reactive_power_<n> into the match. Require a word boundary and
        # explicitly refuse a preceding "re".
        ("active_power_phrase", lambda d: bool(ACTIVE_POWER_RE.search(d))),
        # Farm A calls its measured channel simply "Grid power" (kW). Without
        # this it matched nothing and the capability channel won by default.
        ("grid_power", lambda d: "grid power" in d and "reactive" not in d),
    ],
    "wind_speed": [
        ("exact_wind_speed", lambda d: re.fullmatch(r"\s*wind speed\s*", d)),
        ("wind_speed_phrase", lambda d: "wind speed" in d),
    ],
    "rotor_speed": [
        ("exact_rotor_speed", lambda d: re.fullmatch(r"\s*rotor speed\s*", d)),
        ("rotor_rpm", lambda d: "rotor" in d and ("speed" in d or "rpm" in d)),
        ("generator_speed", lambda d: "generator" in d and "speed" in d),
    ],
    # Ordered strictly. The first three identify the MAIN (rotor/slow-shaft)
    # bearing, which is what Base Scorer 2 models. The last rule is a
    # deliberate catch-all for any OTHER bearing -- gearbox, generator,
    # high-speed shaft -- and is reported as a substitute requiring an
    # explicit decision, never as a resolved mapping. On the real archive it
    # silently handed Farm A a "Temperature in gearbox bearing on high speed
    # shaft", which is a different component on the other side of the gearbox.
    "main_bearing_temperature": [
        ("main_bearing_temp", lambda d: "main bearing" in d and "temp" in d),
        ("rotor_bearing_temp", lambda d: "rotor bearing" in d and "temp" in d),
        ("slow_shaft_bearing_temp", lambda d: ("slow shaft" in d or "main shaft" in d)
                                              and "bearing" in d and "temp" in d),
        ("SUBSTITUTE_other_bearing_temp", lambda d: "bearing" in d and "temp" in d),
    ],
    # "Min pitch angle" is a derived aggregate, while "Position rotor blade
    # axis N" is the per-blade pitch position actually measured. Farm C
    # carries both, so the blade-position rule sits alongside the plain
    # pitch-angle rule rather than below the catch-all.
    "pitch_angle": [
        ("exact_pitch_angle", lambda d: re.fullmatch(r"\s*pitch angle\s*", d)),
        ("blade_position", lambda d: "blade" in d and ("position" in d or "axis" in d)
                                     and "temp" not in d),
        ("blade_pitch", lambda d: "pitch" in d and ("angle" in d or "position" in d)),
        ("blade_angle", lambda d: "blade" in d and "angle" in d),
        ("pitch_any", lambda d: "pitch" in d),
    ],
    "ambient_temperature": [
        ("exact_ambient_temp", lambda d: re.fullmatch(r"\s*ambient temperature\s*", d)),
        ("outdoor_temp", lambda d: ("outdoor" in d or "outside" in d) and "temp" in d),
        ("ambient_any", lambda d: "ambient" in d and "temp" in d),
    ],
}

# A counter channel (kWh totalisers and the like) is a cumulative register,
# never an instantaneous reading, so it can never satisfy these signals.
EXCLUDE_IF_COUNTER = True

# is_counter is not always set even when the channel plainly is one: Farm A
# carries "Active power - generator connected in delta" in Wh. The unit
# settles it -- energy is not power.
ENERGY_UNITS = {"wh", "kwh", "mwh", "varh", "kvarh", "mvarh"}

# A modelled capability, not a measurement. "Possible power" is standard wind
# availability terminology (IEC 61400-26) for the power a turbine COULD have
# produced at the current wind -- it is a smooth function of wind speed, so a
# turbine that is underperforming shows NO deviation in it. That is precisely
# the anomaly the detector exists to find. Farm A's dictionary offers both
# "Possible grid active power" and "Grid power"; the phrase rule matched the
# first. Demote these so a measured channel wins, and refuse to resolve
# silently to one when it is all that is left.
CAPABILITY_WORDS = ("possible", "potential", "available", "theoretical",
                    "estimated", "expected", "reference", "setpoint",
                    "set point", "demanded", "nominal", "rated")
POWER_SIGNALS_REJECTING_ENERGY = {"active_power"}

CANDIDATE_DELIMITERS = [";", ",", "\t", "|"]


def sniff_delimiter(path):
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            header = f.readline()
    except OSError:
        return ";"
    best, best_count = ";", -1
    for d in CANDIDATE_DELIMITERS:
        n = header.count(d)
        if n > best_count:
            best, best_count = d, n
    return best


# Signatures of text that has been through a wrong encoding at some point.
# "ï¿½" is U+FFFD's UTF-8 bytes read as Western-8bit: the original character
# is GONE and cannot be recovered from the file. "Â°"/"Ã…"/"Ã©" are UTF-8 read
# as cp1252, which is reversible but still means we picked the wrong codec.
MOJIBAKE_MARKERS = ("ï¿½", "Â°", "Ã‚", "Ã©", "Ã¤", "Ã¶", "Ã¼")

UNIT_UNREADABLE = "UNREADABLE_IN_SOURCE"

# Only ever a SUGGESTION printed next to a destroyed unit, for the operator to
# confirm. Temperatures are degC and angles are deg; conflating them is how a
# wrong unit reaches the C0 map.
LIKELY_UNIT = {
    "ambient_temperature": "degC",
    "main_bearing_temperature": "degC",
    "pitch_angle": "deg",
    "rotor_speed": "rpm",
    "wind_speed": "m/s",
    "active_power": "kW",
}


def has_mojibake(text):
    return any(marker in text for marker in MOJIBAKE_MARKERS)


def entry_label(entry):
    """A one-line label for a signal map entry, whatever shape it is.

    There are four shapes: a plain column, an average over redundant channels
    (derived_from, NO column key), an operator override, and a ratified
    not_available declaration. Code that assumed every entry had a "column"
    crashed on the second one the moment --average-ties actually averaged
    something -- which is to say, on Farm B, on the operator's machine, after
    the tool had already printed Farm A and looked fine."""
    if entry.get("not_available"):
        return "NOT AVAILABLE (ratified)"
    if "derived_from" in entry:
        return "mean(%s)" % ", ".join(entry["derived_from"])
    return entry.get("column", "?")


def clean_unit(unit):
    """Return (unit, raw_or_None). A unit whose characters were destroyed in
    the source file must not be written into the C0 signal map as if it were
    real -- C0 requires a unit, and 'ï¿½C' is not one. Flag it instead so the
    operator declares it with --unit-override."""
    if unit and (has_mojibake(unit) or "�" in unit):
        return UNIT_UNREADABLE, unit
    return unit, None


def read_dictionary(path):
    """Read feature_description.csv. Encoding is not guaranteed: the degree
    sign in the unit column comes through mangled under UTF-8, so try the
    Windows-Western fallback that produced it before giving up on bytes."""
    delimiter = sniff_delimiter(path)
    rows, encoding_used = None, None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(path, newline="", encoding=encoding) as f:
                candidate_rows = list(csv.DictReader(f, delimiter=delimiter))
        except (UnicodeDecodeError, OSError):
            continue
        # A decode can succeed and still be wrong: U+FFFD in the text means the
        # bytes were not this encoding. Keep the result as a fallback but try
        # the next candidate.
        #
        # U+FFFD alone is not a sufficient test. CARE v6's Farm A dictionary
        # has the degree sign ALREADY DESTROYED in the file -- it literally
        # stores the UTF-8 bytes of U+FFFD (EF BF BD). Decoding those as
        # cp1252 yields the three ordinary characters "\u00ef\u00bf\u00bd", which contain no
        # U+FFFD, so the clean-decode test passed and the unit "\u00ef\u00bf\u00bdC" was
        # written into the C0 signal map as if it were real. Look for the
        # mojibake signature too.
        blob = "".join(str(v) for r in candidate_rows for v in r.values() if v)
        if "\ufffd" not in blob and not has_mojibake(blob):
            rows, encoding_used = candidate_rows, encoding
            break
        if rows is None:
            note = "contains U+FFFD" if "\ufffd" in blob else "contains mojibake"
            rows, encoding_used = candidate_rows, "%s (%s)" % (encoding, note)
    if rows is None:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            rows = list(csv.DictReader(f, delimiter=delimiter))
        encoding_used = "utf-8/replace"
    return rows, delimiter, encoding_used


def parse_stats_types(raw):
    """statistics_type holds a comma-separated list inside a semicolon file,
    e.g. `maximum,minimum,average,std_dev`."""
    if not raw:
        return []
    return [t.strip().lower() for t in raw.split(",") if t.strip()]


STAT_SUFFIX = {"average": "avg", "maximum": "max", "minimum": "min", "std_dev": "std"}


def column_names_for(sensor_name, stats_types):
    """Reconstruct the real column names. A channel with a single statistic
    appears bare in some farms and suffixed in others, so emit both and let
    the caller keep whichever exists in the data."""
    if not stats_types:
        return [sensor_name]
    names = []
    for t in stats_types:
        suffix = STAT_SUFFIX.get(t)
        if suffix:
            names.append("%s_%s" % (sensor_name, suffix))
    if len(stats_types) == 1:
        names.append(sensor_name)
    return names


def truthy(value):
    return str(value).strip().lower() in ("true", "1", "yes")


def match_signals(entries):
    """Return {signal: [candidate, ...]} ordered by rule priority."""
    found = defaultdict(list)
    for entry in entries:
        desc = (entry.get("description") or "").strip().lower()
        if not desc:
            continue
        if EXCLUDE_IF_COUNTER and truthy(entry.get("is_counter")):
            continue
        unit = (entry.get("unit") or "").strip().lower()
        for signal, rules in SIGNAL_RULES.items():
            if signal in POWER_SIGNALS_REJECTING_ENERGY and unit in ENERGY_UNITS:
                continue
            for priority, (rule_name, test) in enumerate(rules):
                try:
                    hit = test(desc)
                except Exception:
                    hit = False
                if hit:
                    # A unit destroyed in the source file must not reach the C0
                    # map looking like a real unit. Flag it here, at the single
                    # point where dictionary units enter, so the tie comparison
                    # and every downstream write see the same flagged value.
                    unit_value, unit_raw = clean_unit(entry.get("unit"))
                    lowered = (entry.get("description") or "").lower()
                    found[signal].append({
                        "sensor_name": entry.get("sensor_name"),
                        "description": entry.get("description"),
                        "unit": unit_value,
                        "_unit_raw_in_source": unit_raw,
                        "is_angle": truthy(entry.get("is_angle")),
                        "statistics_type": entry.get("statistics_type"),
                        "columns": column_names_for(
                            entry.get("sensor_name"),
                            parse_stats_types(entry.get("statistics_type"))),
                        "matched_rule": rule_name,
                        "rule_priority": priority,
                        "is_capability_estimate": any(
                            w in lowered for w in CAPABILITY_WORDS),
                    })
                    break
    for signal in found:
        found[signal].sort(key=lambda c: (c["rule_priority"], c["sensor_name"] or ""))
    return found


def farm_matches(prefix, farm):
    """Does an operator flag's [FARM:] prefix select this farm?

    This was a substring test, which is wrong in a way that cost real work:
    the farm names are "Wind Farm A/B/C", and the letter "a" is a substring
    of "wind farm b" -- the word FARM contains an a. So --header-override
    "A:wind_speed=..." silently applied to all three farms, overwriting the
    ratified Farm C pick, and every downstream regime bin for two farms
    would have been computed from the wrong farm's wind channel. Nothing
    errored; the summary just quietly said wind_speed_3_avg three times.

    Match the farm's identifier instead: the trailing token of the name
    ("A"), or the full name."""
    if prefix is None:
        return True
    prefix = prefix.strip().lower()
    farm = (farm or "").strip().lower()
    if not prefix:
        return False
    if prefix == farm:
        return True
    tokens = farm.split()
    return bool(tokens) and prefix == tokens[-1]


def header_candidates(farm_dir, stem):
    """Column names in this farm's case files starting with `stem`.

    Active power and wind speed carry semantic names in CARE v6
    (power_<n>_avg, wind_speed_<n>_avg) rather than sensor_<n> dictionary
    entries, so when the dictionary cannot answer, the case-file header can.
    Reporting these turns a round trip to the operator into a line of output
    they can act on immediately."""
    for pattern in (os.path.join(farm_dir, "datasets", "*.csv"),
                    os.path.join(farm_dir, "datasets", "*", "*.csv")):
        files = sorted(glob.glob(pattern))
        if not files:
            continue
        try:
            delimiter = sniff_delimiter(files[0])
            with open(files[0], newline="", encoding="utf-8", errors="replace") as f:
                header = next(csv.reader(f, delimiter=delimiter), []) or []
        except (OSError, StopIteration):
            return []
        return [c for c in header if c.lower().startswith(stem)]
    return []


def excluded_for(exclusions, farm, signal):
    """Sensor names the operator has ruled out for this farm and signal."""
    out = set()
    for (farm_prefix, sig), names in exclusions.items():
        if sig == signal and farm_matches(farm_prefix, farm):
            out |= names
    return out


def _pick_for(picks, farm_key, signal):
    for (farm_prefix, sig), sensor in picks.items():
        if sig != signal:
            continue
        if farm_matches(farm_prefix, farm_key):
            return sensor
    return None


def _describe(c):
    return "%s = %r" % (c["sensor_name"], (c["description"] or "").strip())


def choose(candidates, average_ties=False, pick_sensor=None):
    """Pick only when unambiguous: a single candidate at the best priority,
    matched by a rule that actually identifies the signal.

    With average_ties, a tie between channels that all describe the SAME
    quantity (three anemometers, two rotor bearings, three blade axes) is
    resolved by averaging them, per the PI decision of 2026-08-15. A
    SUBSTITUTE tie is never averaged: those channels describe DIFFERENT
    components, and averaging a gearbox bearing with a generator bearing
    would manufacture a quantity that no sensor measures."""
    if not candidates:
        return None, "no channel in the dictionary matched this signal"

    # An explicit operator pick outranks both the rule order and averaging.
    # Some ties are between DIFFERENT measurement points rather than redundant
    # sensors -- Farm C offers active power at the ABB-LS, the grid-side
    # converter, the converter and the HV grid -- and averaging those would
    # invent a quantity. Only a human can say which point the study means.
    if pick_sensor:
        chosen = [c for c in candidates if c["sensor_name"] == pick_sensor]
        if not chosen:
            return None, ("operator picked %r but no candidate for this signal has "
                          "that sensor_name; candidates were: %s"
                          % (pick_sensor, "; ".join(_describe(c) for c in candidates)))
        chosen[0] = dict(chosen[0], matched_rule=chosen[0]["matched_rule"] + "+operator_pick")
        return chosen[0], None

    # A measured channel always beats a modelled capability, whatever the rule
    # order says. If capability channels are ALL that matched, do not resolve
    # silently -- say so, the way a substitute bearing is said.
    measured = [c for c in candidates if not c.get("is_capability_estimate")]
    if measured:
        candidates = measured
    elif candidates:
        return None, ("every candidate is a modelled capability, not a measurement "
                      "(%s). 'Possible/available power' is what the turbine COULD "
                      "have produced at this wind, so an underperforming turbine "
                      "shows no deviation in it. Pick a measured channel with "
                      "--pick, or declare this signal --not-available: %s"
                      % (", ".join(sorted({w for c in candidates for w in
                                           CAPABILITY_WORDS
                                           if w in (c["description"] or "").lower()})),
                         "; ".join(_describe(c) for c in candidates)))

    best = candidates[0]["rule_priority"]
    tied = [c for c in candidates if c["rule_priority"] == best]

    if tied[0]["matched_rule"].startswith("SUBSTITUTE_"):
        return None, ("no exact match; %d substitute channel(s) found via %r, which "
                      "identify a DIFFERENT component and must be accepted explicitly "
                      "or rejected: %s"
                      % (len(tied), tied[0]["matched_rule"],
                         "; ".join(_describe(c) for c in tied)))
    if len(tied) > 1:
        if average_ties:
            units = {(c["unit"] or "").strip().lower() for c in tied}
            if len(units) > 1:
                return None, ("%d channels tie at rule %r but their units differ (%s) "
                              "-- averaging them would be meaningless: %s"
                              % (len(tied), tied[0]["matched_rule"], sorted(units),
                                 "; ".join(_describe(c) for c in tied)))
            return {"_average_of": tied}, None
        return None, ("%d channels tie at rule %r -- a human must choose: %s"
                      % (len(tied), tied[0]["matched_rule"],
                         "; ".join(_describe(c) for c in tied)))
    return tied[0], None


def run(args):
    dict_paths = sorted(glob.glob(
        os.path.join(args.workdir, "**", "feature_description.csv"), recursive=True))
    if not dict_paths:
        print("no feature_description.csv found under %s" % args.workdir, file=sys.stderr)
        return 3
    os.makedirs(args.output_dir, exist_ok=True)

    profiler_picks = {}
    if args.profiles_dir:
        summary = os.path.join(args.profiles_dir, "identification_summary.json")
        if os.path.isfile(summary):
            with open(summary, encoding="utf-8") as f:
                profiler_picks = {k: v.get("top_pick", {})
                                  for k, v in json.load(f).get("farms", {}).items()}

    picks = {}
    for spec in (args.pick or []):
        if "=" not in spec:
            continue
        key, sensor = spec.split("=", 1)
        if ":" in key:
            farm_prefix, signal = key.split(":", 1)
            picks[(farm_prefix.strip().lower(), signal.strip())] = sensor.strip()
        else:
            picks[(None, key.strip())] = sensor.strip()

    exclusions = {}
    for spec in (args.exclude_sensor or []):
        if "=" not in spec:
            continue
        key, sensors = spec.split("=", 1)
        if ":" in key:
            farm_prefix, signal = key.split(":", 1)
        else:
            farm_prefix, signal = None, key
        names = {n.strip() for n in sensors.split(",") if n.strip()}
        exclusions.setdefault((farm_prefix and farm_prefix.strip().lower(),
                               signal.strip()), set()).update(names)

    overall = {}
    for path in dict_paths:
        farm = os.path.basename(os.path.dirname(path))
        farm_dir = os.path.dirname(path)
        farm_key = farm.strip().lower()
        entries, delimiter, encoding_used = read_dictionary(path)
        matched = match_signals(entries)

        signal_map, report = {}, {}
        for signal in SIGNAL_RULES:
            candidates = matched.get(signal, [])
            # Drop channels the operator has ruled out. Farm C's rotor speed
            # matched four channels: sensor_144/145 ("Rotor speed 1/2",
            # r=1.0000 with each other, median 9.8 -- the real rotor) and
            # sensor_146/147 ("Rotor speed gearbox main shaft 1/2", median 80,
            # minimum -55, and correlated with each other at only r=0.21).
            # Averaging all four moved the median from 9.8 to 46.6. --pick
            # cannot express "these two, averaged", so exclusion is the tool
            # that fits: it removes the bad members and lets the good ones
            # average as ratified.
            dropped = []
            ruled_out = excluded_for(exclusions, farm, signal)
            if ruled_out:
                dropped = [c for c in candidates if c["sensor_name"] in ruled_out]
                candidates = [c for c in candidates
                              if c["sensor_name"] not in ruled_out]
            pick, problem = choose(candidates, args.average_ties,
                                   _pick_for(picks, farm_key, signal))
            report[signal] = {
                "excluded_by_operator": [
                    {"sensor_name": c["sensor_name"],
                     "description": c["description"]} for c in dropped],
                "n_candidates": len(candidates),
                "candidates": candidates,
                "problem": problem,
            }
            if problem and signal in ("active_power", "wind_speed"):
                report[signal]["hint"] = (
                    "Active power and wind speed already carry semantic column "
                    "names in CARE v6 (power_<n>_*, wind_speed_<n>_*). If the "
                    "dictionary has no sensor_<n> entry for them, read the column "
                    "name straight from the case-file header instead.")
            if pick and "_average_of" in pick:
                members = pick["_average_of"]
                cols = []
                for m in members:
                    avg = [c for c in m["columns"] if c.endswith("_avg")]
                    cols.append((avg or m["columns"])[0])
                signal_map[signal] = {
                    "derived_from": cols,
                    "unit": members[0]["unit"],
                    "derivation": ("arithmetic mean of %d redundant channels measuring "
                                   "the same quantity (PI decision 2026-08-15)"
                                   % len(cols)),
                    "_source": "feature_description.csv",
                    "_matched_rule": members[0]["matched_rule"],
                    "_members": [{"sensor_name": m["sensor_name"],
                                  "description": m["description"]} for m in members],
                }
            elif pick:
                avg_cols = [c for c in pick["columns"] if c.endswith("_avg")]
                signal_map[signal] = {
                    "column": (avg_cols or pick["columns"])[0],
                    "unit": pick["unit"],
                    "_source": "feature_description.csv",
                    "_sensor_name": pick["sensor_name"],
                    "_description": pick["description"],
                    "_matched_rule": pick["matched_rule"],
                    "_all_columns_for_this_sensor": pick["columns"],
                }

        cross = {}
        for signal, guess in (profiler_picks.get(farm) or {}).items():
            truth = signal_map.get(signal, {}).get("column")
            if truth and guess:
                base_t = re.sub(r"_(avg|max|min|std)$", "", truth)
                base_g = re.sub(r"_(avg|max|min|std)$", "", guess)
                cross[signal] = {
                    "dictionary": truth,
                    "profiler_guess": guess,
                    "agree": base_t == base_g,
                }

        for spec in (args.header_override or []):
            if "=" not in spec:
                continue
            key, column = spec.split("=", 1)
            if ":" in key:
                farm_prefix, signal = key.split(":", 1)
                if not farm_matches(farm_prefix, farm):
                    continue
            else:
                signal = key
            signal = signal.strip()
            if signal not in SIGNAL_RULES:
                continue
            signal_map[signal] = {
                "column": column.strip(),
                "unit": args.override_unit or "<CONFIRM>",
                "_source": "operator --header-override (not in feature_description.csv)",
            }
            report.setdefault(signal, {})["overridden_by_operator"] = column.strip()

        # Units whose characters were destroyed in the source file. Fixing
        # these by hand in the JSON afterwards is error-prone, so accept them
        # as a declaration on the command line.
        for spec in (args.unit_override or []):
            if "=" not in spec:
                continue
            key, unit = spec.split("=", 1)
            if ":" in key:
                farm_prefix, signal = key.split(":", 1)
                if not farm_matches(farm_prefix, farm):
                    continue
            else:
                signal = key
            signal = signal.strip()
            if signal in signal_map:
                previous = signal_map[signal].get("unit")
                signal_map[signal]["unit"] = unit.strip()
                signal_map[signal]["_unit_source"] = (
                    "operator --unit-override (was %r)" % previous)
                report.setdefault(signal, {})["unit_overridden_by_operator"] = unit.strip()

        # A signal this farm genuinely does not carry. C0 FAILs on silent
        # absence and accepts an explicit ratified declaration, so emit the
        # declaration here rather than making the operator hand-edit JSON.
        for spec in (args.not_available or []):
            if "=" not in spec:
                continue
            key, reason = spec.split("=", 1)
            if ":" in key:
                farm_prefix, signal = key.split(":", 1)
                if not farm_matches(farm_prefix, farm):
                    continue
            else:
                signal = key
            signal = signal.strip()
            if signal not in SIGNAL_RULES:
                continue
            if signal in signal_map and not args.force_not_available:
                print("  REFUSING to declare %r not available on %s: it resolved to "
                      "%s. Pass --force-not-available if that is really intended."
                      % (signal, farm, entry_label(signal_map[signal])))
                continue
            signal_map[signal] = {
                "not_available": True,
                "reason": reason.strip(),
                "ratified_by": args.ratified_by,
                "ratified_on": args.ratified_on,
                "_source": "operator --not-available",
            }
            report.setdefault(signal, {})["declared_not_available"] = reason.strip()

        missing = [s for s in SIGNAL_RULES if s not in signal_map]
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", farm)
        with open(os.path.join(args.output_dir, "feature_dictionary_%s.json" % safe),
                  "w", encoding="utf-8") as f:
            json.dump({"farm": farm, "source": os.path.abspath(path),
                       "delimiter": delimiter, "encoding_used": encoding_used,
                       "n_entries": len(entries), "entries": entries},
                      f, indent=2, ensure_ascii=False)
        with open(os.path.join(args.output_dir, "signal_map_%s.json" % safe),
                  "w", encoding="utf-8") as f:
            json.dump(signal_map, f, indent=2, ensure_ascii=False)
        with open(os.path.join(args.output_dir, "signal_map_report_%s.json" % safe),
                  "w", encoding="utf-8") as f:
            json.dump({
                "farm": farm,
                "n_dictionary_entries": len(entries),
                "signals_resolved": sorted(signal_map),
                "signals_unresolved": missing,
                "per_signal": report,
                "cross_validation_vs_profiler": cross,
                "note": ("Entries marked with a leading underscore are provenance, not "
                         "C0 fields. Units come from the dictionary verbatim -- check "
                         "them before use; a mangled degree sign means the source file "
                         "is not UTF-8."),
            }, f, indent=2, ensure_ascii=False)

        overall[farm] = {
            "n_dictionary_entries": len(entries),
            "resolved": {s: entry_label(signal_map[s]) for s in sorted(signal_map)},
            "unresolved": missing,
            "cross_validation": cross,
        }

        print("\n=== %s (%d dictionary entries, %s, %s) ==="
              % (farm, len(entries), delimiter and repr(delimiter), encoding_used))
        unreadable_units = []
        for signal in SIGNAL_RULES:
            if signal in signal_map:
                m = signal_map[signal]
                if m.get("not_available"):
                    print("  %-26s NOT AVAILABLE (ratified by %s on %s): %s"
                          % (signal, m.get("ratified_by", "?"),
                             m.get("ratified_on", "?"), m.get("reason", "")))
                    continue
                if m.get("unit") == UNIT_UNREADABLE:
                    unreadable_units.append(signal)
                if "derived_from" in m:
                    print("  %-26s mean(%s) %-8s %d redundant channels"
                          % (signal, ", ".join(m["derived_from"]), m["unit"],
                             len(m["derived_from"])))
                    continue
                agree = cross.get(signal, {}).get("agree")
                mark = "" if agree is None else ("  [profiler agrees]" if agree
                                                 else "  [profiler DISAGREED: %s]"
                                                 % cross[signal]["profiler_guess"])
                # An operator override carries no dictionary description, since
                # by definition the dictionary did not name the signal.
                description = m.get("_description") or m.get("_source") or ""
                print("  %-26s %-16s %-8s %s%s"
                      % (signal, m.get("column", "?"), m.get("unit", "?"),
                         description, mark))
            else:
                print("  %-26s -- %s" % (signal, report[signal]["problem"]))
                # Do not just say "take it from the header" -- read the header
                # and say which columns are actually there, with the exact flag
                # to paste. The alternative is another round trip to a person
                # who has already done enough of them.
                if signal in ("active_power", "wind_speed"):
                    stem = "power" if signal == "active_power" else "wind_speed"
                    found = header_candidates(farm_dir, stem)
                    avg = [c for c in found if c.lower().endswith("_avg")]
                    shortlist = avg or found
                    if shortlist:
                        print("      case-file header offers: %s"
                              % ", ".join(shortlist[:8])
                              + (" (+%d more)" % (len(shortlist) - 8)
                                 if len(shortlist) > 8 else ""))
                        print('      --header-override "%s:%s=%s" --override-unit "%s"'
                              % (farm.split()[-1], signal, shortlist[0],
                                 "kW" if signal == "active_power" else "m/s"))
                    else:
                        print("      no %s* column found in this farm's case files "
                              "either" % stem)

        # C0 requires a unit, and Phase 5.1's cross-farm consistency check
        # reads it. A unit destroyed in the source file has to be declared.
        if unreadable_units:
            print("      unit unreadable in the source file for: %s"
                  % ", ".join(unreadable_units))
            for signal in unreadable_units:
                # Do NOT suggest degC for everything. Pitch angle is degrees;
                # suggesting degC here would have put a wrong unit into the C0
                # map, in the one place whose entire job is recording units.
                guess = LIKELY_UNIT.get(signal, "CONFIRM")
                print('      --unit-override "%s:%s=%s"   <- confirm the unit'
                      % (farm.split()[-1], signal, guess))

    with open(os.path.join(args.output_dir, "signal_map_summary.json"),
              "w", encoding="utf-8") as f:
        json.dump({"generated_at_utc": datetime.now(timezone.utc).isoformat(),
                   "source": "CARE v6 feature_description.csv (archive ground truth)",
                   "farms": overall,
                   "cli_invocation": " ".join(sys.argv)}, f, indent=2, ensure_ascii=False)

    unresolved_any = {f: v["unresolved"] for f, v in overall.items() if v["unresolved"]}
    if unresolved_any:
        print("\nUNRESOLVED signals remain: %s" % json.dumps(unresolved_any, ensure_ascii=False))
        print("For those, and only those, fall back to sensor_identification_profile.py "
              "and mark the result unratified.")
    print("\nWrote %s" % args.output_dir, file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdir", required=True, help="Extracted CARE v6 root")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--pick", action="append", metavar="[FARM:]SIGNAL=SENSOR",
                    help="Resolve a tie explicitly, e.g. 'C:active_power=power_6'. "
                         "Use when the tied channels are different measurement "
                         "points rather than redundant sensors. Repeatable.")
    ap.add_argument("--average-ties", action="store_true",
                    help="Resolve a tie between channels measuring the same quantity "
                         "by averaging them (emitted as C0 derived_from). Never "
                         "applied to SUBSTITUTE ties.")
    ap.add_argument("--header-override", action="append", metavar="[FARM:]SIGNAL=COLUMN",
                    help="Map a signal the dictionary does not name, e.g. "
                         "'A:wind_speed=wind_speed_3_avg'. Repeatable.")
    ap.add_argument("--override-unit", help="Unit to record for --header-override entries")
    ap.add_argument("--unit-override", action="append", metavar="[FARM:]SIGNAL=UNIT",
                    help="Declare the unit for a signal whose dictionary unit is "
                         "unreadable (CARE v6 Farm A stores a destroyed degree sign). "
                         "Repeatable.")
    ap.add_argument("--not-available", action="append", metavar="[FARM:]SIGNAL=REASON",
                    help="Declare that this farm carries no such signal, emitting the "
                         "ratified not_available block C0 requires. Repeatable.")
    ap.add_argument("--exclude-sensor", action="append",
                    metavar="[FARM:]SIGNAL=SENSOR[,SENSOR...]",
                    help="Remove named channels from a signal's candidates before "
                         "choosing, so the remaining ones resolve or average "
                         "normally. Repeatable.")
    ap.add_argument("--force-not-available", action="store_true",
                    help="Allow --not-available to override a signal that did resolve")
    ap.add_argument("--ratified-by", default="PI",
                    help="Recorded in --not-available declarations")
    ap.add_argument("--ratified-on", default="2026-08-15",
                    help="Recorded in --not-available declarations")
    ap.add_argument("--profiles-dir",
                    help="sensor_profile_out/ from the statistical profiler, to "
                         "cross-validate the dictionary against the guesses")
    args = ap.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
