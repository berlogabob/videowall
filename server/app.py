"""Wall server: works out what every screen shows, renders it with FFmpeg, tells the Pis over WebSocket.

    uv run python -m server --cols 5 --rows 5 --media ~/tv-media --cache ~/wall-cache

Control: the LAN page (/), and the office through Supabase when SUPABASE_URL / SUPABASE_SERVICE_KEY are set.
"""
import argparse, asyncio, json, queue, shutil, threading, time, traceback
from pathlib import Path

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import db as sdb
from . import render as R
from datetime import datetime

from .schedule import TZ, describe, in_window, link_events, resolve

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
OVERLAY_SECONDS = {"identify": 10, "test": 60}
NOW_LEAD = 3  # seconds between "show now" and the synced start, time for the Pis to download


def load_json(p, default):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


class Wall:
    def __init__(self, a):
        self.a = a
        self.grid = (a.cols, a.rows, R.even(a.bezel_x), R.even(a.bezel_y))
        self.codes = R.codes(a.cols, a.rows)
        self.root = Path(a.cache).expanduser()
        self.cache = R.Cache(self.root, a.cache_gb)
        self.media_dir = Path(a.media).expanduser()
        self.media, self.assets = {}, {}
        self.state = load_json(self.root / "state.json", {}) or {}
        self.state = {"blackout": False, "playing": True, "now": None, "now_at": None, "now_until": None} | self.state
        self.slides = load_json(self.root / "playlist.json", [])
        self.activities = []
        self.screens = {}      # code -> {ws, ip, status, seen, clock_ms}
        self.overlay = {}      # code -> (kind, until)
        self.jobs = {}         # render key -> "queued" | "rendering 40%" | "failed: ..."
        self.q = queue.Queue()
        self.sent = {}
        self.pinned = set()
        self.show = ("defaults", None, 0, None)
        self.db = sdb.connect()
        self.db_error = None
        if self.db:
            cached = load_json(self.root / "last-db.json", None)
            if cached:
                self.state, self.slides, self.activities = cached["state"], cached["slides"], cached["activities"]
        threading.Thread(target=self.worker, daemon=True).start()

    # --- persistence ----------------------------------------------------------------------------------------
    def save_state(self):
        (self.root / "state.json").write_text(json.dumps(self.state))
        if self.db:
            try:
                sdb.set_state(self.db, self.state)
            except Exception as e:
                self.db_error = f"{type(e).__name__}: {e}"

    # --- renders --------------------------------------------------------------------------------------------
    def worker(self):
        while True:
            k, fn = self.q.get()
            self.jobs[k] = "rendering 0%"
            d = self.cache.dir(k)
            try:
                meta = fn(d, lambda p: self.jobs.__setitem__(k, f"rendering {p:.0f}%")) or {}
                self.cache.finish(k, **meta)
                self.jobs.pop(k, None)
                self.cache.evict(self.pinned)
            except Exception as e:
                shutil.rmtree(d, ignore_errors=True)
                self.jobs[k] = f"failed: {str(e).splitlines()[-1][:200] if str(e) else type(e).__name__}"
                traceback.print_exc()

    def ensure(self, k, fn, est_bytes=50 * 2**20):
        """True when render k is ready; otherwise queue it once (a failure stays failed until its key changes)."""
        self.pinned.add(k)
        if self.cache.ready(k):
            return True
        if k not in self.jobs:
            if not self.cache.room_for(est_bytes):
                self.jobs[k] = "failed: disk"
            else:
                self.jobs[k] = "queued"
                self.q.put((k, fn))
        return False

    def src(self, name):
        return (ASSETS if name in self.assets and name not in self.media else self.media_dir) / name

    def info(self, name):
        return self.media.get(name) or self.assets.get(name)

    def tile_key(self, name, fit):
        """Mosaic: one file on one screen. Returns (key, ext) and queues the render."""
        m = self.info(name)
        video = m["kind"] == "video"
        k = R.key("tile", name, m["size"], m["mtime"], fit)
        ext = "mp4" if video else "jpg"

        def fn(d, progress):
            R.render_tile(self.src(name), d / f"tile.{ext}", fit, video, m["seconds"], progress)
            return {"period": m["seconds"]} if video else {}
        return (k, ext) if self.ensure(k, fn, 30 * 2**20 * max(1, (m["seconds"] or 0) / 60)) else (None, ext)

    def wall_keys(self, s):
        """Videowall slide -> (video key or None, poster/still key or None), queueing poster first (D9)."""
        name = (s.get("media_names") or [None])[0]
        m = self.info(name) if name else None
        if not m:
            return None, None
        comp = dict(fit=s.get("fit") or "fit", matte=s.get("matte") or 0, credits=s.get("credits") or None,
                    title=s.get("title") if s.get("show_title") else None,
                    logo=str(ASSETS / "logo.png") if s.get("logo") and (ASSETS / "logo.png").exists() else None)
        base = ("wall", name, m["size"], m["mtime"], self.grid, sorted(comp.items()))
        video = m["kind"] == "video"
        pk = R.key(*base, "poster" if video else "still")

        def still(d, progress):
            R.render_videowall(self.src(name), d, self.grid, video=video, poster=video, font=self.a.font, **comp)
        ready_p = self.ensure(pk, still, 2 * 2**20 * len(self.codes))
        if not video:
            return None, pk if ready_p else None
        vk = R.key(*base, "video")

        def moving(d, progress):
            R.render_videowall(self.src(name), d, self.grid, video=True, duration=m["seconds"], progress=progress,
                               font=self.a.font, **comp)
            return {"period": m["seconds"]}
        est = 30 * 2**20 * len(self.codes) * max(1, m["seconds"] / 60)
        return (vk if self.ensure(vk, moving, est) else None), (pk if ready_p else None)

    def names(self, s):
        return [n for n in (s.get("media_names") or sorted(self.media)) if self.info(n)]

    def ready(self, s):
        if s["mode"] == "videowall":
            return any(self.wall_keys(s))
        names = self.names(s)
        return bool(names) and all([self.tile_key(n, s.get("fit") or "fit")[0] for n in names])

    def grid_key(self):
        k = R.key("grid", self.grid)
        return k if self.ensure(k, lambda d, p: R.render_test_grid(d, self.grid)) else None

    def ident_key(self, code):
        ip = (self.screens.get(code) or {}).get("ip", "")
        k = R.key("identify", code, ip)
        return k if self.ensure(k, lambda d, p: R.render_identify(code, ip, d / f"{code}.jpg", self.a.font)) else None

    # --- plans ----------------------------------------------------------------------------------------------
    def item(self, k, file, kind, at, until=None, period=None):
        it = {"tile": f"{k}-{file}", "url": f"/tiles/{k}/{file}", "kind": kind, "at": at, "until": until}
        return it | ({"period": period} if period else {})

    def mosaic_items(self, code, names, fit, cycle, at, until, t):
        i, n = self.codes.index(code), len(names)
        out = []
        for step in (0, 1):  # this file and the next one, so the Pi preloads it
            k_ = int((t - at) // cycle) + step if cycle else 0
            iat = at + k_ * cycle if cycle else at
            if step and (not cycle or (until and iat >= until)):
                break
            name = names[(i + k_) % n]
            m = self.info(name)
            k, ext = self.tile_key(name, fit)
            if k:
                out.append(self.item(k, f"tile.{ext}", m["kind"] if m["kind"] == "video" else "image", iat,
                                     min(iat + cycle, until or 1e18) if cycle else until,
                                     m["seconds"] if m["kind"] == "video" else None))
        return out

    def items_for(self, code, show, t):
        level, s, at, until = show
        black = [{"tile": "black", "kind": "black", "at": at}]
        if level == "blackout":
            return black
        if level == "stopped":  # idle card: the logo on every screen, else black
            return self.mosaic_items(code, ["logo.png"], "fit", None, at, until, t) if "logo.png" in self.assets else black
        if level == "defaults":
            names = sorted(n for n in self.assets if n != "logo.png") or sorted(self.assets)
            if names:
                return self.mosaic_items(code, names, "fit", 10, 0, None, t)
            k = self.grid_key()
            return [self.item(k, f"{code}.jpg", "image", 0)] if k else black
        if s["mode"] == "mosaic":
            return self.mosaic_items(code, self.names(s), s.get("fit") or "fit", s.get("cycle_seconds"), at, until, t)
        vk, pk = self.wall_keys(s)
        if vk:
            return [self.item(vk, f"{code}.mp4", "video", at, until, self.cache.meta(vk).get("period"))]
        if pk:
            m = self.info(s["media_names"][0])
            return [self.item(pk, f"poster-{code}.jpg" if m["kind"] == "video" else f"{code}.jpg", "image", at, until)]
        return black

    def durations(self):
        return {n: m["seconds"] for n, m in (self.media | self.assets).items() if m.get("seconds")}

    def plans(self, t):
        self.pinned = set()
        self.show = show = resolve(self.state, self.slides, self.activities, t, self.durations(), self.ready)
        nxt = None
        if show[3] and show[3] - t < 30:  # the next slide, early enough to download
            nxt = resolve(self.state, self.slides, self.activities, show[3] + 0.01, self.durations(), self.ready)
        out = {}
        for code in self.codes:
            kind, until = self.overlay.get(code, (None, 0))
            if kind and until > t:
                k = self.ident_key(code) if kind == "identify" else self.grid_key()
                if k:
                    out[code] = [self.item(k, f"{code}.jpg", "image", 0)]
                    continue
            items = self.items_for(code, show, t)
            if nxt and nxt[:2] != show[:2]:
                items += self.items_for(code, nxt, show[3] + 0.01)
            out[code] = items
        self.pinned.add(self.grid_key() or "")
        return out

    async def tick(self):
        last_ahead = 0
        while True:
            t = time.time()
            try:
                if t - last_ahead > 30:  # render ahead: everything in today's window, in playlist order
                    last_ahead = t
                    self.media = await asyncio.to_thread(R.scan, self.media_dir, self.root)
                    self.assets = await asyncio.to_thread(R.scan, ASSETS, self.root / "assets-probe") \
                        if ASSETS.is_dir() else {}
                    today = datetime.fromtimestamp(t, TZ).date()
                    for s in link_events(self.slides, self.activities, today):
                        if in_window(s, today):
                            self.ready(s)
                plans = self.plans(t)
                for code, items in plans.items():
                    scr = self.screens.get(code)
                    if scr and scr.get("ws") and self.sent.get(code) != items:
                        self.sent[code] = items
                        await scr["ws"].send_json({"t": "plan", "items": items})
            except Exception:
                traceback.print_exc()
            await asyncio.sleep(0.5)

    # --- clocks and the office ------------------------------------------------------------------------------
    async def pings(self):
        while True:
            for scr in list(self.screens.values()):
                if scr.get("ws"):
                    try:
                        await scr["ws"].send_json({"t": "ping", "id": time.time()})
                    except Exception:
                        pass
            await asyncio.sleep(5)

    def status(self):
        now = time.time()
        screens = {}
        for code in self.codes:
            s = self.screens.get(code) or {}
            st = s.get("status") or {}
            screens[code] = {"on": bool(s.get("ws")) and now - s.get("seen", 0) < 15, "ip": s.get("ip"),
                             "tile": st.get("tile"), "drift_ms": st.get("drift_ms"), "dropped": st.get("dropped"),
                             "throttled": st.get("throttled"), "temp": st.get("temp"), "free_mb": st.get("free_mb"),
                             "clock_ms": s.get("clock_ms")}
        level, s, _, until = self.show
        return {"cols": self.a.cols, "rows": self.a.rows, "screens": screens, "playing": describe(level, s, until),
                "state": self.state, "jobs": dict(self.jobs), "db": bool(self.db), "db_error": self.db_error,
                "cache_mb": self.cache.size() // 2**20, "disk_free_mb": shutil.disk_usage(self.root).free // 2**20,
                "media": [{"name": n} | m for n, m in sorted(self.media.items())], "slides": self.slides,
                "bezel": self.grid[2:]}

    async def office(self):
        """Poll the wall tables every 2 s (a slow fetch just delays the next), heartbeat every 10 s."""
        last_beat = 0
        while True:
            try:
                state, slides, acts = await asyncio.to_thread(sdb.fetch, self.db)
                self.state, self.slides, self.activities = state, slides, acts
                ov = state.get("overlay") or {}
                until = sdb.ts(ov.get("until")) or 0
                if ov.get("kind") in OVERLAY_SECONDS and until > time.time():  # Identify / Test from the office
                    for c in self.codes if ov.get("code") == "all" else [ov.get("code")]:
                        if c in self.codes:
                            self.overlay[c] = (ov["kind"], until)
                (self.root / "last-db.json").write_text(json.dumps({"state": state, "slides": slides,
                                                                    "activities": acts}))
                self.db_error = None
            except Exception as e:  # keep playing from the last good copy
                self.db_error = f"{type(e).__name__}: {e}"
            if time.time() - last_beat > 10:
                last_beat = time.time()
                st = self.status()
                slides = {}
                for s in self.slides:
                    keys = [k for k in self.wall_keys(s) if k] if s["mode"] == "videowall" else []
                    jobs = [self.jobs[k] for k in self.jobs if k in keys]
                    slides[str(s["id"])] = "ready" if keys and not jobs else (jobs[0] if jobs else "waiting")
                from datetime import datetime, timezone
                fields = {"seen_at": datetime.now(timezone.utc).isoformat(), "playing": st["playing"],
                          "screens": st["screens"], "slides": slides, "cache_mb": st["cache_mb"],
                          "disk_free_mb": st["disk_free_mb"]}
                if self.db_error:
                    fields |= {"error": self.db_error[:500], "error_at": fields["seen_at"]}
                try:
                    await asyncio.to_thread(sdb.heartbeat, self.db, fields)
                except Exception as e:
                    self.db_error = f"{type(e).__name__}: {e}"
            await asyncio.sleep(2)


def make_app(a):
    wall = Wall(a)
    app = FastAPI(title="videowall")
    app.state.wall = wall
    app.mount("/tiles", StaticFiles(directory=wall.cache.tiles), name="tiles")

    @app.on_event("startup")
    async def start():
        asyncio.create_task(wall.tick())
        asyncio.create_task(wall.pings())
        if wall.db:
            asyncio.create_task(wall.office())
        print(f"wall {a.cols}x{a.rows} on :{a.port}, media {wall.media_dir}, cache {wall.root}, "
              f"office link {'on' if wall.db else 'off (standalone)'}", flush=True)

    @app.get("/")
    def page():
        return FileResponse(HERE / "page.html")

    @app.get("/wall.py")
    def client():
        return FileResponse(HERE.parent / "client" / "wall.py", media_type="text/x-python")

    @app.get("/api/status")
    def status():
        return wall.status()

    @app.post("/api/overlay/{kind}/{code}")
    def overlay(kind: str, code: str):
        if kind not in OVERLAY_SECONDS:
            return JSONResponse({"error": "kind"}, 400)
        until = time.time() + OVERLAY_SECONDS[kind]
        for c in wall.codes if code == "all" else [code]:
            wall.overlay[c] = (kind, until)
        return {"ok": True}

    @app.post("/api/state")
    def set_state(body: dict = Body(...)):
        """{blackout?, playing?}"""
        for k in ("blackout", "playing"):
            if k in body:
                wall.state[k] = bool(body[k])
        wall.save_state()
        return wall.state

    @app.post("/api/now")
    def now(body: dict = Body(...)):
        """Show this now: a slide-shaped dict {mode, media_names, fit, ...}, optional seconds."""
        if body.get("mode") not in ("mosaic", "videowall"):
            return JSONResponse({"error": "mode"}, 400)
        t = time.time() + NOW_LEAD
        wall.state |= {"now": body, "now_at": t, "now_until": t + body["seconds"] if body.get("seconds") else None}
        wall.save_state()
        return wall.state

    @app.delete("/api/now")
    def back():
        wall.state |= {"now": None, "now_at": None, "now_until": None}
        wall.save_state()
        return wall.state

    @app.get("/api/playlist")
    def get_playlist():
        return wall.slides

    @app.put("/api/playlist")
    def put_playlist(rows: list = Body(...)):
        if wall.db:
            return JSONResponse({"error": "the playlist is edited in the office"}, 409)
        for i, s in enumerate(rows):
            s.setdefault("id", i + 1)
        wall.slides = rows
        (wall.root / "playlist.json").write_text(json.dumps(rows, indent=1))
        return rows

    @app.get("/api/preview.jpg")
    def preview():
        """The current videowall canvas (or the test grid) with the screen borders drawn."""
        level, s, _, _ = wall.show
        k = None
        if s and s["mode"] == "videowall":
            k = wall.wall_keys(s)[1]
        k = k or wall.grid_key()
        p = wall.cache.dir(k) / "preview.jpg" if k else None
        return FileResponse(p) if p and p.exists() else Response(status_code=404)

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        code = None
        try:
            while True:
                msg = await sock.receive_json()
                t = msg.get("t")
                if t == "hello":
                    code = msg["screen"]
                    wall.screens[code] = {"ws": sock, "ip": sock.client.host if sock.client else None,
                                          "status": {"free_mb": msg.get("free_mb")}, "seen": time.time()}
                    wall.sent.pop(code, None)
                elif code and t == "status":
                    wall.screens[code] |= {"status": msg, "seen": time.time()}
                elif code and t == "pong":
                    t1 = time.time()
                    wall.screens[code]["clock_ms"] = round((msg["now"] - (msg["id"] + t1) / 2) * 1000)
                    wall.screens[code]["seen"] = t1
                elif t == "error":
                    print(f"{code}: {msg.get('msg')}", flush=True)
        except (WebSocketDisconnect, RuntimeError, KeyError, ValueError):
            pass
        finally:
            if code and (wall.screens.get(code) or {}).get("ws") is sock:
                wall.screens[code]["ws"] = None

    return app


def main():
    ap = argparse.ArgumentParser(description="Video wall server")
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--rows", type=int, default=5)
    ap.add_argument("--bezel-x", type=int, default=0, help="px hidden between columns (bezel mm / 0.264)")
    ap.add_argument("--bezel-y", type=int, default=0, help="px hidden between rows")
    ap.add_argument("--media", default="~/tv-media", help="the shared media folder (the TV's)")
    ap.add_argument("--cache", default="~/wall-cache", help="renders and state, outside the media folder")
    ap.add_argument("--cache-gb", type=float, default=60)
    ap.add_argument("--font", help="TTF for titles and identify (default DejaVu Sans Bold / Arial Bold)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    a = ap.parse_args()
    Path(a.cache).expanduser().mkdir(parents=True, exist_ok=True)
    import uvicorn
    uvicorn.run(make_app(a), host=a.host, port=a.port, log_level="warning")
