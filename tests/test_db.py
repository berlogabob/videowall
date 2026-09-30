"""Supabase row mapping and the fallback when the network fails (no network used)."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from server import db

row = {"blackout": True, "playing": False, "now": {"mode": "mosaic"}, "now_at": "2026-10-01T10:00:00+00:00",
       "now_until": None}
st = db.state_from_row(row)
assert st == {"blackout": True, "playing": False, "now": {"mode": "mosaic"}, "now_at": 1790848800.0, "now_until": None}
back = db.row_from_state(st)
assert back["now_at"].startswith("2026-10-01T10:00:00") and back["now_until"] is None and back["blackout"] is True
assert db.state_from_row({})["playing"] is True

calls = []
db.request = lambda d, method, table, params=None, body=None, headers=None: calls.append((method, table, params, body, headers))
db.heartbeat(("u", "k"), {"seen_at": "x"})
m, table, params, body, headers = calls[-1]
assert (m, table, params["on_conflict"], body[0]["id"]) == ("POST", "wall_status", "id", 1)
assert "merge-duplicates" in headers["Prefer"]
db.set_state(("u", "k"), st)
assert calls[-1][:3] == ("PATCH", "wall_state", {"id": "eq.1"})

# fetch: explicit columns, activities only for linked slides
answers = {"wall_state": [row], "wall_slides": [{"id": 1, "activity_id": 7}, {"id": 2}], "activities": [{"id": 7}]}
seen = []
def fake(d, method, table, params=None, body=None, headers=None):
    seen.append((table, params)); return answers[table]
db.request = fake
state, slides, acts = db.fetch(("u", "k"))
assert state["blackout"] and len(slides) == 2 and acts == [{"id": 7}]
assert all("*" not in p["select"] for _, p in seen) and seen[-1][1]["id"] == "in.(7)"
print("db: ok")
