"""Pure parts of client/wall.py: naming, item pick, loop position, drift, SD eviction."""
import importlib.util, pathlib

spec = importlib.util.spec_from_file_location("wall", pathlib.Path(__file__).parent.parent / "client" / "wall.py")
w = importlib.util.module_from_spec(spec); spec.loader.exec_module(w)

assert w.screen_from_hostname("wall-c4") == "c4" and w.screen_from_hostname("WALL-E5.local") == "e5"
assert w.command_argv("restart") == [w.sys.executable, *w.sys.argv]
assert w.command_argv("reboot") == ["sudo", "systemctl", "reboot"]

items = [{"tile": "x", "at": 100}, {"tile": "y", "at": 160}]
assert w.current_item(items, 99) is None
assert w.current_item(items, 100)["tile"] == "x" and w.current_item(items, 159.9)["tile"] == "x"
assert w.current_item(items, 1e9)["tile"] == "y"          # past the last: keep the last
assert w.current_item([], 5) is None

v = {"at": 100, "period": 60}
assert w.expected_pos(v, 90) == 0 and w.expected_pos(v, 130) == 30
assert abs(w.expected_pos(v, 100 + 3 * 60 + 12.5) - 12.5) < 1e-9   # several loops
assert w.expected_pos({"at": 0}, 7) == 7
assert abs(w.wrap_err(59.9, 0.1, 60) - (-0.2)) < 1e-9     # across the loop seam
assert abs(w.wrap_err(0.1, 59.9, 60) - 0.2) < 1e-9

assert w.drift_action(1.5) == ("seek", None)
assert w.drift_action(0.01) == ("speed", 1.0)
kind, s = w.drift_action(0.5); assert kind == "speed" and s == 0.95   # clamped to 5 %
assert w.drift_action(0.1) == ("speed", 1.0)
kind, s = w.drift_action(-0.11); assert abs(s - 1.022) < 1e-9

files = {"old": (1, 500), "mid": (2, 500), "new": (3, 500), "plan.json": (0, 0)}
assert w.evict(files, {"old", "plan.json"}, free_mb=1000) == ["mid", "new"]
assert w.evict(files, set(), free_mb=5000) == []
assert w.evict(files, {"old", "mid", "new", "plan.json"}, free_mb=0) == []
print("client: ok")
