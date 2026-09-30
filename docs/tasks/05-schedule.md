# Task 05: Schedule (playlist, windows, takeover, announcements, activity link)

Read `docs/tasks/00-rules.md`, then `docs/PLAN.md` "Precedence" (all 8 levels), "Render ahead" (queue order), "Tables" (`wall_slides` row shape), D3-D6, D10.

- `server/schedule.py`: copy `in_window`, `link_events` and the occurrence expansion from openlabtwin `scripts/tv.py` / `scripts/export.py` (read them in `../openlabtwin`; note the source commit sha in a comment). `uv add python-dateutil`. Europe/Lisbon time.
- `resolve(state, slides, activities, t, ready) -> per-screen plan items`: the 8 precedence levels exactly as PLAN. Loop anchor `A` persisted in `state.json` with the live-set hash; a live-set change applies at the next item boundary. Takeover anchored at that day's `from_time`. Announcement when `t % every < seconds` (TV formula; only takeover announcements during a takeover). Not-ready videowall video -> its poster; otherwise skip to next level.
- Standalone source: `<cache>/playlist.json` = list of `wall_slides`-shaped rows (+ optional `activities`); editable through `GET/PUT /api/playlist` and a simple list editor on page.html (add/edit/delete row, all columns).
- Render-ahead queue in PLAN order; `/api/status` gives per-slide state (ready / rendering n% / failed: reason).

Test: `tests/test_schedule.py`: window vectors (copy the relevant cases from openlabtwin `scripts/test_tv.py` or its tests), loop wrap, anchor moves only at boundaries, takeover starts exactly at from_time, announcement formula incl. during takeover, each precedence level beats the next, poster fallback, activity link gives the slide that activity's slot today.

Docs: README (schedule), ROADMAP.

Done when: tests pass.
