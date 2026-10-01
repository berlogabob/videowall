"""What the wall shows at a given second: the TV's playlist rules applied to wall slides.

in_window, link_events and occurrences are copied from openlabtwin (scripts/tv.py, scripts/export.py @2eda801),
so a slide linked to a schedule activity takes the same slot on the TV and the wall. Like the TV page, the loop
runs from the epoch and an announcement shows while t % every < its length, so both switch in the same second.
"""
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

TZ = ZoneInfo("Europe/Lisbon")
STILL_SECONDS, MOSAIC_SECONDS = 10, 30


def occurrences(a, first, last):
    """(start, end) local datetimes of an activity between two dates. Repeats run on Lisbon wall-clock time."""
    start = datetime.fromisoformat(a["starts_at"]).astimezone(TZ).replace(tzinfo=None)
    length = datetime.fromisoformat(a["ends_at"]) - datetime.fromisoformat(a["starts_at"])
    if a.get("rrule"):
        starts = rrulestr(a["rrule"], dtstart=start).between(datetime.combine(first, dtime.min),
                                                            datetime.combine(last, dtime.max), inc=True)
    else:
        starts = [start] if first <= start.date() <= last else []
    skip = set(a.get("exdates") or [])
    return [(s, s + length) for s in starts if s.date().isoformat() not in skip]


def in_window(s, day, clock=None):
    """Active, inside its dates, and (given the clock, HH:MM) inside its times of day."""
    d = day.isoformat()
    if not (s.get("active", True) and (not s.get("starts_on") or s["starts_on"] <= d)
            and (not s.get("ends_on") or s["ends_on"] >= d)):
        return False
    start, end = (s.get("from_time") or "")[:5], (s.get("to_time") or "")[:5]
    return clock is None or ((not start or start <= clock) and (not end or clock < end))


def in_sleep(sleep, t):
    if not sleep:
        return False
    try:
        start, end = (dtime.fromisoformat(sleep[k]) for k in ("from", "to"))
    except (KeyError, TypeError, ValueError):
        return False
    clock = datetime.fromtimestamp(t, TZ).time()
    return start <= clock < end if start <= end else clock >= start or clock < end


def link_events(slides, activities, day):
    """Slides linked to a schedule activity take that activity's slot today as their dates and times; with no
    approved occurrence today (cancelled, deleted, another day) they don't play."""
    acts = {a["id"]: a for a in activities}
    out = []
    for s in slides:
        if not s.get("activity_id"):
            out.append(s)
            continue
        a = acts.get(s["activity_id"])
        slot = occurrences(a, day, day)[:1] if a and a.get("status", "approved") == "approved" else []
        if not slot:
            out.append(s | {"active": False})
            continue
        start, end = slot[0]
        out.append(s | {"starts_on": day.isoformat(), "ends_on": day.isoformat(), "from_time": f"{start:%H:%M:%S}",
                        "to_time": f"{end:%H:%M:%S}" if end.date() == start.date() else "23:59:59"})
    return out


def slide_len(s, durations):
    """Seconds on the wall: its own seconds, else a videowall video's length, else 10 (still) / 30 (mosaic)."""
    if s.get("seconds"):
        return s["seconds"]
    if s["mode"] == "videowall":
        return durations.get((s.get("media_names") or [""])[0]) or STILL_SECONDS
    return MOSAIC_SECONDS


