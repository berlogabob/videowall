# Setting up the wall Pis

Every Pi gets a fresh Raspberry Pi OS; nothing is recovered from the old cards (their password is lost and their state unknown). A card is flashed on the Mac, then `scripts/pi-setup.sh` finishes all Pis at once over SSH. Running the script again is safe, so a broken Pi is rebuilt the same way in about 10 minutes.

## 1. Flash the cards (Mac, Raspberry Pi Imager)

- Device: Raspberry Pi 3 (or the model in hand). OS: **Raspberry Pi OS Lite (64-bit)**, no desktop: mpv draws straight to the screen.
- Edit settings:
  - Hostname `wall-01`, `wall-02`, … numbered like the wall: top-left is 01, left to right, then the next row down.
  - Username `techlab`, any password (write it in the lab password store; logins use the key).
  - Services: SSH on, **public-key only**, key = output of `cat ~/.ssh/techlab.pub`.
  - Time zone Europe/Lisbon. Wi-Fi empty (wired only).
- Imager keeps these settings; for each next card change only the hostname.
- Sticker with the number on the Pi and on the card.

Optional, before ejecting: `scripts/pi-setup.sh --boot /Volumes/bootfs` writes the display settings straight onto the card, so the first boot already drives the VGA adapter at 1280×1024.

## 2. Connect

All Pis on the TP-Link switch, the switch on the lab network, the Mac on the same network (or go through the node, see below). After about a minute each Pi answers as `wall-NN.local`:

```sh
for n in $(seq -w 1 15); do ping -c1 -t2 wall-$n.local >/dev/null && echo "wall-$n up" || echo "wall-$n MISSING"; done
```

Later, give each Pi a fixed address (DHCP reservation) in the router, by the MAC it shows there.

## 3. Run the setup

From the repo on the Mac:

```sh
scripts/pi-setup.sh wall-{01..15}.local
```

It runs on all Pis in parallel, writes `logs/<host>.log` for each and prints one line per Pi:

```
wall-01.local            ok wall-01 throttled=0x0 REBOOT NEEDED
```

Then reboot the ones that ask: `ssh -i ~/.ssh/techlab techlab@wall-01.local sudo reboot`.

On one Pi without the Mac: copy the script over and run `sudo bash pi-setup.sh`.

From outside the lab (Tailscale), jump through the node: add to `~/.ssh/config`

```
Host wall-*.local
  IdentityFile ~/.ssh/techlab
  ProxyJump TechLAB@techlab-01
```

This needs the node to resolve `.local` names (avahi); if it doesn't, use the Pis' IP addresses.

## What the script does

| Part | Why |
|---|---|
| `mpv`, `chrony`, `curl`, then `uv` for the `techlab` user | player; tight clocks for synced starts (`play_at`); the Python client runs with `uv run` |
| Time zone Europe/Lisbon | same clock as the TV and node |
| `cmdline.txt`: `video=HDMI-A-1:1280x1024@60D` | forces the HDMI output on at the Samsung 720N's native mode; cheap HDMI→VGA adapters often report no screen |
| `cmdline.txt`: `consoleblank=0 vt.global_cursor_default=0` | screen never blanks, no blinking cursor |
| `config.txt`: `hdmi_force_hotplug=1 disable_overscan=1` | output on even with no screen detected, no black border |
| `config.txt`: `dtoverlay=disable-wifi`, `dtoverlay=disable-bt`; Bluetooth services off | wired only, fewer things running |
| Report: model, memory, HDMI status, `vcgencmd get_throttled` | `throttled=0x0` is good; anything else (e.g. `0x50005`) means undervoltage, usually the shared USB charger (5 V / 2 A per port, the Pi 3B+ wants 2.5 A) |

Knobs: `MODE=1920x1080@60` for another monitor, `WALL_USER=pi` for another user name, both as environment variables on the Mac.

Test (no Pi needed): `tests/test_pi_setup.sh` checks the boot-file edits on a fake card.

## Not done yet (after the bench test)

- Video memory / hardware decode tuning for the Pi 3 (settle on the bench with a real 1280×1024 H.264 tile).
- Client start at boot: manual `uv run` for now, systemd later.
