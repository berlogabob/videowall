# Task 06: Supabase link on the wall server

Read `docs/tasks/00-rules.md`, then `docs/PLAN.md` "Tables", "Precedence" level 4, D10, and openlabtwin `scripts/db.py` (read `../openlabtwin/scripts/db.py`).

- `server/db.py`: copy of openlabtwin `scripts/db.py` request/select (urllib PostgREST, `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` env). Without the env vars the server stays standalone (playlist.json + state.json) - log once.
- Poll every 2 s: `wall_state` (id=1: blackout, playing, now, now_at, now_until) and, every 30 s or when `wall_state` changes, `wall_slides` (explicit column list), today's `activities` rows referenced by `activity_id` (id,title,starts_at,ends_at,rrule,exdates,status). Keep the last good copy in `<cache>/last-db.json`; on errors keep playing from it.
- Heartbeat every 10 s: upsert `wall_status` id=1 (`on_conflict=id`, `Prefer: resolution=merge-duplicates,return=minimal`) with seen_at, playing (human text like "Videowall: intro.mp4", "Takeover: X until 20:00", "Blackout"), screens (per code: on, tile, drift_ms, throttled, free_mb, clock_ms), slides (id -> state), cache_mb, disk_free_mb, error, error_at.
- With Supabase on, the LAN page's blackout/play/stop/now write to `wall_state` too (same row the office edits), so both stay in agreement; playlist editing on the LAN page becomes read-only ("edit in the office").

Test: `tests/test_db.py`: row -> internal state mapping, heartbeat payload shape, fallback to last-db.json when the request raises (monkeypatch the request function; no network).

Docs: README (env vars, `set -a; . ~/openlabtwin/.env; set +a` before `uv run python -m server` in tmux), ROADMAP.

Done when: tests pass.
