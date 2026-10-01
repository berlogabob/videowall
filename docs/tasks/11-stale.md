# 11 Wall-off state (openlabtwin, apps/office)
Goal: when wall_status.seen_at is older than 60 s the Wall screen shows one grey line "Wall off or server down since HH:MM · last N/M screens on" instead of the red status line; grid squares grey with tooltip "last seen HH:MM"; all controls stay enabled.
Files: lib/logic.dart (new `wallStaleLine(Map? status, DateTime now) -> String?`, null when fresh), lib/wall_screen.dart (use it above the grid).
Test: test/logic_test.dart: fresh -> null; 61 s old -> text with HH:MM and "10/10"; null status -> "Wall server has not reported yet".
Accept: `cd apps/office && flutter analyze && flutter test`.
Do not touch: supabase/, other screens.
