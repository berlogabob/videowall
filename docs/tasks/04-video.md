# Task 04: Video (Mosaic and Videowall) with synced start

Read `docs/tasks/00-rules.md`, then `docs/PLAN.md` "Storage" (video tile format), "Protocol" (client switching/drift), "Render ahead", D9. Builds on tasks 01-03.

- `render.py`: video in the media scan (mp4/mov/mkv/webm, ffprobe duration/fps). Mosaic video: one normalised 1280x1024 tile per file+fit. Videowall video: one ffmpeg run: decode -> canvas (fit/fill/center) -> `split=N` -> N crops -> N libx264 outputs with identical settings: `-preset veryfast -profile:v high -level 4.0 -r 30 -g 30 -keyint_min 30 -sc_threshold 0 -b:v 4M -maxrate 5M -bufsize 8M -pix_fmt yuv420p -an -movflags +faststart`. Poster first (D9): JPEG tiles of the first frame under `<key>/poster-<code>.jpg`, rendered before the video; while the video renders the poster is shown. Progress % from ffmpeg `-progress pipe:1` out_time vs duration.
- Server: plan items for video carry `period` = tile duration; `at` = anchor (now + 3 s after all online screens report `ready`, timeout 60 s then start without the missing ones). Rejoining Pi gets the same `at` (client seeks by itself).
- Server measures clock offset per Pi; `/api/status` shows `drift_ms` and `clock_ms`; page shows amber when |clock_ms| > 50.
- Client (task 01 code) already has drift logic; fix whatever the end-to-end run shows.

Tests: `tests/test_render.py` add: video command has identical encoder args for every output; ffmpeg smoke 2x2 from `lavfi testsrc2` 2 s gives 4 mp4 of 1280x1024, 30 fps, same frame count. `tests/test_client.py`: expected position across several loops.

Docs: README (video), ROADMAP, PLAN risks if a measured value changes (render speed: log seconds per wall-minute on this machine).

Done when: tests pass; local run with 2 fake clients (`--mpv-args=--vo=null`) plays a 2x2 videowall video and both report |drift_ms| < 100 after 20 s.
