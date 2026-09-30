# Task 02: Wall server skeleton `server/`

Read `docs/tasks/00-rules.md`, then `docs/PLAN.md` "Protocol", "Precedence" (levels 1-3 and 8 only for now), "Files" (server part), D6/D7/D11. Needs `client/wall.py` from task 01.

`uv add fastapi "uvicorn[standard]"`. Run: `uv run python -m server --cols 5 --rows 5 --media ~/tv-media --cache ~/wall-cache --port 8080`.

- `server/__main__.py` -> calls `server.app.main()`. `server/app.py`: argparse (`--cols --rows --bezel-x --bezel-y --media --cache --cache-gb --port --font`), FastAPI app:
  - `GET /` serves `server/page.html`; `GET /wall.py` serves `client/wall.py`; `/tiles/` static from the cache dir.
  - `WS /ws`: register by `hello.screen`, keep last `status` per screen, measure clock offset (`status.now` vs server time, RTT-compensated via a ping).
  - Tick every 0.5 s: `resolve()` (for now: setup overlay per screen > blackout > stopped > test-mode defaults) -> per-screen `plan`; send only when it changed.
  - `POST /api/identify/{code}` (or `all`), `POST /api/test`, `POST /api/blackout`, `POST /api/play`, `POST /api/stop`; `GET /api/status` (grid of codes a1..e5 from cols/rows, online, last status, clock_ms).
  - State (blackout, playing, anchor) persisted to `<cache>/state.json`.
- `server/render.py` (start of it): `run_ffmpeg(args)`, `identify_tile(code, ip)` -> 1280x1024 JPEG with the big code (drawtext, font from `--font` or DejaVuSans-Bold / a Windows fallback, skip text if no font) and a border; `test_grid(cols, rows)` -> the continuous diagonal/circle grid canvas (see `docs/pi-setup.md` "Bench test tile" style; canvas `cols*1280 x rows*1024`, circle + two diagonals + 512 px lines) sliced into per-screen JPEGs; `black_tile()`; defaults = Mosaic of `server/assets/*.jpg|png` normalised to 1280x1024 fit, cycling every 10 s, screen i offset by i; fall back to the test grid if `server/assets/` is empty.
- `server/page.html`: plain HTML/JS, no build. Grid of cards laid out by cols/rows (code, online dot, throttled amber if not 0x0, temp, clock_ms, playing tile), per-card Identify/Test buttons, top bar: Identify all, Test pattern, Blackout, Play/Stop. Poll `/api/status` every 2 s.
- `scripts/wall.sh start|stop|status [codes...]` (bash 3.2 safe, see AGENTS.md): default codes = all 25; for each, sequentially, `ssh wall-$c.local` to start/stop the client as in pi-setup.md.

Test: `tests/test_render.py` (canvas size and crop offsets for 5x5 with and without bezel: e5 x = 4*(1280+gx); ffmpeg smoke test on a 2x2 test grid: 4 JPEGs of 1280x1024 via ffprobe, skipped with a message if ffmpeg is missing).

Docs: README "Running the server" (node: tmux, `sudo ufw allow from 192.168.1.0/24 to any port 8080`), ROADMAP marks progress.

Done when: tests pass; locally `uv run python -m server --cols 2 --rows 2 --cache /tmp/wc` + `uv run --script client/wall.py --screen a1 --server ws://127.0.0.1:8080/ws --mpv-args=--vo=null` shows a1 online on http://127.0.0.1:8080/ and Identify makes the client load the identify tile (visible in its log).
