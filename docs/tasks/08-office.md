# Task 08 (repo openlabtwin): wall tables and office Wall screen

Work in `../openlabtwin`. Read its `AGENTS.md`, `docs/ARCHITECTURE.md`, and in videowall `docs/PLAN.md` "Tables", "Precedence", D3/D4/D10.

- `supabase/migrations/20261001100000_wall.sql`: tables `wall_slides`, `wall_state` (one row inserted), `wall_status` exactly as PLAN "Tables"; RLS and grants copied from the TV migrations (`20260924200000_tv_showcase.sql`, `20260925150000_tv_status.sql`, `20260929120000_tv_every.sql`); audit triggers on wall_slides and wall_state.
- `supabase/tests/database/12_wall.test.sql` (pgTAP, copy style of `06_tv.test.sql`; top-level selects at column 0): RLS on all 3; anon reads nothing; staff can't write wall_status or insert a second wall_state; videowall needs exactly 1 file; time-order/every/fit checks.
- Office (Flutter, `apps/office/lib/`): `logic.dart` `WallSlide` (fromRow/toRow/problem(): takeover needs an end like TvSlide), `wallStatusLine` (stale after 60 s, error newer than seen_at), `wallGrid` (sort status keys: columns by letter, rows by number). `data.dart`: wallSlides, wallState, wallStatus, saveWallSlide, deleteWallSlide, setWallState. New `wall_screen.dart` copying `tv_screen.dart` patterns: status line + grid of screens (green/amber/grey), Blackout, Play/Stop, "Show now" (mode, file from `tv_media`, fit) and "Back to schedule", slide list + editor (all wall_slides fields, activity picker like the TV form), ready badges from wall_status.slides; 5 s refresh timer. Nav button next to TV in `bookings.dart`.
- Tests: `apps/office/test/logic_test.dart` for WallSlide.problem, wallStatusLine, wallGrid.
- Docs: ARCHITECTURE.md (tables), STAFF-GUIDE.md (Wall screen), edge-node.md (wall server on the node: tmux, ufw 8080 from 192.168.1.0/24), ROADMAP.md.
- Do NOT run `scripts/sqltest.py` (it applies migrations to the live database) and do not push. `flutter analyze` and `flutter test` in apps/office must pass.

Done when: flutter analyze + flutter test pass.
