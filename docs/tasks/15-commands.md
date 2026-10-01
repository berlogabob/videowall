# 15 Restart client / Reboot Pi from the office
Goal: per-screen and "all" Restart client and Reboot Pi.
DB: new migration supabase/migrations/20261002100004_commands.sql: `alter table wall_state add column command jsonb check (command is null or (command->>'kind' in ('restart','reboot') and command ? 'code' and command ? 'at'));`.
Server: app.py office(): a command whose `at` was not executed before runs once; 'all' sends {t:"command",kind} to one screen every 30 s (a1, b1, ...); else to that screen. Last executed `at` kept in state.json.
Client: client/wall.py on {t:"command"}: restart -> os.execv(sys.executable, [sys.executable, *sys.argv]); reboot -> sudo systemctl reboot. Pure `command_argv(kind)` for the test.
Office: screen tap menu adds "Restart client", "Reboot Pi"; controls add "Reboot all (30 s apart)" with a confirm dialog.
Tests: tests/test_db.py command mapping; tests/test_client.py command_argv.
Accept: uv run python tests/test_*.py; flutter analyze && flutter test.
Do not touch: scripts/pi-setup.sh.
