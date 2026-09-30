# Video wall 5×5, built on openlabtwin's TV, schedule and storage

## Context

The wall is one more screen in the lab's existing content system, not a standalone player. openlabtwin already has four pieces the wall reuses:
- **One media library:** the Samba `[tv]` share at `~/tv-media` on node `techlab-01`, probed into `tv_media`.
- **A scheduled playlist:** `tv_slides`, with date and time windows, `takeover`, `every_seconds` announcements and `activity_id` links to the lab schedule (`activities`, rrule).
- **A node heartbeat:** `tv_status`.
- **An office screen:** `tv_screen.dart`.

The TV page (`apps/tv/index.html`) already syncs by clock. The loop is anchored to the epoch, an announcement shows while `t % every < seconds`, and the next item preloads 5 s ahead. The wall uses the same model, so TV and wall switch to a linked event in the same second.

Today's facts:
- 6 Pis (A1–B3) are set up and cable only, with 32 GB SD cards (24 GB free).
- The node has an i7-7700K, 46 GB RAM, 197 GB free, FFmpeg 7.1 (drawtext, xstack, drawgrid), uv, Python 3.13 and tmux. ufw opens only ports 80 and 445.
- `tv.py` deletes unknown mp4s in `~/tv-media/.tv/`, so wall renders must live elsewhere.

Owner rules:
- uv only; no Docker; no systemd yet (tmux + `uv run`).
- Standalone on a laptop or Windows without Supabase.
- FFmpeg only; Pis only download and play.
- Rows and cols live only on the server.
- Two modes: Mosaic and Videowall.
- Docs go in the same commit.

**Honest scope:** everything in one day, plus 19 Pis to flash and mount, is not realistic. Tomorrow gives 25 working screens with stills and LAN control, with video as a stretch. The office link, playlists and composition follow over days 2–5, and each day leaves a working wall.

## Who writes the code (spend as few Claude tokens as possible)

Claude orchestrates, reviews and runs the hardware steps. Claude does not write the bulk code.

| Work | Tool | Why |
|---|---|---|
| Task briefs: one file per step in `docs/tasks/NN-name.md`, containing the relevant plan section, files, acceptance test and owner rules | Claude, short | Codex needs self-contained briefs; this is the only prose Claude writes |
| Main implementation (`server/`, `client/wall.py`, `render.py`, `schedule.py`, the openlabtwin migration and Dart) | `codex exec --full-auto -C <repo> "$(cat docs/tasks/NN.md)"` (Codex CLI 0.159, logged in with ChatGPT) | Strong coder, billed outside Claude |
| Small mechanical tasks (test vectors, docs edits, copying `in_window`, the LAN page CSS) | Local model through `unsloth start pi` or `unsloth start codex` on the running Unsloth server, or the `pi-delegate` wrapper (ollama `ornith-1.5:9b`) | Free and local; bounded by the wrapper's verify step |
| Review | Claude reads `git diff --stat` + test output first, and opens files only where a test fails or a hot path changed (sync maths, precedence, RLS) | Keeps Claude's context small |
| Hardware, Pis, node (SSH, flashing, `pi-setup.sh`, ufw, tmux) | Claude, via Bash | Needs this session's SSH setup and judgement |

For each step: Claude writes the brief → Codex implements → the tests run (`uv run python tests/…`, pgTAP, `flutter test`) → on failure the output goes back to Codex (up to 2 retries) → Claude reviews the diff → commit with docs. Codex and pi work in a `git worktree` per step, so a bad run is dropped by removing the worktree.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | The wall server scans the same folder (`--media ~/tv-media`) with its own probe cache, and doesn't read `tv_media` | One share for staff; still works on Windows without Supabase |
| D2 | Renders go in `~/wall-cache/`, outside the share and `.tv/` | `tv.py` deletes unknown mp4s in `.tv/`; staff shouldn't see 25 tiles per item |
| D3 | A separate `wall_slides` table, with the same schedule column names as `tv_slides` | The TV kinds (bio, qr, text) don't apply on the wall, and the wall fields (mode, fit, matte) don't apply on the TV |
| D4 | The same event on TV and wall is linked through `activity_id`; announcements stay in step because both use `t % every` | This mechanism already exists; no shared rows needed |
| D5 | Copy `in_window`, `link_events` and `occurrences` (~35 lines) into `server/schedule.py`, noting the openlabtwin sha | `tv.py` imports `db` and `export` when it loads, and Windows has no checkout |
| D6 | The server evaluates the schedule on its own clock every 0.5 s and sends absolute timestamps | Pis stay dumb players; rejoining is free |
| D7 | One server-to-Pi message, `plan` (the current and next items); Identify and test pattern are plans too | One code path on the Pi |
| D8 | Mosaic tiles are keyed per file, videowall tiles per item | Reuse across items |
| D9 | Every videowall item gets a still poster first (~3 s) | A takeover whose video isn't ready still shows something on time |
| D10 | Office "show this now" = `wall_state.now` jsonb, shaped like a slide row | Quick buttons without junk rows; standalone mode keeps the same thing in `state.json` |
| D11 | The server serves tiles itself (FastAPI static on :8080) | Same on node, laptop and Windows |

