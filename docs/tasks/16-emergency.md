# 16 Emergency message
Goal: the office types a text; every screen shows it across the wall until "Back to schedule".
Server: render.py `wrap(text, width=24)` and `render_text(text, d, grid, font)`: lavfi color=black at canvas size, drawtext from text.txt (white, size H/10, centred), slice_graph -> per-screen jpgs + preview. app.py: a `now` with `text` and no media_names uses it; the render key includes the text.
Office: control "Emergency message…" (multi-line) -> wall_state.now = {mode:'videowall', text, fit:'fit'}, now_until null.
Tests: tests/test_render.py: wrap() cases; render_text 2x2 -> 4 tiles + preview (skip when drawtext missing).
Accept: uv run python tests/test_render.py; flutter analyze && flutter test.
