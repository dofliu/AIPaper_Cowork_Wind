#!/usr/bin/env python3
"""
The physically possible range of each core signal. ONE definition.

WHY THIS FILE EXISTS
--------------------
base_scorer_md2022.py filters readings outside physical possibility, and
check_unit_consistency.py flags a signal whose observed span leaves it. They
had separate copies of the bounds and the copies disagreed: the scorer
allowed rotor speed down to -1.0 while the checker demanded >= 0.0, so a
farm could pass the filter and then be reported as implausible by the very
next tool, on values the first tool had deliberately kept. Two tools
disagreeing about what is possible is worse than either being wrong alone,
because it makes the whole gate unreadable.

WHAT THE BOUNDS ARE FOR
-----------------------
Excluding the IMPOSSIBLE, not the unusual. A bearing at 850 C is a fault
code; a bearing at 95 C is a bad day and must survive. Set them wide.

active_power is deliberately absent. Its scale is a property of the turbine
and of how the publisher chose to express it -- CARE v6 ships it per-unit,
another archive would ship kW -- so there is no physical bound to test
against. An earlier version assumed per-unit and bounded it to [-0.5, 1.5];
against real kW values that rejected EVERY row and left nothing scored.
check_unit_consistency detects the normalisation separately, which is where
that question belongs.

No third-party dependencies beyond the Python 3 standard library.
"""

# signal -> (low, high, expected_unit)
PHYSICAL_RANGE = {
    "wind_speed": (0.0, 60.0, "m/s"),
    # CARE v6 Farm C's rotor speed channels read down to -5.5 when the rotor
    # is stopped -- a sensor offset, not a fault code, and small enough to be
    # harmless. Admit it rather than reject 1% of the farm's stopped rows,
    # but keep the ceiling tight enough that a rad/s or gearbox-shaft channel
    # still fails.
    "rotor_speed": (-6.0, 60.0, "rpm"),
    "main_bearing_temperature": (-40.0, 150.0, "degC"),
    "pitch_angle": (-20.0, 120.0, "deg"),
    "ambient_temperature": (-50.0, 60.0, "degC"),
}


def bounds(signal):
    """(low, high) for the scorer's filter, or None if unbounded."""
    entry = PHYSICAL_RANGE.get(signal)
    return (entry[0], entry[1]) if entry else None


def expected_unit(signal):
    entry = PHYSICAL_RANGE.get(signal)
    return entry[2] if entry else None
