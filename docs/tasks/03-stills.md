# Task 03: Mosaic and Videowall stills

Read `docs/tasks/00-rules.md`, then `docs/PLAN.md` "Storage" (server cache, keys, eviction), "Render ahead" (canvas/crop formulas, mosaic), D1/D2/D8/D10. Needs tasks 01-02.

- `render.py`: folder scan of `--media` (flat, skip dot files; photos jpg/jpeg/png/webp/heic?, videos later) with an ffprobe cache in `<cache>/probe.json` keyed by name+size+mtime. EXIF orientation: honour it (test a portrait phone photo; ffmpeg autorotate handles most; copy `exif_orientation` from openlabtwin `scripts/tv.py` only if needed).
- Mosaic still: normalise one file to 1280x1024 with fit (scale down + pad black) / fill (scale up + crop) / center (no scale, pad or crop). Key per file+fit.
- Videowall still: canvas `W = C*1280 + (C-1)*gx`, `H = R*1024 + (R-1)*gy`, fit/fill/center into the canvas, then one ffmpeg run with `split=N` + N crops at `x = c*(1280+gx)`, `y = r*(1024+gy)` -> `<key>/<code>.jpg`. Key = sha256(name,size,mtime,mode,fit,cols,rows,gx,gy,RENDER_VERSION)[:16].
- Cache: `meta.json` per key with bytes and last_used; LRU eviction over `--cache-gb`, never evicting pinned keys (current `now`, defaults, identify/test). Disk check before render.
- One render worker thread, `nice` where available, jobs in a queue; progress per job in `/api/status`.
- "Show now" (precedence level 4, D10): `POST /api/now {mode, media_names, fit, seconds?}` and `DELETE /api/now` (back to defaults); mosaic with several files cycles every `cycle_seconds` (default 10) with screen offset; persisted in `state.json`.
- page.html: file list (name, kind, size) with mode + fit selectors and "Show now" button; render progress; disk free and cache size.

Tests (extend `tests/test_render.py`): key changes with fit/grid but not per tile; eviction keeps pinned; fit/fill/center filter strings; ffmpeg smoke: 2x2 videowall from a lavfi still gives 4 tiles whose seam pixels match the source canvas.

Docs: README modes section, ROADMAP.

Done when: tests pass; on the node with 6 Pis a photo from `~/tv-media` shows as one picture across the 2x3 block, and a Mosaic of all photos cycles.