## Tables (openlabtwin, migration `20261001100000_wall.sql`)

- **`wall_slides`:**
  - `mode` (mosaic|videowall), `title`, `media_names text[]` (videowall exactly 1; mosaic `{}` = every file), `seconds`, `cycle_seconds`;
  - `fit` (fit|fill|center), `show_title`, `credits`, `logo`, `matte` (0–400 px);
  - `position`, `active`, `starts_on`, `ends_on`, `from_time`, `to_time`, `takeover`, `every_seconds`, `activity_id → activities`;
  - checks copied from `tv_slides` (time order, `every > seconds`);
  - RLS `staff_all`, audit trigger.
- **`wall_state`**, one row with `id=1`:
  - `blackout`, `playing`, `now jsonb`, `now_at`, `now_until`;
  - staff may select and update; insert and delete revoked; audited.
- **`wall_status`**, one row written by the server every 10 s:
  - `seen_at`, `playing` (text), `screens jsonb` (per code: on, tile, drift_ms, throttled, free_mb, clock_ms);
  - `slides jsonb` (ready / rendering % / failed), `cache_mb`, `disk_free_mb`, `error`, `error_at`;
  - staff read only.
- anon is revoked on all three. The office grid layout comes from the keys of `screens`, so rows and cols stay on the server.

## Storage

- **Server cache:** `~/wall-cache/<key>/` holds `a1..e5.{mp4,jpg}`, `poster-*.jpg` and `meta.json`.
  - `key = sha256(name, size, mtime, mode, composition, grid, bezel, format, RENDER_VERSION)[:16]`.
  - LRU eviction with a `--cache-gb 60` budget. Pinned items are never evicted: today's in-window items, `now`, the defaults, and the identify/test tiles.
  - Before each render the server checks free disk ≥ estimate ×1.2 + 5 GB, otherwise the item is marked `failed: disk`.
- **Video tile format:**
  - libx264 veryfast, High@4.0, 30 fps, `-g 30`, `sc_threshold 0`, 4 Mb/s, yuv420p, `+faststart`, no audio.
  - That's about 30 MB per tile-minute, or 750 MB per wall-minute.
  - Stills are JPEG `q 2`.
- **Pi cache:** `~/wall-cache/`.
  - Downloads go to `.part`, are checked against Content-Length, then renamed.
  - The client keeps at least 2 GB free by evicting the oldest-mtime files outside the current plan.
  - mtime is touched on use, because the SD card is mounted `noatime`.

## Protocol (WebSocket `ws://node:8080/ws`, JSON)

- **Pi → server:**
  - `hello {screen, have[], free_mb}`;
  - `status {tile, pos, drift_ms, dropped, throttled, temp, free_mb, now}` every 5 s;
  - `ready {tile}`, `error {msg}`.
- **Server → Pi:** `plan {items:[{tile, url, kind, at, until, period}, next]}`.
  - The whole plan is replaced each time; `[]` means black.
  - It is sent on connect, on any change, and at the start of each item.
  - The server measures clock offset from `status.now`.
- **Client:**
  - Downloads the plan items in order.
  - Switches at `at − lead`, where `lead` is an EWMA of loadfile → playback-restart time. The start position is `(now + lead − at) mod period`.
  - Every 1 s it compares its position with the expected one: an error over 1 s → seek; 40 ms–1 s → speed ±5 % max; under 40 ms → speed 1.
  - Keeps looping the last item when it loses the server. The plan is saved to disk, so a reboot without the server plays from cache.
- **mpv:** `--idle --force-window --keep-open=always --image-display-duration=inf --hwdec=no --no-osc --osd-level=0 --input-ipc-server=/tmp/mpv-wall`. The client restarts mpv if it exits.

## Precedence (`schedule.resolve(state, slides, t)`, per tick)

