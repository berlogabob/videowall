"""Everything FFmpeg: grid maths, media scan, tile renders, the render cache.

All tiles are 1280x1024 (Samsung 720N). A render lives in <cache>/tiles/<key>/ with one file per screen code
(a1.jpg, b1.mp4, ...), optional poster-<code>.jpg and preview.jpg, and meta.json written last (= ready).
"""
import hashlib, json, os, shutil, subprocess, textwrap, time
from pathlib import Path

TW, TH = 1280, 1024
RENDER_VERSION = 1
PHOTO = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic"}
VIDEO = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi"}
STILL = ["-frames:v", "1", "-q:v", "2"]
# Same settings on every tile, so all 25 decode alike; 1 s GOP makes joining mid-video cheap.
VIDEO_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-profile:v", "high", "-level", "4.0", "-r", "30", "-g", "30",
              "-keyint_min", "30", "-sc_threshold", "0", "-b:v", "4M", "-maxrate", "5M", "-bufsize", "8M",
              "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart"]
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/Library/Fonts/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"]
NICE = ["nice", "-n", "10"] if shutil.which("nice") else []


# --- grid -----------------------------------------------------------------------------------------------
def codes(cols, rows):
    """a1 b1 ... e1 a2 ... e5: letter = column, number = row, reading order."""
    return [f"{chr(97 + c)}{r + 1}" for r in range(rows) for c in range(cols)]


def cell(code):
    return ord(code[0]) - 97, int(code[1:]) - 1


def even(n):
    return int(n) // 2 * 2  # yuv420p needs even sizes; a bezel of 1 px is noise anyway


def canvas_size(cols, rows, gx=0, gy=0):
    """The picture spans the screens and the bezel gaps between them (gx, gy px, hidden behind the frames)."""
    return cols * TW + (cols - 1) * even(gx), rows * TH + (rows - 1) * even(gy)


def crop_xy(code, gx=0, gy=0):
    c, r = cell(code)
    return c * (TW + even(gx)), r * (TH + even(gy))


def bezel_px(mm, pitch_mm=0.264):
    """Bezel gap in canvas pixels: the frames of two neighbours (mm) over the 720N's pixel pitch."""
    return even(round(mm / pitch_mm))


# --- filters --------------------------------------------------------------------------------------------
def fit_filter(fit, w, h):
    """fit: whole picture, black bars. fill: cover, cut the overflow. center: no scaling."""
    if fit == "fill":
        f = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    elif fit == "center":
        f = f"crop='min(iw,{w})':'min(ih,{h})',pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
    else:
        f = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
    return f + ",setsar=1"


def drawtext(textfile, size, x, y):
    # ponytail: text and font go in as files next to the render (cwd), so nothing needs filtergraph escaping
    return (f"drawtext=fontfile=font.ttf:textfile={textfile}:expansion=none:fontsize={size}:fontcolor=white"
            f":borderw={max(2, size // 20)}:bordercolor=black@0.7:x={x}:y={y}")


