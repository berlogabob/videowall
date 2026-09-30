# Task 07: Composition, preview, bezel

Read `docs/tasks/00-rules.md`, then `docs/PLAN.md` "Render ahead" (canvas, crops, bezel), "Tables" (`show_title`, `credits`, `logo`, `matte`).

- Videowall canvas composition in the same ffmpeg graph before `split`: matte (px frame, black, around the picture inside the canvas), title (drawtext, large, bottom third, shadow), credits (drawtext, small, bottom right), logo (overlay of `server/assets/logo.png` top right, skipped if missing). Font from `--font` (default DejaVuSans-Bold on Linux, Arial on Windows, skip text if none). Text must be escaped for drawtext (colons, quotes, percent).
- Bezel: `--bezel-x/--bezel-y` in px (help text: px = bezel mm / 0.264 for the 720N), used in canvas size and crop offsets; also a `bezel_mm` helper in the help.
- Preview: `GET /api/preview/{key}.jpg` = the composed canvas scaled to 640 px wide with `drawgrid` lines at tile borders (bezel gaps shaded); page.html shows it for the selected file/mode/fit and for the current item.
- Mosaic: fit/fill/center only (no title/logo) - keep it simple.

Test: extend `tests/test_render.py`: drawtext escaping, the filter graph contains matte/title/logo only when set, key changes with each composition field, preview dimensions (ffmpeg smoke on 2x2).

Docs: README composition section, ROADMAP.

Done when: tests pass.