The first level that applies wins:
1. **Setup overlay** from the LAN page (Identify or Test on one Pi, 10 s). It sits above blackout because someone is standing at the wall.
2. **Blackout:** black.
3. **Stopped:** idle card.
4. **`now`,** until `now_until` or "Back to schedule".
5. **Takeover:** only takeover items loop, anchored at that day's `from_time`, so it starts exactly at 17:00:00.
6. **Announcement:** `t % every < seconds`, the TV's formula; the loop keeps running underneath.
7. **Loop:** in-window, ready items, `pos = (t − A) mod L`.
   - The anchor `A` is persisted in `state.json`.
   - A change to the live set applies at the next item boundary, so there's no mid-item cut and a restart doesn't jump.
8. **Test-mode defaults:** a Mosaic of `server/assets/` (logo plus lab photos).

If an item isn't ready: a videowall video falls back to its poster; otherwise the next level down is used.

## Render ahead

- **One worker, `nice -n 10`,** one FFmpeg at a time. It shares the CPU with `tv.py`.
- **Queue order:** posters → `now` → live takeover → next loop item → rest of today → tomorrow (after 22:00).
- **Videowall render:** one decode, then scale/pad/crop to the canvas, then drawtext/overlay/pad (title, credits, logo, matte), then `split=25`, then 25 crops to 25 encoders.
- **Canvas and crops:** `W = C·1280 + (C−1)·gx`, `H = R·1024 + (R−1)·gy`; the crop is at `x = c·(1280+gx)`, `y = r·(1024+gy)`. The bezel gap in px = bezel mm ÷ 0.264.
- **Mosaic:** each file is normalised once to 1280×1024 with fit/fill/center. The LAN page shows a preview: a downscaled canvas with a `drawgrid` overlay.

## Files

**videowall** (`uv add fastapi uvicorn python-dateutil`):
- `server/app.py`
  - args: `--cols 5 --rows 5 --bezel-x/y --media --cache --cache-gb --port 8080 --font`;
  - WebSocket hub, `/tiles/`, `/wall.py` (serves the client), LAN page `/`;
  - the tick, the render worker, and the optional Supabase poll (2 s) and heartbeat (10 s) through urllib, copying openlabtwin `scripts/db.py`;
  - standalone: `state.json` + `playlist.json` in the `wall_slides` row shape.
- `server/render.py`: FFmpeg builders (canvas, compose, slice, poster, mosaic, identify, test pattern), cache keys and eviction, folder scan with a probe cache, and `exif_orientation` copied from `tv.py`.
- `server/schedule.py`: copied window and event logic, timeline, `resolve()`.
- `server/page.html`: 5×5 status grid; per-Pi Identify and Test; file list with "Show now" (mode, fit); preview; blackout and stop; disk and cache.
- `server/assets/`: test-mode defaults. The owner supplies the logo and 3–4 photos; the generated test grid is the fallback.
- `client/wall.py`: one file with a PEP 723 header (`websockets`). Pis start it with `curl -O node:8080/wall.py && setsid nohup uv run --script wall.py &`, run from the Mac by `scripts/wall.sh start|stop`.
- Tests: `tests/test_schedule.py`, `tests/test_render.py`, `tests/test_client.py`.
- Docs: `README.md`, `docs/ROADMAP.md` (replaced by this day order), `docs/pi-setup.md` (25 Pis, second switch, starting the client).

**openlabtwin:**
- the migration above and `supabase/tests/database/12_wall.test.sql`;
- `apps/office/lib/logic.dart`: `WallSlide` with `fromRow`/`toRow`/`problem()`, `wallStatusLine` (stale after 60 s), `wallGrid`;
- `data.dart`: `wallSlides`, `wallState`, `wallStatus`, `saveWallSlide`, `setWallState`;
- a new `wall_screen.dart`, copying `tv_screen.dart`:
  - status grid with a 5 s timer;
  - blackout, play/stop, quick "Mosaic: all" / "Videowall: file…", "Back to schedule";
  - slide list and editor, copying the TV form, with ready badges from `wall_status.slides`;
- a nav button next to TV in `bookings.dart:51-55`;
- `test/logic_test.dart`;
- docs: `ARCHITECTURE.md`, `STAFF-GUIDE.md`, `edge-node.md` (starting the wall server in tmux; ufw `8080 from 192.168.1.0/24` only), `ROADMAP.md`. `edge-setup.sh` is untouched until the MVP is stable.

## Day order (one person; hours are estimates)

**Tomorrow, 2026-10-01: 25 screens, stills, LAN control.** Flash one card every ~4 min between coding blocks (Imager: hostname only, no Wi-Fi).

