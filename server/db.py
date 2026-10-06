"""Optional Supabase link (openlabtwin's wall tables), PostgREST over urllib like openlabtwin scripts/db.py.
Service key only: it bypasses RLS, so every select names its columns. No env vars = standalone wall."""
import json, os, shutil, urllib.parse, urllib.request

SLIDE_COLS = ("id,mode,title,media_names,seconds,cycle_seconds,fit,show_title,credits,logo,matte,position,active,"
              "starts_on,ends_on,from_time,to_time,takeover,every_seconds,activity_id")
STATE_COLS = "blackout,playing,now,now_at,now_until,overlay,command,sleep,bezel"
ACT_COLS = "id,title,status,starts_at,ends_at,rrule,exdates"


def connect():
    if not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY")):
        return None
    return os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1", os.environ["SUPABASE_SERVICE_KEY"]


def request(db, method, table, params=None, body=None, headers=None):
    base, key = db
    query = "?" + urllib.parse.urlencode(params, safe=",.()*") if params else ""
    req = urllib.request.Request(f"{base}/{table}{query}", method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"apikey": key, "Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = r.read()
    return json.loads(data) if data else None


def ts(v):
    """timestamptz text -> epoch seconds (None stays None)."""
    from datetime import datetime
    return datetime.fromisoformat(v).timestamp() if v else None


def state_from_row(row):
    return {"blackout": bool(row.get("blackout")), "playing": row.get("playing", True) is not False,
            "now": row.get("now"), "now_at": ts(row.get("now_at")), "now_until": ts(row.get("now_until")),
            "overlay": row.get("overlay"), "command": row.get("command"), "sleep": row.get("sleep"),
            "bezel": row.get("bezel")}


def row_from_state(state):
    from datetime import datetime, timezone
    iso = lambda v: datetime.fromtimestamp(v, timezone.utc).isoformat() if v else None
    row = {"blackout": state["blackout"], "playing": state["playing"], "now": state.get("now"),
           "now_at": iso(state.get("now_at")), "now_until": iso(state.get("now_until"))}
    if "sleep" in state:
        row["sleep"] = state["sleep"]
    if "bezel" in state:
        row["bezel"] = state["bezel"]
    return row


def fetch(db):
    """(state, slides, activities) from the wall tables; raises on any network or HTTP error."""
    st = request(db, "GET", "wall_state", {"select": STATE_COLS, "id": "eq.1"})
    slides = request(db, "GET", "wall_slides", {"select": SLIDE_COLS, "order": "position,id"})
    ids = sorted({s["activity_id"] for s in slides if s.get("activity_id")})
    acts = request(db, "GET", "activities", {"select": ACT_COLS, "id": f"in.({','.join(map(str, ids))})"}) if ids else []
    return state_from_row(st[0] if st else {}), slides, acts


def set_state(db, state, keys=None):
    """PATCH the control row; with keys, only those columns, so a change made here never writes back other
    fields the server may hold stale between polls (a stale playing=false once undid a Play)."""
    row = row_from_state(state)
    if keys:
        row = {k: v for k, v in row.items() if k in keys}
    request(db, "PATCH", "wall_state", {"id": "eq.1"}, row, {"Prefer": "return=minimal"})


def heartbeat(db, fields):
    request(db, "POST", "wall_status", {"on_conflict": "id"}, [{"id": 1, **fields}],
            {"Prefer": "resolution=merge-duplicates,return=minimal"})


def storage_put(db, bucket, path, data, content_type):
    base, key = db
    url = base.removesuffix("/rest/v1")
    obj = urllib.parse.quote(path, safe="/")
    req = urllib.request.Request(f"{url}/storage/v1/object/{bucket}/{obj}", data=data, method="POST",
                                 headers={"apikey": key, "Authorization": f"Bearer {key}",
                                          "Content-Type": content_type, "x-upsert": "true"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def storage_list(db, bucket):
    base, key = db
    url = base.removesuffix("/rest/v1")
    req = urllib.request.Request(f"{url}/storage/v1/object/list/{bucket}",
                                 data=json.dumps({"prefix": "", "limit": 1000, "offset": 0,
                                                  "sortBy": {"column": "name", "order": "asc"}}).encode(),
                                 method="POST", headers={"apikey": key, "Authorization": f"Bearer {key}",
                                                         "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def storage_get(db, bucket, path, dest):
    base, key = db
    url = base.removesuffix("/rest/v1")
    obj = urllib.parse.quote(path, safe="/")
    req = urllib.request.Request(f"{url}/storage/v1/object/{bucket}/{obj}",
                                 headers={"apikey": key, "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
