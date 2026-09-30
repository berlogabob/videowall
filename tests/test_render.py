"""Grid maths, filters, cache keys and eviction; FFmpeg smoke renders on a 2x2 grid when ffmpeg is present."""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from server import render as r

assert r.codes(5, 5)[:6] == ["a1", "b1", "c1", "d1", "e1", "a2"] and r.codes(5, 5)[-1] == "e5"
assert r.canvas_size(5, 5) == (6400, 5120) and r.canvas_size(5, 5, 40, 30) == (6400 + 160, 5120 + 120)
assert r.crop_xy("a1", 40, 30) == (0, 0) and r.crop_xy("e5", 40, 30) == (4 * 1320, 4 * 1054)
assert r.canvas_size(2, 1, 41, 0) == (2600, 1024)       # odd bezel rounds to even
assert r.bezel_px(10) == 38

assert "decrease" in r.fit_filter("fit", 10, 10) and "increase" in r.fit_filter("fill", 10, 10)
assert "scale" not in r.fit_filter("center", 10, 10)

g, W, H = r.canvas_graph(5, 5, 0, 0, "fit", matte=100, title=True, credits=False, logo=True)
assert "title.txt" in g and "credits.txt" not in g and "overlay" in g and "pad=6400:5120:100:100" in g
g2, *_ = r.canvas_graph(5, 5)
assert "drawtext" not in g2 and "overlay" not in g2
s = r.slice_graph(g2, r.codes(5, 5), 0, 0, W)
assert s.count("crop=1280:1024") == 25 and "split=25" in s and "crop=1280:1024:5120:4096[o_e5]" in s

assert r.key("a.jpg", 1, "fit") != r.key("a.jpg", 1, "fill") and r.key("a.jpg", 1, "fit") == r.key("a.jpg", 1, "fit")
e = {"old": (1, 50), "mid": (2, 50), "new": (3, 50)}
assert r.evict_plan(e, {"old"}, budget=100) == ["mid"]
assert r.evict_plan(e, set(), budget=1000) == []
assert r.evict_plan(e, {"old", "mid", "new"}, budget=0) == []

if not shutil.which("ffmpeg"):
    print("render: ok (ffmpeg missing, smoke renders skipped)"); sys.exit()


def dims(p):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                        "stream=width,height,nb_read_frames,r_frame_rate", "-of", "json", str(p)],
                       capture_output=True, text=True).stdout
    return json.loads(o)["streams"][0]


with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    grid = (2, 2, 0, 0)
    r.render_test_grid(t / "grid", grid)
    assert sorted(p.name for p in (t / "grid").glob("*.jpg")) == ["a1.jpg", "a2.jpg", "b1.jpg", "b2.jpg", "preview.jpg"]
    assert (dims(t / "grid" / "b2.jpg")["width"], dims(t / "grid" / "b2.jpg")["height"]) == (1280, 1024)

    src = t / "src.mp4"
    r.ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30", "-t", "2", "-pix_fmt", "yuv420p", str(src)])
    r.render_videowall(src, t / "vw", grid, fit="fill", video=True, poster=True)
    r.render_videowall(src, t / "vw", grid, fit="fill", video=True, duration=2)
    frames = set()
    for c in r.codes(2, 2):
        d = dims(t / "vw" / f"{c}.mp4")
        assert (d["width"], d["height"], d["r_frame_rate"]) == (1280, 1024, "30/1"), d
        frames.add(d["nb_read_frames"])
        assert (t / "vw" / f"poster-{c}.jpg").exists()
    assert len(frames) == 1, frames                                   # every tile the same length
    assert dims(t / "vw" / "preview.jpg")["width"] == 640

    r.render_tile(src, t / "m" / "tile.jpg", "center")
    assert dims(t / "m" / "tile.jpg")["width"] == 1280
    r.render_identify("c4", "192.168.1.9", t / "id" / "c4.jpg")
    assert (t / "id" / "c4.jpg").exists()

    c = r.Cache(t / "cache", 1)
    (c.dir("k1")).mkdir(parents=True); (c.dir("k1") / "a1.jpg").write_bytes(b"x" * 10); c.finish("k1")
    assert c.ready("k1") and c.meta("k1")["bytes"] == 10 and not c.ready("k2")
print("render: ok")
