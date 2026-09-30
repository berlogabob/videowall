"""Playlist rules: windows, links to schedule activities, precedence, loop maths, takeover, announcements."""
import sys
from datetime import date, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from server.schedule import TZ, describe, in_window, link_events, occurrences, resolve, slide_len

day = date(2026, 10, 1)
s = {"active": True, "starts_on": "2026-10-01", "ends_on": None, "from_time": "09:00:00", "to_time": "17:00:00"}
assert in_window(s, day) and in_window(s, day, "09:00") and not in_window(s, day, "17:00") and not in_window(s, day, "08:59")
assert not in_window(s | {"active": False}, day) and not in_window(s, date(2026, 9, 30))

act = {"id": 7, "status": "approved", "starts_at": "2026-09-29T15:00:00+01:00", "ends_at": "2026-09-29T17:30:00+01:00",
       "rrule": "FREQ=DAILY", "exdates": ["2026-10-02"]}
assert [x[0].hour for x in occurrences(act, day, day)] == [15]
assert occurrences(act, date(2026, 10, 2), date(2026, 10, 2)) == []
linked = link_events([{"id": 1, "activity_id": 7}], [act], day)[0]
assert (linked["from_time"], linked["to_time"], linked["starts_on"]) == ("15:00:00", "17:30:00", "2026-10-01")
assert link_events([{"id": 1, "activity_id": 7}], [act | {"status": "cancelled"}], day)[0]["active"] is False

durations = {"clip.mp4": 25.0}
assert slide_len({"mode": "videowall", "media_names": ["clip.mp4"]}, durations) == 25
assert slide_len({"mode": "videowall", "media_names": ["a.jpg"]}, durations) == 10
assert slide_len({"mode": "mosaic"}, durations) == 30 and slide_len({"mode": "mosaic", "seconds": 5}, durations) == 5

at = lambda hh, mm, ss=0: datetime(2026, 10, 1, hh, mm, ss, tzinfo=TZ).timestamp()
yes = lambda s: True
A = {"id": 1, "mode": "videowall", "media_names": ["a.jpg"], "seconds": 10, "position": 1}
B = {"id": 2, "mode": "mosaic", "media_names": [], "seconds": 20, "position": 2}
T = {"id": 3, "mode": "videowall", "media_names": ["clip.mp4"], "takeover": True, "from_time": "17:00:00",
     "to_time": "18:00:00", "position": 3}
N = {"id": 4, "mode": "videowall", "media_names": ["n.jpg"], "seconds": 5, "every_seconds": 60, "position": 4}
state = {"blackout": False, "playing": True}
slides = [A, B]

# loop from the epoch: A 10 s then B 20 s, period 30
t0 = 30 * 60_000_000  # a multiple of 30
assert resolve(state, slides, [], t0 + 3, durations, yes)[:3] == ("loop", A, t0)
lv, sl, start, end = resolve(state, slides, [], t0 + 12, durations, yes)
assert (lv, sl["id"], start, end) == ("loop", 2, t0 + 10, t0 + 30)
assert resolve(state, slides, [], t0 + 31, durations, yes)[2] == t0 + 30          # wraps
assert resolve(state, slides, [], t0 + 3, durations, lambda s: s is not A)[1] is B  # not ready -> skipped

# precedence
assert resolve(state | {"blackout": True, "now": A}, slides, [], t0, durations, yes)[0] == "blackout"
assert resolve(state | {"playing": False}, slides, [], t0, durations, yes)[0] == "stopped"
now = {"mode": "mosaic", "media_names": []}
assert resolve(state | {"now": now, "now_at": t0}, slides + [T], [], at(17, 30), durations, yes)[:3] == ("now", now, t0)
assert resolve(state | {"now": now, "now_at": t0, "now_until": t0 + 5}, slides, [], t0 + 6, durations, yes)[0] == "loop"
assert resolve(state, [], [], t0, durations, yes)[0] == "defaults"

# takeover: exactly from 17:00:00, its own loop anchored there, only while in its window
assert resolve(state, slides + [T], [], at(16, 59, 59), durations, yes)[0] == "loop"
lv, sl, start, _ = resolve(state, slides + [T], [], at(17, 0), durations, yes)
assert (lv, sl["id"], start) == ("takeover", 3, at(17, 0))
assert resolve(state, slides + [T], [], at(17, 0, 30), durations, yes)[2] == at(17, 0, 25)  # 25 s clip loops
assert resolve(state, slides + [T], [], at(18, 0), durations, yes)[0] == "loop"

# announcements: t % every < length, the loop keeps running underneath; not during a takeover unless takeover
m = at(12, 0)  # a multiple of 60
assert resolve(state, slides + [N], [], m + 2, durations, yes)[:3] == ("announcement", N, m)
assert resolve(state, slides + [N], [], m + 6, durations, yes)[0] == "loop"
assert resolve(state, slides + [T, N], [], at(17, 1, 1), durations, yes)[0] == "takeover"
assert resolve(state, slides + [T, N | {"takeover": True}], [], at(17, 1, 1), durations, yes)[0] == "announcement"

# linked activity gives the slide its slot on the wall too
L = A | {"id": 9, "activity_id": 7, "takeover": True}
assert resolve(state, [L], [act], at(15, 0), durations, yes)[0] == "takeover"
assert resolve(state, [L], [act], at(14, 59), durations, yes)[0] == "defaults"

assert describe("takeover", T, None) == "Takeover: clip.mp4 until 18:00"
assert describe("blackout", None, None) == "Blackout"
print("schedule: ok")