| Time | Step | Done when |
|---|---|---|
| 08:30–10:00 | `client/wall.py`: hello, plan, status, cache, mpv IPC, switching at `at` | a1 shows a tile from a server stub |
| 10:00–11:30 | `server/app.py` + identify/test tiles + LAN grid; ufw 8080 on the node; server in tmux | 6 Pis show their codes |
| 11:30–13:00 | 19 Pis: sudo step (`sudo -S`), `pi-setup.sh wall-{a..e}{1..5}.local`, reboot, second switch, start clients | 25 green on the LAN page |
| 13:30–15:00 | `render.py`: mosaic stills (fit/fill/center), videowall still (canvas + 25 crops), test-mode defaults, "Show now" | a still wall across 25 screens |
| 15:00–17:00 | Mount and cable the new 19; replace the power supplies on a1, b1, a2 | Identify all shows the right positions; `throttled=0x0` |
| 17:00–18:30 | Stretch: videowall video (x264 tiles, period, drift nudging), measuring drift. Commit with docs | median drift < 50 ms, or noted as day 2 |

**Next days:**

| Day | Hours | Work |
|---|---|---|
| 2 | 5 h | Video sync if it slipped; Pi and server cache eviction; poster fallback; `state.json` anchor; rejoin mid-video |
| 3 | 5 h | openlabtwin link: migration + pgTAP, server poll/heartbeat, office wall screen (status, blackout, play/stop, show now) |
| 4 | 6 h | Schedule: `schedule.py` (windows, takeover, announcements, activity link), render-ahead queue, office slide editor |
| 5 | 5 h | Composition (title, credits, logo, matte), LAN preview with grid, bezel measurement → `--bezel-x/y` |
| Later | | Office preview through a private Storage bucket; "Also on wall" in the TV list; systemd; 6×6 |

## Tests (minimal, assert-based, `uv run python tests/…`)

- **`test_schedule.py`:**
  - window and event vectors copied from openlabtwin `test_tv.py`;
  - loop wrap; the anchor moves only at item boundaries;
  - takeover starts exactly at `from_time`; the announcement formula; only takeover announcements during a takeover;
  - each precedence level beats the next; poster fallback.
- **`test_render.py`:**
  - crop offsets and canvas size for 5×5 with a bezel;
  - the key changes with composition but not with the tile code;
  - eviction keeps pinned items;
  - an FFmpeg smoke test on a 2×2 grid from `lavfi` (4 outputs, dimensions checked with ffprobe).
- **`test_client.py`:** current-item pick, expected position mod period, drift → speed or seek, SD eviction choice.
- **pgTAP `12_wall`:** RLS on all 3; anon reads nothing; staff can't write `wall_status` or add a second `wall_state` row; videowall needs exactly 1 file; the checks.
- **Flutter:** `WallSlide.problem()`, `wallStatusLine` stale after 60 s, `wallGrid` ordering.
- Existing: `bash tests/test_pi_setup.sh`.

## Risks

- **Render time for 25 encodes on 8 threads:** measure on the first clip before promising video takeovers. Fall back to `ultrafast` or a lower bitrate if it's too slow.
- **Pi 3B+ decoding:** 2 dropped frames per 20 s on the bench. Keep 30 fps and 4 Mb/s, and log drops per Pi.
- **mpv switch gap** of 100–300 ms at item changes is accepted; the lead is calibrated per Pi.
- **Under-voltage on the shared USB charger:** amber on the LAN page and in the office.
- **The LAN page has no login:** ufw allows 8080 from `192.168.1.0/24` only.
- **The service key on the server:** explicit column selects; it writes only `wall_status`.
- **Portrait phone photos (EXIF):** test once; if they come out sideways, use the copied `exif_orientation` + `transpose`.

## Verification

- 25 green on the LAN page. "Identify all" shows each code on the right monitor, checked against a photo of the wall.
- The diagonal test grid is continuous across the seams (checks alignment, and the bezel once it's set).
- Video: median drift < 50 ms. Unplug a Pi mid-video: it's back in sync within 5 s. Kill the server: the Pis keep playing, and after a restart the position doesn't jump.
- Set a bad `SUPABASE_URL`: the wall keeps its playlist. With `--cache-gb 1`, evictions are logged and pinned items stay.
- From the office on Pages, as staff: blackout, stop and show now take effect on the wall within 3 s. A takeover linked to an activity at HH:MM starts on the TV and the wall in the same second.
- All test files above pass, plus `uv run python scripts/sqltest.py` and `flutter test` in openlabtwin.
