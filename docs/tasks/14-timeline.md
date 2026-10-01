# 14 Today timeline
Goal: the office lists the next 12 h: time -> what plays.
Server: server/schedule.py `timeline(state, slides, activities, t0, hours, durations, ready) -> [{at, until, level, label}]`: walk resolve() boundary to boundary; merge consecutive loop items into one "Loop: N entries" row; cap 200 rows. server/app.py writes it to wall_status.timeline every 60 s.
DB: new migration supabase/migrations/20261002100003_timeline.sql: `alter table wall_status add column timeline jsonb not null default '[]';`.
Office: wall_screen.dart "Today" block, rows like "17:00–18:00 Takeover: PROTO26".
Tests: tests/test_schedule.py: takeover 17:00-18:00 appears with exact times; announcements every 60 s collapse into one row; empty playlist -> one "Test mode" row.
Accept: uv run python tests/test_schedule.py; flutter analyze && flutter test.
