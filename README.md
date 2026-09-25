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

**Layout.** Rows/cols live only on the server. Screens numbered 1..N from top-left, left to right, then down. A Pi knows only its number. 5×3 canvas = 6400 × 3072.

**Composition.** Fit / Fill / Center. Logo, event title, credits, matte/frame baked into the canvas before slicing, so they cross screen borders correctly.

**Software.** Server: Python + uv, FastAPI + Uvicorn, FFmpeg only (no Pillow), plain HTML/JS page, WebSocket to Pis. Pi client: Python + uv, mpv, websockets. Manual `uv run`, no systemd, no Docker. Server prepares everything; Pis download their tile and play it. Sync: preload, then `play_at` timestamp, chrony on all Pis; millisecond sync not needed. Dropped: Godot (not needed for pre-rendered media; stays a thesis idea), PiWall.

**Media.** Photo first, then HD/4K video. Tiles 1280×1024, same codec/fps/duration/GOP on every tile.
