# 18 Night sleep window
Goal: wall_state.sleep = {"from":"20:00","to":"08:00"}: inside it the server sends black plans and {t:"command",kind:"display",on:false}; outside, on:true.
DB: append `alter table wall_state add column sleep jsonb;`.
Server: schedule.py `in_sleep(sleep, t) -> bool` (windows over midnight); app.py applies it below blackout, above everything else.
Client: display off/on with `vcgencmd display_power 0|1`; if that fails, black only; log which worked.
Office: control "Night sleep 20:00–08:00 [edit]".
Tests: tests/test_schedule.py in_sleep: inside, outside, over midnight, null.
Accept: uv run python tests/test_schedule.py; flutter analyze && flutter test.
