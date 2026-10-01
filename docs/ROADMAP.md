# Roadmap

Open work in order. Update in the same commit that finishes or adds an item.

0. **Pis and bench.** Reflash every card (old password lost) and run `scripts/pi-setup.sh`, see [pi-setup.md](pi-setup.md). Done: the script and its test; 6 Pis set up and online, A1–B3 (`wall-a1`…`wall-b3`, all Pi 3B+, HDMI connected, 2026-09-30); `wall-a1` plays a 1280×1024 H.264 tile (software decode, 2 drops in 20 s). `wall-a1`, `wall-b1`, `wall-a2` report `throttled=0x50000` (under-voltage since boot): swap their PSU/cable. The wall router (TL-WR802N) is in Client mode on TechClub, so the switches are on the lab network. Next: pilot on the 2×3 block A1–B3, then the rest of the grid. Bench checks with one Pi 3B+ + one monitor: 1280×1024@60 over 2–3 adapter models, mpv plays a 1280×1024 H.264 tile smoothly, PSU throttling check. Pick one adapter, buy the same for all. Settle Pi 3 video memory / hardware decode here and add it to the script.
1. **Software (built 2026-10-01, see [PLAN.md](PLAN.md)).** Server, Pi client, Mosaic and Videowall (stills and video), schedule rules, composition, bezel, LAN page, Supabase link. Tested end to end on A1–B3 through SSH tunnels (2026-10-01): identify, test grid, Mosaic, Videowall still and video. Videowall video (39.4 s PROTO26 clip, 25 tiles rendered in 113 s): drift -9 to -42 ms on a1, b1, a2, a3 over 60 s, 0 dropped frames; b2/b3 dropped out of the SSH tunnel chain, not a client fault. b1 reported `throttled=0x80000` (soft temperature limit since boot). Port 8080 open on the node (ufw, 2026-10-01); all 6 Pis connect directly: drift -27 to +29 ms, clock offset under 5 ms, 0 dropped frames while playing the videowall video. Under load a1, b1, a2 report `throttled=0x80000` (soft temperature limit reached) and b2, b3 `0x50000` (under-voltage and throttling): check cooling and the USB charger before 25 Pis. Open: measure drift on 25 screens; test a portrait phone photo (EXIF rotation); put the logo and 3–4 lab photos in `server/assets/` (test-mode defaults, `logo.png` for the logo option and the stopped screen).
2. **openlabtwin link.** Migration `wall_slides` / `wall_state` / `wall_status` + pgTAP, office Wall screen (branch `wall` in openlabtwin). Open: apply the migration (`scripts/sqltest.py`) and merge, which deploys the office.
3. **Pis 19 more.** Flash `wall-c1`…`wall-e5` (hostname only, no Wi-Fi), sudo step, `scripts/pi-setup.sh`, second switch, then `scripts/wall.sh start`.
4. **Physical build.** Print bracket + coil, fix PSU (a1, b1, a2 showed under-voltage), measure bezels for `--bezel-x/-y`, then 6×6.
Later: bezel compensation in Videowall mode, playlists and schedule, event takeover like the TV, systemd once stable.

## Open questions

- Wall server host: the edge node (192.168.1.131, already has nginx, Samba, FFmpeg) if its CPU copes with tile renders, else an old laptop. Same LAN as the wall?
- Repo name / public or private.
