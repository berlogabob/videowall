# videowall

Old Samsung monitors turned into one video wall for the IADE Tech Lab: one Raspberry Pi per screen, a Python + FFmpeg server that prepares everything, mpv on each Pi.

Controlled from [openlabtwin](https://github.com/berlogabob/openlabtwin) (office app) through two Supabase tables; setup tools live on this server's own LAN page. Plan: [docs/ROADMAP.md](docs/ROADMAP.md). Setting up the Pis: [docs/pi-setup.md](docs/pi-setup.md).

## How it fits with openlabtwin

This repo holds the wall itself (render server + Pi client). openlabtwin stays the one entry point: it owns two small Supabase tables and an office screen, nothing else.

Why split: different runtime (Python on the lab LAN, 15–25 Pis, heavy FFmpeg) vs openlabtwin (Supabase + Jaspr + Flutter on Pages); must run standalone on a laptop or Windows for the professor; may go open source on its own.

Why control goes through the DB, not HTTP: the office app is HTTPS on GitHub Pages, the wall server is plain http on the LAN, so the browser blocks direct calls (same blocker as "upload from the office"). The TV already solves this: `tv.py` on the node polls tables, writes `tv_status`. The wall server does the same with `wall_state` (mode, playing, blackout) and `wall_status` (heartbeat, online Pis). Poll every few seconds.

Setup-only actions (identify screen, test pattern, per-Pi status) stay in the wall server's own LAN web page. The office gets mode switch, play/stop, blackout, status.

## Summary

**Hardware.** Samsung SyncMaster 720N, 17", 1280×1024 5:4, VGA only, VESA 100×100, <34 W. Grid now 5 cols × 3 rows (15 screens), next 5×5 (25), target 6×6 (36). One Raspberry Pi per screen (Pi 3B+ on hand) through an HDMI→VGA adapter, wired Ethernet. Switch TP-Link TL-SG1024D, 24 ports: enough for 15 + server, not for 25 + server (second switch or 48-port). Power: shared multi-port USB charger, 5 V / 2 A per port, below the Pi 3B+'s 2.5 A: undervoltage risk, check `vcgencmd get_throttled`.

**Mount.** 3D-printed bracket on the monitor's stand/VESA holes, carrying the Pi and a cable coil for slack. From the notes: HDMI plug sticks out 55 mm, power plug 20 mm; inner height 25–30 mm for air; coil inner area about 85 × 65 mm, cable bundle ø20 mm; plate about 54 × 33.5 mm; hole pitch about 40 mm horizontal, 15 mm vertical. Several values marked uncertain, measure again before printing.

**Modes.** Mosaic: each screen shows its own file from the pool, cycling like a photo frame. Videowall: one picture or video split across all screens. "Same media" is a case of Mosaic, not shown as a mode. Test mode: when the pool is empty, show bundled images (institute logo, lab photos, staff). Switching must be easy (office button).

**Layout.** Rows/cols live only on the server. Each screen has a grid code: letter = column, number = row, A1 top-left, so a 5×5 grid ends at E5. A Pi knows only its code (hostname `wall-a1`). Start: 2 screens, A1 and B1. 5×3 canvas = 6400 × 3072.

**Composition.** Fit / Fill / Center. Logo, event title, credits, matte/frame baked into the canvas before slicing, so they cross screen borders correctly.

**Software.** Server: Python + uv, FastAPI + Uvicorn, FFmpeg only (no Pillow), plain HTML/JS page, WebSocket to Pis. Pi client: Python + uv, mpv, websockets. Manual `uv run`, no systemd, no Docker. Server prepares everything; Pis download their tile and play it. Sync: preload, then `play_at` timestamp, chrony on all Pis; millisecond sync not needed. Dropped: Godot (not needed for pre-rendered media; stays a thesis idea), PiWall.

**Media.** Photo first, then HD/4K video. Tiles 1280×1024, same codec/fps/duration/GOP on every tile.

## Running

Design: [docs/PLAN.md](docs/PLAN.md). Parts: `server/` (FastAPI + FFmpeg, on the node), `client/wall.py` (one per Pi, mpv), `scripts/wall.sh` (start/stop the clients).

**Server** (node `techlab-01`, in tmux; also runs on a laptop or Windows with a local media folder):

```sh
cd ~/videowall && uv sync
set -a; . ~/openlabtwin/.env; set +a          # optional: the office link (SUPABASE_URL, SUPABASE_SERVICE_KEY)
tmux new -s wall 'uv run python -m server --cols 5 --rows 5 --media ~/tv-media --cache ~/wall-cache'
```

The Pis reach it on port 8080; the node's firewall needs, once: `sudo ufw allow from 192.168.1.0/24 to any port 8080`. LAN page: `http://192.168.1.131:8080/`. Options: `--bezel-x/--bezel-y` (px hidden behind the frames, bezel mm / 0.264), `--cache-gb` (render cache budget, default 60), `--font`.

**Clients** (from the Mac, one Pi at a time): `scripts/wall.sh start` (all 25), `scripts/wall.sh start a1 b1`, `scripts/wall.sh status`, `scripts/wall.sh stop`. Each Pi downloads `wall.py` from the server and runs it with `uv run --script`.

**What shows** (first match wins): Identify/Test overlay from the LAN page, blackout, stopped (logo or black), "show now", takeover, announcement, the playlist loop, test-mode defaults (`server/assets/`, else the test grid). The playlist uses the TV's rules: dates, times of day, takeover, `every_seconds` announcements, links to schedule activities. Without Supabase it is `~/wall-cache/playlist.json`, edited on the LAN page; with Supabase it is the office's `wall_slides` table.

**Media**: the TV's share (`smb://192.168.1.131/tv`, `~/tv-media`). Renders go to `~/wall-cache/tiles/` (never into the share). Measured on the node: a 39.4 s 1080p clip renders to 25 video tiles in about 113 s (2.9× real time), 405 MB.

**Tests**: `uv run python tests/test_client.py`, `test_render.py` (FFmpeg smoke renders on a 2×2 grid), `test_schedule.py`, `test_db.py`; `bash tests/test_pi_setup.sh`.
