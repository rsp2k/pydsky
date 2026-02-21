"""Data assembler — merges common + vehicle-specific data into display-ready format."""


def get_data(vehicle, software):
    """Return all data for the given vehicle as display-ready lists.

    Returns dict with keys: verbs, nouns, programs, alarms, routines.
    """
    from pydsky.datacards.data.common import NORMAL_NOUNS, REGULAR_VERBS

    if vehicle == "CM":
        from pydsky.datacards.data.colossus249 import ALARMS, EXTENDED_VERBS, MIXED_NOUNS, PROGRAMS, ROUTINES
    else:
        from pydsky.datacards.data.luminary099 import ALARMS, EXTENDED_VERBS, MIXED_NOUNS, PROGRAMS, ROUTINES

    # Verbs — format as zero-padded code strings
    regular = [{"code": f"{k:02d}", "desc": v} for k, v in sorted(REGULAR_VERBS.items())]
    extended = [{"code": f"{k:02d}", "desc": v} for k, v in sorted(EXTENDED_VERBS.items())]

    # Nouns — merge normal (N00-N39) + mixed (N40+)
    all_nouns = {**NORMAL_NOUNS, **MIXED_NOUNS}
    nouns = []
    for k in sorted(all_nouns):
        n = all_nouns[k]
        nouns.append({
            "code": f"{k:02d}",
            "comp": n.get("comp", 0),
            "desc": n.get("desc", ""),
            "scales": n.get("scales", []),
            "restr": n.get("restr", ""),
        })

    # Programs — sorted by code, grouped by phase
    programs = []
    for k in sorted(PROGRAMS):
        phase, desc = PROGRAMS[k]
        programs.append({"code": f"{k:02d}", "desc": desc, "group": phase})

    # Alarms — 5-digit octal code strings, sorted
    alarms = []
    for k in sorted(ALARMS):
        desc, severity = ALARMS[k]
        alarms.append({"code": f"{k:05o}", "desc": desc, "severity": severity})

    # Routines — sorted by code
    routines = [{"code": f"{k:02d}", "desc": v} for k, v in sorted(ROUTINES.items())]

    return {
        "verbs": {"regular": regular, "extended": extended},
        "nouns": nouns,
        "programs": programs,
        "alarms": alarms,
        "routines": routines,
    }
