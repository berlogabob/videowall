# 12 Presets (openlabtwin)
Goal: playlist rows marked `preset` appear as one-tap buttons under the controls; tap = set wall_state.now to that row (as Show now, now_at = now + 3 s).
DB: new supabase/migrations/20261002100000_wall_panel.sql: `alter table wall_slides add column preset boolean not null default false;` (later tasks append). supabase/tests/database/12_wall.test.sql: preset defaults to false (bump plan()).
Files: lib/logic.dart (WallSlide.preset in fromRow/toRow), lib/wall_screen.dart (preset button row; star toggle in the editor; "Show now" icon per playlist row).
Test: test/logic_test.dart round trip includes preset.
Accept: flutter analyze && flutter test. Claude applies the migration (scripts/sqltest.py).
