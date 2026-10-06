# /// script
# requires-python = ">=3.11"
# dependencies = ["websockets"]
# ///
"""Wall client for one Pi: downloads its tiles and plays them in mpv at the server's timestamps.

    uv run --script wall.py [--server ws://192.168.1.131:8080/ws] [--screen a1]

The server sends whole plans ({"t":"plan","items":[{tile,url,kind,at,until,period}, ...]}); this
file only caches, switches at `at` on its own (chrony) clock and nudges video speed to stay in step.
"""
import argparse, asyncio, json, os, shutil, socket, subprocess, sys, time, urllib.request
from pathlib import Path

CACHE = Path.home() / "wall-cache"
KEEP_FREE_MB = 2048


def command_argv(kind):
    return {"restart": [sys.executable, *sys.argv], "reboot": ["sudo", "systemctl", "reboot"]}.get(kind)


def screen_from_hostname(name):
    """'wall-c4' or 'wall-c4.local' -> 'c4'."""
    name = name.split(".")[0].lower()
    return name[5:] if name.startswith("wall-") else name


def current_item(items, now):
    """The item to show at `now`: the last one that has started. None before the first starts.
    Past the last `until` the last item keeps looping (server gone or late)."""
    started = [i for i in items if i["at"] <= now]
    return max(started, key=lambda i: i["at"]) if started else None


def expected_pos(item, now):
    """Where the video should be at `now`: seconds since `at`, wrapped by `period` when looping."""
    t = max(0.0, now - item["at"])
    return t % item["period"] if item.get("period") else t


def wrap_err(pos, expected, period):
    """pos - expected, taking the shorter way round a loop."""
    err = pos - expected
    return (err + period / 2) % period - period / 2 if period else err


def drift_action(err):
    """Seek when far off, nudge speed when a little off, else play at 1."""
    if abs(err) > 1:
        return ("seek", None)
    if abs(err) > 0.04:
        return ("speed", 1 - max(-0.05, min(0.05, err / 5)))
    return ("speed", 1.0)


def evict(files, keep, free_mb, need_mb=KEEP_FREE_MB):
    """files: {name: (mtime, size_mb)}. Oldest first, never a name in `keep`, until free >= need."""
    out = []
    for name, (_, size) in sorted(files.items(), key=lambda kv: kv[1][0]):
        if free_mb >= need_mb:
            break
        if name not in keep:
            out.append(name)
            free_mb += size
    return out


def free_mb(path=CACHE):
    return shutil.disk_usage(path).free // 2**20


def sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


class Mpv:
    """One long-lived mpv, driven over its JSON IPC socket. Restarted if it exits."""

    def __init__(self, extra):
        self.sock = f"/tmp/mpv-wall-{os.getpid()}"
        self.extra = extra
        self.proc = None
        self.reader = self.writer = None
        self.pending = {}
        self.events = asyncio.Queue()
        self.rid = 0

    async def start(self):
        if self.proc and self.proc.returncode is None:
            return
        Path(self.sock).unlink(missing_ok=True)
        self.proc = await asyncio.create_subprocess_exec(
            "mpv", "--idle", "--force-window", "--fs", "--keep-open=always", "--image-display-duration=inf",
            "--hwdec=no", "--drm-mode=1280x1024@60", "--loop-file=inf", "--no-osc", "--osd-level=0", "--no-audio", "--really-quiet", "--no-input-default-bindings",
            f"--input-ipc-server={self.sock}", *self.extra)
        for _ in range(100):
            if Path(self.sock).exists():
                break
            await asyncio.sleep(0.05)
        self.reader, self.writer = await asyncio.open_unix_connection(self.sock)
        asyncio.create_task(self._read())

    async def _read(self):
        async for line in self.reader:
            msg = json.loads(line)
            fut = self.pending.pop(msg.get("request_id"), None)
            if fut and not fut.done():  # a reply after its timeout is dropped, not fatal
                fut.set_result(msg)
            elif "event" in msg:
                self.events.put_nowait(msg["event"])

    async def cmd(self, *args):
        await self.start()
        self.rid += 1
        fut = asyncio.get_running_loop().create_future()
        self.pending[self.rid] = fut
        self.writer.write((json.dumps({"command": list(args), "request_id": self.rid}) + "\n").encode())
        await self.writer.drain()
        try:
            msg = await asyncio.wait_for(fut, 5)
        except asyncio.TimeoutError:
            self.pending.pop(self.rid, None)
            return None
        return msg.get("data") if msg.get("error") == "success" else None