def canvas_graph(cols, rows, gx=0, gy=0, fit="fit", matte=0, title=False, credits=False, logo=False):
    """[0:v] (and [1:v] = logo) -> [c], the whole composed canvas."""
    W, H = canvas_size(cols, rows, gx, gy)
    m = even(matte)
    g = f"[0:v]{fit_filter(fit, W - 2 * m, H - 2 * m)},pad={W}:{H}:{m}:{m}:black"
    if title:
        g += "," + drawtext("title.txt", H // 12, "(w-tw)/2", "h*0.78-th/2")
    if credits:
        g += "," + drawtext("credits.txt", max(24, H // 40), f"w-tw-{m + 40}", f"h-th-{m + 40}")
    if logo:
        return g + f"[c0];[1:v]scale=-2:{even(H // 8)}[lg];[c0][lg]overlay=W-w-{m + 40}:{m + 40}[c]", W, H
    return g + "[c]", W, H


def slice_graph(graph, codes_, gx, gy, W, preview=False):
    """[c] -> one [o_<code>] per screen (+ [o_preview], 640 px wide with the tile borders drawn)."""
    n = len(codes_) + (1 if preview else 0)
    g = graph + f";[c]split={n}" + "".join(f"[s{i}]" for i in range(n))
    for i, code in enumerate(codes_):
        x, y = crop_xy(code, gx, gy)
        g += f";[s{i}]crop={TW}:{TH}:{x}:{y}[o_{code}]"
    if preview:
        s = 640 / W
        g += (f";[s{n - 1}]scale=640:-2,drawgrid=w={(TW + even(gx)) * s:.2f}:h={(TH + even(gy)) * s:.2f}"
              f":t=2:c=red@0.8[o_preview]")
    return g


# --- running ffmpeg -------------------------------------------------------------------------------------
def has_filter(name, _cache={}):
    if name not in _cache:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        _cache[name] = f" {name} " in out
    return _cache[name]


def ffmpeg(args, cwd=None, duration=None, progress=None):
    """Run ffmpeg; progress(percent) from -progress when the output duration is known."""
    cmd = NICE + ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args]
    if progress and duration:
        cmd[len(NICE) + 1:len(NICE) + 1] = ["-progress", "pipe:1", "-nostats"]
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if progress and duration:
        for line in p.stdout:
            if line.startswith("out_time_us=") and line[12:].strip().isdigit():
                progress(min(99, int(line[12:]) / 1e6 / duration * 100))
    err = p.stderr.read()
    if p.wait():
        raise RuntimeError(err.strip()[-400:] or f"ffmpeg exit {p.returncode}")


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True).stdout
    d = json.loads(out or "{}")
    s = (d.get("streams") or [{}])[0]
    kind = "video" if path.suffix.lower() in VIDEO else "photo"
    secs = float(d.get("format", {}).get("duration") or 0) if kind == "video" else None
    return {"kind": kind, "width": s.get("width"), "height": s.get("height"), "seconds": secs}


def scan(media, cache):
    """The shared media folder (flat, like the TV's): {name: {kind, width, height, seconds, size, mtime}}."""
    pfile = cache / "probe.json"
    try:
        old = json.loads(pfile.read_text())
    except (OSError, ValueError):
        old = {}
    out = {}
    for p in sorted(media.iterdir()) if media.is_dir() else []:
        if not p.is_file() or p.name.startswith(".") or p.suffix.lower() not in PHOTO | VIDEO:
            continue
        st = p.stat()
        o = old.get(p.name)
        if o and o["size"] == st.st_size and o["mtime"] == st.st_mtime_ns:
            out[p.name] = o
            continue
        info = probe(p)
        if info["width"]:
            out[p.name] = info | {"size": st.st_size, "mtime": st.st_mtime_ns}
    if out != old:
        pfile.write_text(json.dumps(out))
    return out


# --- cache ----------------------------------------------------------------------------------------------
def key(*parts):
    return hashlib.sha256(json.dumps([RENDER_VERSION, *parts], sort_keys=True, default=str).encode()).hexdigest()[:16]


def evict_plan(entries, pinned, budget):
    """entries {key: (last_used, bytes)}: oldest unpinned first until the total fits the budget."""
    total, out = sum(b for _, b in entries.values()), []
    for k, (_, b) in sorted(entries.items(), key=lambda kv: kv[1][0]):
        if total <= budget:
            break
        if k not in pinned:
            out.append(k)
            total -= b
    return out


class Cache:
    def __init__(self, root, budget_gb):
        self.root = root
        self.tiles = root / "tiles"
        self.tiles.mkdir(parents=True, exist_ok=True)
        self.budget = budget_gb * 2**30

    def dir(self, k):
        return self.tiles / k

    def meta(self, k):
        try:
            return json.loads((self.dir(k) / "meta.json").read_text())
        except (OSError, ValueError):
            return None

    def ready(self, k):
        return (self.dir(k) / "meta.json").exists()

    def touch(self, k):
        try:
            os.utime(self.dir(k) / "meta.json")
        except OSError:
            pass

    def finish(self, k, **meta):
        d = self.dir(k)
        size = sum(f.stat().st_size for f in d.iterdir() if f.is_file())
        (d / "meta.json").write_text(json.dumps(meta | {"bytes": size, "made": time.time()}))

    def size(self):
        return sum((self.meta(p.name) or {}).get("bytes", 0) for p in self.tiles.iterdir() if p.is_dir())

    def evict(self, pinned):
        entries = {}
        for p in self.tiles.iterdir():
            m = self.meta(p.name)
            if p.is_dir() and m:
                entries[p.name] = ((p / "meta.json").stat().st_mtime, m["bytes"])
        gone = evict_plan(entries, pinned, self.budget)
        for k in gone:
            shutil.rmtree(self.dir(k), ignore_errors=True)
        return gone

    def room_for(self, est_bytes):
        return shutil.disk_usage(self.root).free > est_bytes * 1.2 + 5 * 2**30


def find_font(font=None):
    for f in [font, *FONTS]:
        if f and Path(f).is_file():
            return f
    return None


def prepare_text(d, font, title=None, credits=None):
    """Writes title.txt / credits.txt / font.ttf into the render dir; returns which ones drawtext can use."""
    ok = bool(font) and has_filter("drawtext")
    if ok:
        shutil.copyfile(font, d / "font.ttf")
    for name, text in (("title.txt", title), ("credits.txt", credits)):
        if text and ok:
            (d / name).write_text(text)
    return bool(ok and title), bool(ok and credits)


def wrap(text, width=24):
    """Wrap words while preserving explicit paragraph breaks."""
    return "\n".join(textwrap.fill(line, width) for line in text.splitlines() or [text])


def render_text(text, d, grid, font):
    """Render an emergency message onto a black canvas, then slice it into screen JPGs."""
    cols, rows, gx, gy = grid
    W, H = canvas_size(cols, rows, gx, gy)
    d.mkdir(parents=True, exist_ok=True)
    font = find_font(font)
    if not font or not has_filter("drawtext"):
        raise RuntimeError("emergency text needs an FFmpeg drawtext filter and a font")
    shutil.copyfile(font, d / "font.ttf")
    (d / "text.txt").write_text(wrap(text))
    graph = f"[0:v]{drawtext('text.txt', H // 10, '(w-tw)/2', '(h-th)/2')}[c]"
    cs = codes(cols, rows)
    args = ["-f", "lavfi", "-i", f"color=c=black:s={W}x{H}", "-filter_complex",
            slice_graph(graph, cs, gx, gy, W, preview=True)]
    for code in cs:
        args += ["-map", f"[o_{code}]", *STILL, f"{code}.jpg"]
    ffmpeg(args + ["-map", "[o_preview]", *STILL, "preview.jpg"], cwd=d)


# --- renders --------------------------------------------------------------------------------------------
def render_videowall(src, d, grid, fit="fit", matte=0, title=None, credits=None, logo=None, font=None,
                     video=False, poster=False, duration=None, progress=None):
    """One decode, one composed canvas, split into one tile per screen (+ preview). Still (jpg) unless video."""
    cols, rows, gx, gy = grid
    d.mkdir(parents=True, exist_ok=True)
    t, c = prepare_text(d, find_font(font), title, credits)
    graph, W, H = canvas_graph(cols, rows, gx, gy, fit, matte, t, c, bool(logo))
    cs = codes(cols, rows)
    still = not video or poster
    g = slice_graph(graph, cs, gx, gy, W, preview=still)
    args = ["-i", str(src)] + (["-i", str(logo)] if logo else []) + ["-filter_complex", g]
    for code in cs:
        name = (f"poster-{code}.jpg" if poster else f"{code}.jpg") if still else f"{code}.mp4"
        args += ["-map", f"[o_{code}]", *(STILL if still else VIDEO_ARGS), name]
    if still:
        args += ["-map", "[o_preview]", *STILL, "preview.jpg"]
    ffmpeg(args, cwd=d, duration=None if still else duration, progress=progress)


def render_tile(src, out, fit="fit", video=False, duration=None, progress=None):
    """Mosaic: one file normalised to one screen."""
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg(["-i", str(src), "-vf", fit_filter(fit, TW, TH), *(VIDEO_ARGS if video else STILL), str(out)],
           duration=duration if video else None, progress=progress)


def mosaic_preview(tiles, cols, rows, out):
    """Compose the current mosaic tiles into a 640 px wide preview with screen borders."""
    cs = codes(cols, rows)
    layout = "|".join(f"{c % cols * TW}_{c // cols * TH}" for c in range(cols * rows))
    graph = f"xstack=inputs={len(cs)}:layout={layout},scale=640:-2,drawgrid=w={TW * 640 / (cols * TW):.2f}:h={TH * 640 / (cols * TW):.2f}:t=2:c=red@0.8"
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg([*sum((["-i", str(tiles[c])] for c in cs), []), "-filter_complex", graph, *STILL, str(out)])


PALETTE = ["0x1f77b4", "0xd62728", "0x2ca02c", "0x9467bd", "0xff7f0e", "0x17becf", "0x8c564b", "0xe377c2"]


def render_identify(code, ip, out, font=None):
    """A screen's own code in huge letters on a colour of its own, IP below."""
    out.parent.mkdir(parents=True, exist_ok=True)
    c, r = cell(code)
    g = f"drawbox=x=0:y=0:w=iw:h=ih:t=24:c=white"
    f = find_font(font)
    if f and has_filter("drawtext"):
        shutil.copyfile(f, out.parent / "font.ttf")
        (out.parent / f"{code}.txt").write_text(code.upper())
        (out.parent / f"{code}-ip.txt").write_text(ip or "")
        g += "," + drawtext(f"{code}.txt", 520, "(w-tw)/2", "(h-th)/2-60") + "," + \
             drawtext(f"{code}-ip.txt", 64, "(w-tw)/2", "h-160")
    ffmpeg(["-f", "lavfi", "-i", f"color=c={PALETTE[(c + r) % len(PALETTE)]}:s={TW}x{TH}", "-vf", g, *STILL,
            out.name], cwd=out.parent)


def render_test_grid(d, grid):
    """The alignment check: colour bars, 128/512 px lines, a circle and two diagonals across the whole canvas."""
    cols, rows, gx, gy = grid
    W, H = canvas_size(cols, rows, gx, gy)
    d.mkdir(parents=True, exist_ok=True)
    red = (f"lt(abs(hypot(X-{W / 2},Y-{H / 2})-{min(W, H) * 0.45}),10)+lt(abs(X-Y*{W}/{H}),6)"
           f"+lt(abs(X-({W}-Y*{W}/{H})),6)")
    graph = (f"[0:v]drawgrid=w=128:h=128:t=2:c=white@0.6,drawgrid=w=512:h=512:t=8:c=yellow,format=rgb24,"
             f"geq=r='if({red},255,r(X,Y))':g='if({red},0,g(X,Y))':b='if({red},0,b(X,Y))'[c]")
    cs = codes(cols, rows)
    args = ["-f", "lavfi", "-i", f"testsrc2=s={W}x{H}", "-filter_complex",
            slice_graph(graph, cs, gx, gy, W, preview=True)]
    for code in cs:
        args += ["-map", f"[o_{code}]", *STILL, f"{code}.jpg"]
    ffmpeg(args + ["-map", "[o_preview]", *STILL, "preview.jpg"], cwd=d)
