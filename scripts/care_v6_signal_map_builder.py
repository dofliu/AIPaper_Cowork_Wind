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
SIGNAL_RULES = {
    "active_power": [
        ("exact_active_power", lambda d: re.fullmatch(r"\s*active power\s*", d)),
        ("power_output", lambda d: "power" in d and "output" in d),
        ("active_power_phrase", lambda d: "active power" in d),
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
    "main_bearing_temperature": [
        ("main_bearing_temp", lambda d: "main bearing" in d and "temp" in d),
        ("rotor_bearing_temp", lambda d: "rotor bearing" in d and "temp" in d),
        ("shaft_bearing_temp", lambda d: "shaft" in d and "bearing" in d and "temp" in d),
        ("any_bearing_temp", lambda d: "bearing" in d and "temp" in d),
    ],
    "pitch_angle": [
        ("exact_pitch_angle", lambda d: re.fullmatch(r"\s*pitch angle\s*", d)),
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


def read_dictionary(path):
    """Read feature_description.csv. Encoding is not guaranteed: the degree
    sign in the unit column comes through mangled under UTF-8, so try the
    Windows-Western fallback that produced it before giving up on bytes."""
    delimiter = sniff_delimiter(path)
    rows, encoding_used = None, None
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            with open(path, newline="", encoding=encoding) as f:
                rows = list(csv.DictReader(f, delimiter=delimiter))
            encoding_used = encoding
            break
        except (UnicodeDecodeError, OSError):
            continue
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
        for signal, rules in SIGNAL_RULES.items():
            for priority, (rule_name, test) in enumerate(rules):
                try:
                    hit = test(desc)
                except Exception:
                    hit = False
                if hit:
                    found[signal].append({
                        "sensor_name": entry.get("sensor_name"),
                        "description": entry.get("description"),
                        "unit": entry.get("unit"),
                        "is_angle": truthy(entry.get("is_angle")),
                        "statistics_type": entry.get("statistics_type"),
                        "columns": column_names_for(
                            entry.get("sensor_name"),
                            parse_stats_types(entry.get("statistics_type"))),
                        "matched_rule": rule_name,
                        "rule_priority": priority,
                    })
                    break
    for signal in found:
        found[signal].sort(key=lambda c: (c["rule_priority"], c["sensor_name"] or ""))
    return found


def choose(candidates):
    """Pick only when unambiguous: a single best-priority candidate."""
    if not candidates:
        return None, "no channel in the dictionary matched this signal"
    best = candidates[0]["rule_priority"]
    tied = [c for c in candidates if c["rule_priority"] == best]
    if len(tied) > 1:
        return None, ("%d channels tie at rule %r (%s) -- a human must choose"
                      % (len(tied), tied[0]["matched_rule"],
                         ", ".join(c["sensor_name"] for c in tied)))
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

    overall = {}
    for path in dict_paths:
        farm = os.path.basename(os.path.dirname(path))
        entries, delimiter, encoding_used = read_dictionary(path)
        matched = match_signals(entries)

        signal_map, report = {}, {}
        for signal in SIGNAL_RULES:
            candidates = matched.get(signal, [])
            pick, problem = choose(candidates)
            report[signal] = {
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
            if pick:
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
            "resolved": {s: signal_map[s]["column"] for s in sorted(signal_map)},
            "unresolved": missing,
            "cross_validation": cross,
        }

        print("\n=== %s (%d dictionary entries, %s, %s) ==="
              % (farm, len(entries), delimiter and repr(delimiter), encoding_used))
        for signal in SIGNAL_RULES:
            if signal in signal_map:
                m = signal_map[signal]
                agree = cross.get(signal, {}).get("agree")
                mark = "" if agree is None else ("  [profiler agrees]" if agree
                                                 else "  [profiler DISAGREED: %s]"
                                                 % cross[signal]["profiler_guess"])
                print("  %-26s %-16s %-8s %s%s"
                      % (signal, m["column"], m["unit"], m["_description"], mark))
            else:
                extra = ""
                if signal in ("active_power", "wind_speed"):
                    extra = ("  (this one is usually a named `%s_<n>_avg` column "
                             "rather than a sensor_<n> entry -- take it from the "
                             "header, not the dictionary)"
                             % ("power" if signal == "active_power" else "wind_speed"))
                print("  %-26s -- %s%s" % (signal, report[signal]["problem"], extra))

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
    ap.add_argument("--profiles-dir",
                    help="sensor_profile_out/ from the statistical profiler, to "
                         "cross-validate the dictionary against the guesses")
    args = ap.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