class Client:
    def __init__(self, args):
        self.server = args.server
        self.http = args.server.replace("ws://", "http://").replace("wss://", "https://").rsplit("/ws", 1)[0]
        self.screen = args.screen or screen_from_hostname(socket.gethostname())
        self.mpv = Mpv(args.mpv_args.split() if args.mpv_args else [])
        self.items = self.load_plan()
        self.cur = None           # tile loaded in mpv, or "black"
        self.lead = 0.25          # seconds from loadfile to first frame, EWMA
        self.seek_lead = 0.5      # seconds a seek takes on this Pi (a Pi 3 needs ~2 s at 1280x1024), learnt
        self.drift_ms = 0
        self.ws = None
        self.downloading = set()

    # --- cache -------------------------------------------------------------------------------------
    def path(self, item):
        return CACHE / item["tile"]

    def have(self, item):
        return self.path(item).exists()

    def load_plan(self):
        try:
            return json.loads((CACHE / "plan.json").read_text())
        except (OSError, ValueError):
            return []

    def download(self, item):
        dst, part = self.path(item), self.path(item).with_suffix(".part")
        with urllib.request.urlopen(self.http + item["url"], timeout=30) as r, open(part, "wb") as f:
            size = int(r.headers.get("Content-Length") or -1)
            shutil.copyfileobj(r, f, 1 << 20)
        if size >= 0 and part.stat().st_size != size:
            part.unlink()
            raise OSError(f"short download {item['tile']}")
        part.rename(dst)

    async def fetch_all(self):
        for item in list(self.items):
            if item.get("kind") == "black" or self.have(item) or item["tile"] in self.downloading:
                continue
            self.make_room()
            self.downloading.add(item["tile"])
            try:
                await asyncio.to_thread(self.download, item)
                await self.send({"t": "ready", "tile": item["tile"]})
            except OSError as e:
                await self.send({"t": "error", "msg": f"{item['tile']}: {e}"})
            finally:
                self.downloading.discard(item["tile"])

    def make_room(self):
        files = {p.name: (p.stat().st_mtime, p.stat().st_size / 2**20) for p in CACHE.iterdir() if p.is_file()}
        keep = {i["tile"] for i in self.items} | {"plan.json"}
        for name in evict(files, keep, free_mb()):
            (CACHE / name).unlink(missing_ok=True)

    # --- server link -------------------------------------------------------------------------------
    async def send(self, msg):
        if self.ws:
            try:
                await self.ws.send(json.dumps(msg))
            except Exception:
                pass

    async def link(self):
        import websockets
        backoff = 1
        while True:
            try:
                async with websockets.connect(self.server, ping_interval=10, open_timeout=10) as ws:
                    self.ws, backoff = ws, 1
                    have = [p.name for p in CACHE.iterdir() if p.is_file()]
                    await self.send({"t": "hello", "screen": self.screen, "have": have, "free_mb": free_mb()})
                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("t") == "plan":
                            self.items = sorted(msg["items"], key=lambda i: i["at"])
                            (CACHE / "plan.json").write_text(json.dumps(self.items))
                            asyncio.create_task(self.fetch_all())
                        elif msg.get("t") == "ping":
                            await self.send({"t": "pong", "id": msg.get("id"), "now": time.time()})
                        elif msg.get("t") == "command" and msg.get("kind") == "display":
                            # Night sleep: HDMI off lets the monitor go to standby; on KMS this may be refused,
                            # then the server's black plan is all there is.
                            out = sh(["vcgencmd", "display_power", "1" if msg.get("on") else "0"])
                            print(f"display {'on' if msg.get('on') else 'off'}: vcgencmd -> {out or 'no answer'}", flush=True)
                        elif msg.get("t") == "command":
                            argv = command_argv(msg.get("kind"))
                            if msg.get("kind") == "restart" and argv:
                                if self.mpv.proc and self.mpv.proc.returncode is None:
                                    self.mpv.proc.terminate()  # else the new client starts a second mpv
                                os.execv(argv[0], argv)
                            elif argv:
                                subprocess.Popen(argv)
            except Exception as e:
                print(f"link: {type(e).__name__}: {e}; retry in {backoff}s", flush=True)
            self.ws = None
            await asyncio.sleep(backoff)
            backoff = min(5, backoff + 1)

    async def report(self):
        while True:
            await asyncio.sleep(5)
            dropped = await self.mpv.cmd("get_property", "frame-drop-count")
            temp = sh(["cat", "/sys/class/thermal/thermal_zone0/temp"])
            await self.send({"t": "status", "tile": self.cur, "drift_ms": self.drift_ms, "dropped": dropped or 0,
                             "throttled": sh(["vcgencmd", "get_throttled"]).split("=")[-1] or None,
                             "temp": round(int(temp) / 1000) if temp.isdigit() else None,
                             "free_mb": free_mb(), "now": time.time()})

    # --- playback ----------------------------------------------------------------------------------
    async def show(self, item):
        if item is None or item.get("kind") == "black":
            if self.cur != "black":
                await self.mpv.cmd("stop")
                self.cur = "black"
            return
        path = self.path(item)
        os.utime(path)  # the SD card is noatime; mtime is the LRU clock
        opts = "pause=no"
        if item.get("kind") == "video":
            opts += f",start={expected_pos(item, time.time() + self.lead):.3f}"
        t0 = time.monotonic()
        await self.mpv.cmd("loadfile", str(path), "replace", -1, opts)  # mpv >= 0.38: index before options
        self.cur = item["tile"]
        if item.get("kind") == "video":
            try:
                while await asyncio.wait_for(self.mpv.events.get(), 3) != "playback-restart":
                    pass
                self.lead = 0.7 * self.lead + 0.3 * (time.monotonic() - t0)
            except asyncio.TimeoutError:
                pass

    async def seek(self, pos):
        while not self.mpv.events.empty():
            self.mpv.events.get_nowait()
        await self.mpv.cmd("seek", pos, "absolute")
        try:
            while await asyncio.wait_for(self.mpv.events.get(), 8) != "playback-restart":
                pass
        except asyncio.TimeoutError:
            pass

    async def correct(self, item):
        pos = await self.mpv.cmd("get_property", "time-pos")
        if pos is None:
            return
        expected = expected_pos(item, time.time())
        err = wrap_err(pos, expected, item.get("period"))
        self.drift_ms = round(err * 1000)
        kind, speed = drift_action(err)
        if kind == "seek":
            # Aim where the video will be once the seek is done, wait for it, then learn from the miss.
            await self.mpv.cmd("set_property", "speed", 1.0)
            await self.seek(expected_pos(item, time.time() + self.seek_lead))
            pos = await self.mpv.cmd("get_property", "time-pos")
            if pos is not None:
                miss = wrap_err(pos, expected_pos(item, time.time()), item.get("period"))
                self.seek_lead = max(0.1, min(5.0, self.seek_lead - miss))
        else:
            await self.mpv.cmd("set_property", "speed", speed)

    async def play(self):
        last_check = 0
        while True:
            now = time.time()
            if not self.items:
                await self.show(None)
            else:
                item = current_item(self.items, now + self.lead)
                if item and item["tile"] != self.cur and (item.get("kind") == "black" or self.have(item)):
                    await self.show(item)
                elif item and item["tile"] == self.cur and item.get("kind") == "video" and now - last_check > 1:
                    last_check = now
                    await self.correct(item)
            await asyncio.sleep(0.1)

    async def run(self):
        CACHE.mkdir(exist_ok=True)
        await self.mpv.start()
        await asyncio.gather(self.link(), self.report(), self.play(), self.fetch_all())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--server", default="ws://192.168.1.131:8080/ws")
    ap.add_argument("--screen", help="grid code, default from the hostname (wall-a1 -> a1)")
    ap.add_argument("--mpv-args", default="", help="extra mpv flags, e.g. --vo=null for a test without a screen")
    try:
        asyncio.run(Client(ap.parse_args()).run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
