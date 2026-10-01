# Wall operator panel in the office: from status page to full control

## Context

The office Wall screen (`openlabtwin/apps/office/lib/wall_screen.dart`) already has these controls:
- status line, screen grid and power line;
- Blackout, Stop/Play, Show now…, Back to schedule, Identify all, Test pattern;
- per-screen Identify/Test;
- a playlist editor.

In use it reads as a status page. With the wall off, the stale status takes the top of the page and nothing shows what the wall is doing or will do. There is no preview, no timeline, no one-tap recall, no way to add files from outside the lab, and no way to restart a screen.

The pages also break a few existing rules:
- The server's LAN page (`videowall/server/page.html`) holds things the office lacks: preview, render jobs, per-Pi detail.
- Setup actions were planned to stay on the LAN page, but staff work from the office.

Decisions from the owner (2026-10-01):
- **No zones.** One mode on the whole wall: Mosaic or Videowall.
- **Office upload: yes.**
- **Coding goes to the local model** (Unsloth Studio, Qwen coder, via `pi`). Claude writes briefs and reviews diffs.

Industry practice used as the checklist ([Userful presets](https://www.userful.com/blog/take-a-look-at-userful-video-wall-features-preset-remote-control), [Datapath WallControl 10](https://www.svconline.com/products/datapath-wallcontrol-10-software), [signage CMS monitoring and emergency override](https://www.fugo.ai/digital-signage-tools/wiki/automated-content-scheduling/)):
- one-tap presets for non-admin operators;
- a live preview of the wall;
- an emergency override above the playlist;
- monitoring with last heartbeat per screen;
- dayparting (time-of-day schedule);
- a browser panel that works on a phone.

## The panel (one screen, top to bottom)

| Block | Content | Source |
|---|---|---|
| **1. Now** | Preview image of the wall with screen borders, what plays, until when, what plays next. Wall-off state stated in one line ("Wall server not reporting since 21:40 – screens off or server down"), not a red banner over everything | `wall_status.preview_url`, `playing`, new `next` |
| **2. Controls** | Blackout · Stop/Play · Back to schedule · Identify all · Test pattern · **Emergency message…** (see below) | `wall_state` (exists) |
| **3. Presets** | Buttons, one per playlist entry marked `preset`: one tap = Show now with that entry | `wall_slides.preset` (new bool) |
| **4. Screens** | Grid (exists) + per-screen tap menu: Identify, Test, **Restart client**, **Reboot Pi**; tooltip: last seen, power, temp, drift, SD free | `wall_state.overlay` (exists), new `wall_state.command` |
| **5. Today** | Timeline of the next 12 h: time → entry (loop, takeover, announcement windows) | `wall_status.timeline`, computed by the server with `schedule.resolve` |
| **6. Playlist** | Existing editor + "Show now" on each row + preset star | exists |
| **7. Files** | List from `tv_media` with duration, render state; **Upload** button; delete own uploads | `tv_media`, Storage bucket `wall-upload` |

Layout: a single column on a phone; blocks 1–2 side by side on a wide screen.

## New pieces (small, each one testable)

1. **Preview to the office.**
   - The server already renders `preview.jpg` (640 px canvas with borders) for every videowall render and the test grid.
   - On each change of what plays, the server uploads it to the private Storage bucket `wall-preview`, as `current.jpg` and `next.jpg` (PUT with the service key, through the urllib helper in `server/db.py`).
   - The office shows it through a signed URL.
   - For a mosaic, the server composes a preview with `xstack` from the tiles, which fits `render.py`.
2. **Timeline.** Every 60 s the server calls `resolve()` at each item boundary over the next 12 h and writes a list to `wall_status.timeline` as `[{at, until, level, label}]`. It reuses `schedule.py` and adds no new rules.
3. **Presets.**
   - Database: `wall_slides.preset boolean default false`.
   - Office: a preset row and a star toggle in the editor.
   - Show now sends that row's fields to `wall_state.now`, the existing path.
4. **Emergency message.**
   - The office types text. `wall_state.now = {mode: videowall, text: "...", fit: fit}` with no end time.
   - The server renders text on a black canvas with `drawtext`, so a text source needs no file. In `render.py` that's a new input: `-f lavfi color` plus a text file, then the same slice graph.
   - Priority is that of `now`: above takeover and the playlist, below blackout. That matches the signage "emergency channel".
   - It stays until "Back to schedule".
5. **Restart client / Reboot Pi from the office.**
   - Database: `wall_state.command jsonb {kind: restart|reboot, code: a1|all, at}`.
   - The server forwards it over the WebSocket as `{t: "command", kind}`.
   - The client: `restart` re-execs itself, `reboot` runs `sudo systemctl reboot` (passwordless sudo exists).
   - "All" is staggered 30 s per Pi by the server, the same pattern as today's manual staggered reboot, against peak current.
6. **Upload.**
   - Private Storage bucket `wall-upload`; staff can insert and delete their own objects (RLS on `storage.objects`, `is_staff()`).
   - Every 30 s the server lists the bucket and downloads new objects into `--media` (`~/tv-media`) under the same name. Each one is downloaded once; a server-side file `uploads.json` records what was already fetched.
   - `tv.py` picks the files up for the TV too. That's one library, D1 of the previous plan.
   - Limit 2 GB per file (bucket setting). The office uses `supabase_flutter` storage `upload` with progress.
7. **Wall-off state.**
   - `wallStatusLine` already reports staleness. The panel shows the stale state as one grey line ("Wall off or server down since HH:MM; last screens: 10/10"). Controls stay usable; they apply when the wall comes back, because the server reads `wall_state` on start.
   - Grid squares turn grey with "last seen HH:MM".
8. **Dayparting for power and heat (optional knob):** a `wall_state.sleep` window, for example `{"from":"20:00","to":"08:00"}`. In it, the server sends black plans, and the clients stop mpv and turn HDMI off (`kmsprint`/`wlr-randr` to be verified on the Pi; fallback: black only). This saves the 34 W per monitor at night and keeps the Pis cool.

Not included: zones (owner decision), user roles (all staff are equal today), screenshots from the Pis (mpv over DRM has no cheap capture; the preview shows the intended picture).

## Database (openlabtwin, migration `20261002100000_wall_panel.sql`)

- `alter table wall_slides add column preset boolean not null default false;`
- `alter table wall_state add column command jsonb check (...kind in ('restart','reboot')...), add column sleep jsonb;`
- `alter table wall_status add column timeline jsonb not null default '[]', add column preview_at timestamptz;`
- Storage buckets `wall-preview` (private; read by staff, written by the service key) and `wall-upload` (private; staff insert, select and delete). Policies use `is_staff()`, copying `20260926110000_storage_quality.sql`, which already sets bucket policies.
- pgTAP: extend `12_wall.test.sql` (preset default, command check, bucket policies exist).

## Files

**videowall:**
- `server/app.py`: preview upload on change, timeline, command forwarding with stagger, upload sync, sleep window.
- `server/render.py`: `render_text()` and `mosaic_preview()`.
- `server/db.py`: `storage_put()`, `storage_list()`, `storage_get()`.
- `client/wall.py`: `command` handler (restart, reboot, display off/on).
- Tests: `tests/test_render.py` (text render, mosaic preview size), `tests/test_schedule.py` (timeline from `resolve`), `tests/test_db.py` (storage request shapes).

**openlabtwin:**
- `apps/office/lib/wall_screen.dart`, restructured into the 7 blocks.
- `logic.dart`: `wallTimelineRows`, `wallStaleLine`; `WallSlide.preset`.
- `data.dart`: preview signed URL, upload, command.
- `test/logic_test.dart`.
- Docs: `STAFF-GUIDE.md` (operator guide for the panel), `ARCHITECTURE.md`.

## Who writes it: Codex CLI on the local Unsloth model

**Setup, once:**
- Unsloth Studio running with the Qwen coder loaded. The user starts it; its API was not answering when last checked.
- Codex profile `unsloth` in `~/.codex/config.toml`, the same shape as the existing `ollama-launch` provider: `[model_providers.unsloth] base_url = "http://localhost:<studio port>/v1"`, `[profiles.unsloth] model_provider = "unsloth"`. Or `unsloth start codex`, which writes this.
- A Claude Code allow rule for `codex exec`, which the user adds with `/permissions`, because auto mode blocked unattended agent launches before.

**Per task (agent-workflow best practices):**
1. **Brief.** Claude writes one short brief per piece (about 15 lines) in `videowall/docs/tasks/1x-*.md`: goal, the exact files and function names, the acceptance test command, "do not touch" list. Project rules come from `AGENTS.md`, which Codex reads automatically, so briefs don't repeat them.
2. **Isolate.** One git worktree per task, on branch `task/1x-name`. A failed run is dropped with `git worktree remove`.
3. **Run.** `codex exec -p unsloth -s workspace-write -C <worktree> "$(cat brief)"`, one task at a time.
4. **Gate on tests.** The task's test command runs after Codex finishes. On failure, the output goes back to Codex once with the same brief. If it fails twice, Claude writes that piece directly.
5. **Review.** Claude reads only `git diff --stat` and the test output, and opens a file only for hot paths: the reboot stagger, RLS and Storage policies, anything with the service key.
6. **Merge.** One commit per task, with that task's doc updates in the same commit (AGENTS.md rule), then a fast-forward into `main`.

**Housekeeping after each task:**
- Remove the worktree and delete the task branch.
- Mark the brief done in `docs/ROADMAP.md`, and delete briefs that are done.
- Keep `.DS_Store` ignored in both repos.
- Push both repos at the end of each deployable step. A push to openlabtwin `main` deploys the office.
- Restart the wall server on the node after server changes (rsync + tmux restart, as now).

**Docs updated per step:**
- videowall: `README.md` (server options, panel features), `docs/ROADMAP.md`, `docs/pi-setup.md` (client commands, sleep).
- openlabtwin: `docs/STAFF-GUIDE.md` (operator guide for the panel), `docs/ARCHITECTURE.md` (new columns and buckets), `docs/ROADMAP.md`.

**Order** (each step deployable on its own):
1. wall-off state and layout;
2. presets;
3. preview;
4. timeline;
5. restart/reboot;
6. emergency text;
7. upload;
8. sleep window.

The briefs from the first build (`docs/tasks/00-08`) are done and get deleted in step 1's housekeeping.

## Verification

- Tests: `uv run python tests/test_*.py`; in openlabtwin `scripts/sqltest.py` (with `SUPABASE_PROJECT_REF`), then `flutter analyze` and `flutter test`.
- With the wall on (rows 1–2):
  - each office button changes the wall within 4 s;
  - the preview matches the screens;
  - the timeline matches the next takeover set for a test time;
  - Reboot all reboots the Pis 30 s apart and they return through the autostart;
  - an uploaded file appears in the file list and plays within 2 min;
  - the emergency text shows on all screens until Back to schedule.
- With the wall off: the panel shows one grey stale line, and the controls stay usable.
