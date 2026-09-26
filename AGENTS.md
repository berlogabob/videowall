# Agent notes

Start here in a new session: `README.md` (what and why), `docs/ROADMAP.md` (state and next step), `docs/pi-setup.md` (the Pis).

Docs are part of every change. A commit that changes behaviour, commands, hardware facts or setup updates the matching doc in the same commit:
- `README.md`: summary, links;
- `docs/ROADMAP.md`: what's next (mark progress, remove done items, add new ones);
- `docs/pi-setup.md`: flashing and `scripts/pi-setup.sh`.

Rules from the owner:
- Python through `uv` only (`uv run`, `uv add`); never system pip. No Docker. No systemd until the MVP is stable: everything starts by hand with `uv run`. The server must also run on Windows.
- Docs in English.
- Keep it minimal: the server prepares everything (FFmpeg only, no Pillow), Pis only download and play (mpv).
- Two modes only: Mosaic (one file per screen) and Videowall (one picture split across all). "Same media" is not a separate mode.
- Rows and cols live only on the server; a Pi knows only its number (1 = top-left, left to right, then down).

Gotchas the code doesn't show:
- openlabtwin (github.com/berlogabob/openlabtwin) is the one entry point: its office app will control the wall through Supabase tables `wall_state` / `wall_status` that this server polls. The office can't call this server directly (HTTPS page, plain-http LAN server).
- Lab access: the Mac reaches the lab over Tailscale; the node `techlab-01` (`ssh -i ~/.ssh/techlab TechLAB@techlab-01`) is the jump host and resolves `wall-NN.local`.
- `scripts/pi-setup.sh` has never run on a real Pi yet; only `tests/test_pi_setup.sh` (boot-file edits) has run.
- The Mac's `/usr/bin/env bash` is bash 3.2: no `wait -n`, no empty arrays under `set -u` in scripts that run on the Mac.
