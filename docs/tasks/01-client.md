# Task 01: Pi client `client/wall.py`

Read `docs/tasks/00-rules.md`, then `docs/PLAN.md` sections "Storage" (Pi cache), "Protocol", and D6/D7.

Build `client/wall.py`, one file with a PEP 723 header (`dependencies = ["websockets"]`, `requires-python = ">=3.11"`), run on a Pi as `uv run --script wall.py [--server ws://192.168.1.131:8080/ws]`.

- Screen code from hostname: `wall-c4` -> `c4`; `--screen` overrides (for testing on a Mac).
- Starts and supervises one `mpv --idle --force-window --fs --keep-open=always --image-display-duration=inf --hwdec=no --no-osc --osd-level=0 --no-audio --input-ipc-server=<sock>`; talks JSON IPC over the unix socket (asyncio). Restart mpv if it exits. `--mpv-args` extra flags (e.g. `--vo=null` for tests).
- Protocol exactly as in PLAN "Protocol": send `hello`, `status` every 5 s (`throttled` from `vcgencmd get_throttled` if present, `temp` from `/sys/class/thermal/thermal_zone0/temp`, `free_mb`, `now=time.time()`), `ready`, `error`. Receive `plan` (replaces the whole plan; `items: []` = black: load a black frame via `av://lavfi:color=black:s=1280x1024` or `stop` + black background).
- Cache `~/wall-cache/`: download `url` (relative to the server's http base) to `<tile>.part`, check Content-Length, rename; send `ready`. Touch mtime on use. Keep >= 2 GB free: delete oldest-mtime files not in the current plan. Save the last plan to `~/wall-cache/plan.json`; on start without a server, play it.
- Switching: loop every 100 ms, pick the item with `at <= now < until` (last item keeps looping when past its `until` or disconnected). Switch at `at - lead` (`lead` = EWMA of loadfile -> `playback-restart` event time, start 0.25 s), `loadfile` with `start=<(now+lead-at) mod period>` for video, paused-then-unpause at `at`.
- Drift (video only), every 1 s: `err = time-pos - expected` (wrap-aware, expected = `(now-at) mod period`); `|err| > 1 s` seek absolute; `0.04 < |err| <= 1` set `speed = 1 - clamp(err/5, -0.05, 0.05)`; else speed 1. Report `drift_ms`, `dropped` (mpv `frame-drop-count`).
- Reconnect with backoff 1-5 s. `websockets` imported inside `main()` so the pure functions import without it.

Pure functions (no I/O) so they are testable: `screen_from_hostname`, `current_item(items, now)`, `expected_pos(item, now)`, `drift_action(err) -> ("seek", x) | ("speed", s) | None`, `evict(files, keep, free_mb, need_mb) -> list to delete`.

Test: `tests/test_client.py` covering those five functions (edge cases: loop wrap, past-last-until, no items, pinned files never evicted).

Docs: `docs/pi-setup.md` new section "Running the client" (start: `curl -sO http://192.168.1.131:8080/wall.py && setsid nohup uv run --script wall.py >wall.log 2>&1 &`).

Done when: `uv run python tests/test_client.py` passes and `uv run --script client/wall.py --screen a1 --mpv-args=--vo=null --server ws://127.0.0.1:9` starts, logs reconnect attempts, and exits cleanly on Ctrl-C.
