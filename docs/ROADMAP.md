# Roadmap

Open work in order. Update in the same commit that finishes or adds an item.

0. **Pis and bench.** Reflash every card (old password lost) and run `scripts/pi-setup.sh`, see [pi-setup.md](pi-setup.md). Done: the script and its test; not yet run on a real Pi. Next: one pilot card on the bench monitor, then the other 14. Bench checks with one Pi 3B+ + one monitor: 1280×1024@60 over 2–3 adapter models, mpv plays a 1280×1024 H.264 tile smoothly, PSU throttling check. Pick one adapter, buy the same for all. Settle Pi 3 video memory / hardware decode here and add it to the script.
1. **Mosaic, stills.** Pool folder (Samba share on the node, like `smb://…/tv`), each Pi cycles its images, test-mode defaults, Identify Screen, test pattern. 5×3.
2. **Videowall, stills.** FFmpeg canvas + slice, distribute, synced image change.
3. **Video.** Tile render, preload, `play_at`, chrony. Measure drift across 15 screens.
4. **Composition.** Fit/Fill/Center, logo, title, credits, matte; small preview with grid overlay.
5. **openlabtwin link.** `wall_state` / `wall_status` tables, office screen (mode, play/stop, blackout, status), docs in openlabtwin.
6. **Physical build.** Print bracket + coil, fix PSU, scale to 5×5 (second switch), then 6×6.
Later: bezel compensation in Videowall mode, playlists and schedule, event takeover like the TV, systemd once stable.

## Open questions

- Wall server host: the edge node (192.168.1.131, already has nginx, Samba, FFmpeg) if its CPU copes with tile renders, else an old laptop. Same LAN as the wall?
- Repo name / public or private.
