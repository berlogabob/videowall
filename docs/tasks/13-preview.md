# 13 Preview in the office (videowall server + openlabtwin)
Goal: the office shows the wall's current picture.
Server: server/db.py `storage_put(db, bucket, path, data, content_type)`: POST {SUPABASE_URL}/storage/v1/object/{bucket}/{path}, header x-upsert: true. server/render.py `mosaic_preview(tiles: dict code->path, cols, rows, out)`: xstack, 640 px wide, drawgrid borders. server/app.py: when the shown item changes, upload its preview.jpg (videowall) or mosaic_preview (mosaic) to bucket wall-preview as current.jpg; set wall_status.preview_at.
DB: append to 20261002100000_wall_panel.sql: private bucket wall-preview, staff select via is_staff() on storage.objects (copy 20260926110000_storage_quality.sql); `alter table wall_status add column preview_at timestamptz`.
Office: data.dart `wallPreviewUrl()` = createSignedUrl('current.jpg', 60); wall_screen.dart shows it at the top, reloaded when preview_at changes.
Tests: tests/test_db.py storage_put request shape; tests/test_render.py mosaic_preview 2x2 -> 640 px wide.
Accept: uv run python tests/test_db.py && uv run python tests/test_render.py; flutter analyze && flutter test.