def resolve(state, slides, activities, t, durations, ready):
    """Wall-wide answer for second t: (level, slide, at, until). Levels in order: blackout, stopped, now,
    takeover, announcement, loop, defaults (the per-screen setup overlay sits above all, in the app).
    ready(slide) says whether its tiles (or a poster) exist; not-ready slides are skipped."""
    if state.get("blackout"):
        return ("blackout", None, 0, None)
    if in_sleep(state.get("sleep"), t):
        return ("sleep", None, 0, None)
    if not state.get("playing", True):
        return ("stopped", None, 0, None)
    now = state.get("now")
    if now and (not state.get("now_until") or t < state["now_until"]) and ready(now):
        return ("now", now, state.get("now_at") or 0, state.get("now_until"))
    dt = datetime.fromtimestamp(t, TZ)
    day, clock = dt.date(), dt.strftime("%H:%M")
    ordered = sorted(link_events(slides, activities, day), key=lambda s: (s.get("position") or 0, s.get("id") or 0))
    live = [s for s in ordered if in_window(s, day, clock) and ready(s)]
    takeover = [s for s in live if s.get("takeover")]
    pool = takeover or live
    for s in pool:
        every, length = s.get("every_seconds"), slide_len(s, durations)
        if every and t % every < length:
            start = t - t % every
            return ("announcement", s, start, start + length)
    loop = [s for s in pool if not s.get("every_seconds")]
    if not loop:
        return ("defaults", None, 0, None)
    anchor = 0.0
    starts = [s["from_time"] for s in takeover if s.get("from_time")]
    if takeover and starts:  # a takeover starts its loop at its own from_time, so 17:00:00 shows its first item
        anchor = datetime.combine(day, dtime.fromisoformat(min(starts))).replace(tzinfo=TZ).timestamp()
    lens = [slide_len(s, durations) for s in loop]
    pos, acc = (t - anchor) % sum(lens), 0
    for s, length in zip(loop, lens):
        if pos < acc + length:
            start = t - (pos - acc)
            return ("takeover" if takeover else "loop", s, start, start + length)
        acc += length


def describe(level, slide, until):
    """For the office's status line."""
    if level in ("blackout", "sleep", "stopped", "defaults"):
        return {"blackout": "Blackout", "sleep": "Night sleep", "stopped": "Stopped", "defaults": "Test mode (defaults)"}[level]
    name = slide.get("text") if slide.get("text") and not slide.get("media_names") else (
        slide.get("title") or ", ".join(slide.get("media_names") or []) or "all files")
    text = f"{slide['mode'].capitalize()}: {name}"
    if level == "takeover":
        end = (slide.get("to_time") or "")[:5]
        return f"Takeover: {name}" + (f" until {end}" if end else "")
    return ("Announcement: " + name) if level == "announcement" else ("Now: " + text) if level == "now" else text


def timeline(state, slides, activities, t0, hours, durations, ready):
    """Wall-wide schedule over the next hours, sampled at resolve() boundaries."""
    end = t0 + hours * 3600
    rows, t = [], t0
    while t < end and len(rows) < 200:
        level, slide, at, until = resolve(state, slides, activities, t, durations, ready)
        stop = min(until or end, end)
        dt = datetime.fromtimestamp(t, TZ)
        for offset in range(hours // 24 + 2):
            day = dt.date() + timedelta(days=offset)
            sleep = state.get("sleep") or {}
            for key in ("from", "to"):
                if sleep.get(key):
                    boundary = datetime.combine(day, dtime.fromisoformat(sleep[key])).replace(tzinfo=TZ).timestamp()
                    if t < boundary < stop:
                        stop = boundary
            for s in slides:
                for key in ("from_time", "to_time"):
                    if s.get(key):
                        boundary = datetime.combine(day, dtime.fromisoformat(s[key])).replace(tzinfo=TZ).timestamp()
                        if t < boundary < stop:
                            stop = boundary
        if stop <= t:
            stop = min(t + 1, end)
        label = "Test mode" if level == "defaults" else describe(level, slide, until)
        row = {"at": t, "until": stop, "level": level, "label": label}
        # Repeated timed announcements share one row; ordinary adjacent loop items are one loop window.
        previous = next((r for r in reversed(rows) if r["level"] == level and r["label"] == label), None) \
            if level == "announcement" else (rows[-1] if rows else None)
        if previous and previous["level"] == level and previous["label"] == label and (level == "announcement" or previous["until"] == t):
            previous["until"] = stop
        elif level == "takeover" and rows and rows[-1]["level"] == level and rows[-1]["label"] == label and rows[-1]["until"] == t:
            rows[-1]["until"] = stop
        elif level == "loop" and rows and rows[-1]["level"] == level and rows[-1]["label"].startswith("Loop:"):
            rows[-1]["until"] = stop
        elif level == "loop":
            rows.append({"at": t, "until": stop, "level": level,
                         "label": f"Loop: {sum(1 for s in slides if not s.get('takeover') and not s.get('every_seconds'))} entries"})
        else:
            rows.append(row)
        t = stop
    return rows
