# Rules for every task (read first)

- Repo: videowall. Read `AGENTS.md`, `README.md`, `docs/PLAN.md` (the design; sections named in each task are binding).
- Python 3.13 through `uv` only (`uv add`, `uv run`). No pip, no Docker, no systemd. FFmpeg only for images/video (no Pillow).
- Must also run on Windows (no POSIX-only calls in `server/`; the Pi client may be Linux-only).
- Minimal: fewest files, stdlib first, no abstractions with one user. Match the existing style: short, plain comments, `ponytail:` comment on deliberate shortcuts.
- Tests are plain assert scripts: `uv run python tests/test_x.py` prints `... ok` and exits 0. No pytest.
- Update the docs named in the task in the same change (English).
- Do not touch `scripts/pi-setup.sh` unless the task says so. Do not commit; leave changes in the working tree.
