# Setting up the wall Pis

Every Pi gets a fresh Raspberry Pi OS; nothing is recovered from the old cards (their password is lost and their state unknown). A card is flashed on the Mac, then `scripts/pi-setup.sh` finishes all Pis at once over SSH. Running the script again is safe, so a broken Pi is rebuilt the same way in about 10 minutes.

## 1. Flash the cards (Mac, Raspberry Pi Imager)

- Device: Raspberry Pi 3 (or the model in hand). OS: **Raspberry Pi OS Lite (64-bit)**, no desktop: mpv draws straight to the screen.
- Edit settings:
  - Hostname `wall-` + the screen's grid code in lower case: letter = column, number = row, top-left is `wall-a1`, the one to its right `wall-b1`, the row below starts `wall-a2`; a 5×5 grid ends at `wall-e5`.
  - Username `techlab`, any password (write it in the lab password store; logins use the key).
  - Services: SSH on, **public-key only**, key = output of `cat ~/.ssh/techlab.pub`.
  - Time zone Europe/Lisbon. No Wi-Fi: wall Pis are cable only (the script switches Wi-Fi off anyway).
- Imager keeps these settings; for each next card change only the hostname.
- Sticker with the code (A1, B1, …) on the Pi and on the card.

Optional, before ejecting: `scripts/pi-setup.sh --boot /Volumes/bootfs` writes the display settings straight onto the card, so the first boot already drives the VGA adapter at 1280×1024.

## 2. Connect

All Pis on the TP-Link switch, the switch on the lab network, the Mac on the same network (or go through the node, see below). After about a minute each Pi answers as `wall-XX.local`:

```sh
for n in a1 b1; do ping -c1 -t2 wall-$n.local >/dev/null && echo "wall-$n up" || echo "wall-$n MISSING"; done   # 5×3: wall-{a..e}{1..3}
```

Later, give each Pi a fixed address (DHCP reservation) in the router, by the MAC it shows there.

## 3. Run the setup

Once per Pi, let `techlab` use sudo without a password (the Imager user needs one, and the parallel run can't type it). It asks for the Imager password:

```sh
ssh -t -i ~/.ssh/techlab techlab@wall-a1.local 'echo "techlab ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/010-techlab && sudo chmod 440 /etc/sudoers.d/010-techlab'
```

Then, from the repo on the Mac:

```sh
scripts/pi-setup.sh wall-a1.local wall-b1.local   # 5×3: wall-{a..e}{1..3}.local
```

It runs on all Pis in parallel, writes `logs/<host>.log` for each and prints one line per Pi:

```
wall-a1.local            ok wall-a1 throttled=0x0 REBOOT NEEDED
```

Then reboot the ones that ask: `ssh -i ~/.ssh/techlab techlab@wall-a1.local sudo reboot`.

On one Pi without the Mac: copy the script over and run `sudo bash pi-setup.sh`.

From outside the lab (Tailscale), jump through the node: add to `~/.ssh/config`

```
Host techlab-01
  User TechLAB
  IdentityFile ~/.ssh/techlab

Host wall-*.local
  User techlab
  IdentityFile ~/.ssh/techlab
  ProxyJump techlab-01
```

The `techlab-01` block matters: without it the jump offers the wrong key, and a burst of failed logins gets the Mac's Tailscale IP banned by the node for a while (seen 2026-09-30).

The node resolves `.local` names (avahi, checked 2026-09-25), so `wall-XX.local` works through it. From home the link goes through Tailscale's relay (about 40 ms): fine for setup, slow for copying video. SSH to `techlab-01` by name needs its `known_hosts` line, see openlabtwin `docs/edge-node.md` → Tailscale.

## What the script does

| Part | Why |
|---|---|
| `mpv`, `chrony`, `curl`, then `uv` for the `techlab` user | player; tight clocks for synced starts (`play_at`); the Python client runs with `uv run` |
| Time zone Europe/Lisbon | same clock as the TV and node |
| `cmdline.txt`: `video=HDMI-A-1:1280x1024@60D` | forces the HDMI output on at the Samsung 720N's native mode; cheap HDMI→VGA adapters often report no screen |
| `cmdline.txt`: `consoleblank=0 vt.global_cursor_default=0` | screen never blanks, no blinking cursor |
| `config.txt`: `hdmi_force_hotplug=1 disable_overscan=1` | output on even with no screen detected, no black border |
| `config.txt`: `dtoverlay=disable-bt`, `dtoverlay=disable-wifi`; Bluetooth services off | cable only: a Pi with Wi-Fi too has two addresses, `wall-XX.local` flips between them and SSH times out (seen on a3/b3, 2026-09-30). The wall router in Client mode is the uplink; if it drops, plug into the wall switch |
| `@reboot` cron line for `techlab`: fetch `wall.py` from the server, start it | a screen comes back by itself after a power dip or reboot (cron, not systemd); `WALL_SERVER=host:port` to point it elsewhere |
| Report: model, memory, HDMI status, `vcgencmd get_throttled` | `throttled=0x0` is good; anything else (e.g. `0x50005`) means undervoltage, usually the shared USB charger (5 V / 2 A per port, the Pi 3B+ wants 2.5 A) |

Knobs: `MODE=1920x1080@60` for another monitor, `WALL_USER=pi` for another user name, both as environment variables on the Mac.

Test (no Pi needed): `tests/test_pi_setup.sh` checks the boot-file edits on a fake card.

## Bench test tile

A 60-second 1280×1024 H.264 test video and a still, made on the Mac:

```sh
ffmpeg -f lavfi -i testsrc2=size=1280x1024:rate=30 -t 60 -c:v libx264 -profile:v high -level 4.0 -pix_fmt yuv420p -g 60 tile-1280x1024.mp4
ffmpeg -f lavfi -i testsrc2=size=1280x1024 -frames:v 1 pattern-1280x1024.png
```

Copy to the Pi and play: `scp tile-1280x1024.mp4 techlab@wall-a1.local:` then `ssh techlab@wall-a1.local mpv --fs --loop tile-1280x1024.mp4`. Watch for dropped frames (`mpv` prints them).

Measured on `wall-a1` (Pi 3B+, 2026-09-30), 20 s of the 30 fps tile: software decode (mpv default) dropped 2 frames; `--hwdec=v4l2m2m-copy` dropped 155. Keep software decode.

## Not done yet (after the bench test)

- Video memory tuning, if longer or 60 fps tiles drop frames.
- Client start at boot: manual `uv run` for now, systemd later.

## Running the client

From the Mac: `scripts/wall.sh start` (all 25, one after another), or with codes: `scripts/wall.sh start a1 b1`. It downloads `wall.py` from the server (`http://192.168.1.131:8080/wall.py`) and starts it detached with `uv run --script`; the log is `~/wall.log`, tiles are cached in `~/wall-cache/` (the client keeps 2 GB of the SD card free). `scripts/wall.sh status` and `stop` do what they say. Another server: `SERVER=ws://host:8080/ws scripts/wall.sh start`.
