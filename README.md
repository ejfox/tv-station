# tv-station

A personal cable channel: every visitor sees the same YouTube video at the same second.

You feed in a list of YouTube URLs (Watch Later export, Obsidian/Notion vault, plain CSV, whatever). A small Deno app on your VPS computes "what should be playing right now?" deterministically from a fixed epoch and the sum of video durations. Browsers fetch `/now`, seek the YouTube IFrame Player to that offset, and re-sync once a minute against the server clock. No database. No per-client state. Just a public access channel for your taste.

Running version: <https://tv.tools.ejfox.com>

---

## How it works

```
        ┌──── playlist.json ────┐
        │  475 alive videos     │
        │  224h total runtime   │
        └──────────┬────────────┘
                   │
            ┌──────▼────────┐
            │ main.ts       │   (Deno, ~140 lines)
            │ (now - epoch) │
            │   % total     │   ← deterministic playhead
            └──────┬────────┘
                   │
        ┌──────────▼──────────────┐
        │  GET /        →  HTML   │   IFrame Player + auto-sync
        │  GET /now     →  JSON   │   { video, offset, idx }
        │  GET /playlist.json     │   public list
        └─────────────────────────┘
```

Every client lands on the same frame because the playhead is a pure function of `Date.now()`. There's no shared websocket or "TV server" maintaining state. If the smallweb process restarts at 3am, viewers don't notice.

---

## Prereqs

**On your laptop:**
- Python 3.10+
- `yt-dlp` (`brew install yt-dlp` or `pip install yt-dlp`)
- `ssh` access to your VPS (key auth recommended)

**On your VPS (Debian/Ubuntu assumed):**
- [smallweb](https://www.smallweb.run) installed and running
- Caddy (or any reverse proxy) handling TLS + subdomain routing to smallweb

If you already host other smallweb apps at `*.tools.example.com` you're done. If not, follow the smallweb install guide once and you can spin up infinite tiny apps after.

---

## Recipe

### 1. Collect URLs from any/all sources

You probably already have a corpus you forgot about. Two easy ones:

**Watch Later export.** YouTube's Watch Later isn't exposed via the public Data API. The cheap way: open `https://www.youtube.com/playlist?list=WL`, scroll to load everything, and save the HTML. Then grep:

```bash
mkdir sources
grep -oE 'href="/watch\?v=[a-zA-Z0-9_-]{11}' WatchLater.html \
  | sort -u | sed 's|href="/watch?v=|https://youtu.be/|' > sources/watchlater.txt
```

Alternatively use Google Takeout → YouTube → Playlists, which gives you a CSV with one URL per row.

**Obsidian / Notion / Logseq vault.** Just point the script at the folder:

```bash
# happens during step 2 — no extraction needed up front
```

**A bare CSV.** Any CSV with a `url` column works. Headers are sniffed, falling back to "scan every cell for YT links."

### 2. Build the master playlist

```bash
python scripts/build_playlist.py \
  --watch-later sources/watchlater.txt \
  --csv sources/your-other-list.csv \
  --vault ~/Documents/MyObsidianVault \
  --out playlist.json
```

You'll get a `playlist.json` like:

```json
[
  {
    "id": "dQw4w9WgXcQ",
    "title": "",
    "url": "https://youtu.be/dQw4w9WgXcQ",
    "sources": [
      { "kind": "watchlater", "ref": "watchlater.txt" },
      { "kind": "vault", "ref": "blog/2016/video-mixes.md" }
    ]
  }
]
```

### 3. Enrich politely

This is the load-bearing step. We need titles, durations, and a liveness check for each video. We use `yt-dlp` with a randomized 1.0–2.5 sec delay between requests — not a hammer.

```bash
python scripts/enrich_playlist.py --in playlist.json
```

Expect ~1.5 sec per video. 500 videos ≈ 12–15 minutes. Resumable — re-running only touches videos missing `duration`.

After enrichment each record looks like:

```json
{
  "id": "dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up",
  "url": "https://youtu.be/dQw4w9WgXcQ",
  "duration": 213,
  "channel": "Rick Astley",
  "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
  "age_limit": 0,
  "is_live": false,
  "alive": true,
  "sources": [...]
}
```

Dead/blocked entries get `"alive": false` and a `"dead_reason"` string (private, removed, age-restricted, region-locked, copyright strike, etc.). They stay in the JSON so you can see what you lost — the runtime filters them out.

In a typical Watch Later from a few years back, expect **~5–7% to be dead**.

### 4. Ship it

```bash
# pick your VPS host alias
VPS=myvps
APP=tv  # → tv.example.com if your reverse proxy maps *.example.com → smallweb

ssh $VPS "mkdir -p /data2/smallweb/data/$APP"
scp server/main.ts $VPS:/data2/smallweb/data/$APP/
scp playlist.json  $VPS:/data2/smallweb/data/$APP/
```

That's it. smallweb auto-restarts the app on file change. Hit `https://$APP.example.com` and you should see your channel start playing immediately.

### 5. Verify

```bash
curl -s https://$APP.example.com/now | jq '.video.title, .offset, .idx'
```

If you get a video title back, you're live.

---

## Customization

**Change the epoch.** Edit `EPOCH` in `server/main.ts` (default `2026-05-18T00:00:00Z`). The playhead is `(now - epoch) mod total_runtime`, so changing the epoch shifts the entire schedule.

**Themed sub-channels.** Add a Hono route that filters the playlist by `channel_id`, `sources[].ref`, or your own tags:

```ts
app.get("/cooking", c => {
  // filtered nowPlaying using a subset of PLAYLIST
});
```

**Skip on un-embeddable.** Already handled — the IFrame Player's `onError` triggers a `syncToNow()` which advances to whatever the server says is current. (The server isn't waiting for any client — the dead video just stays in the schedule for its duration, then naturally moves on.)

**Different epoch per viewer (private "rerun" mode).** Replace `EPOCH` with a cookie value. Now everyone has their own playhead that began the moment they first visited.

---

## Watching it on an actual TV

There's no real browser on Apple TV / Roku / Fire TV / Chromecast, so the cleanest "permanent channel on the wall" setup is **a cheap headless box → HDMI → TV, running Chromium in kiosk mode**. ~30 minutes once, then it's a dumb appliance.

### Hardware

Anything with HDMI out and Chromium/Chrome:
- **Raspberry Pi 5** (~$80) — the canonical choice. Pi 4 works too, slightly less smooth.
- **Mac mini** you already own — total overkill, but if it's sitting around, plug it in.
- **A used Intel NUC** off eBay — silent, more headroom, $50-ish.

### Pi (Raspberry Pi OS Lite + chromium-browser)

Install Chromium, openbox, unclutter, and set autostart:

```bash
sudo apt update && sudo apt install -y \
  --no-install-recommends \
  xserver-xorg x11-xserver-utils xinit openbox chromium-browser unclutter
```

`~/.config/openbox/autostart`:

```bash
# disable screen blanking / DPMS
xset s off
xset -dpms
xset s noblank

# hide cursor after 0.1s idle
unclutter -idle 0.1 -root &

# launch the channel
chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-translate \
  --check-for-update-interval=31536000 \
  --autoplay-policy=no-user-gesture-required \
  --app=https://tv.tools.ejfox.com
```

Start X on boot. In `~/.bash_profile`:

```bash
[[ -z $DISPLAY && $XDG_VTNR -eq 1 ]] && startx
```

Enable auto-login (`sudo raspi-config` → System Options → Boot/Auto Login → Console Autologin), reboot, you're live.

**Audio out the HDMI**: `sudo raspi-config` → Advanced Options → Audio → HDMI. Verify with `speaker-test -c 2`.

### Mac mini (macOS)

LaunchAgent at `~/Library/LaunchAgents/com.user.tv-kiosk.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.user.tv-kiosk</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Applications/Google Chrome.app/Contents/MacOS/Google Chrome</string>
    <string>--kiosk</string>
    <string>--autoplay-policy=no-user-gesture-required</string>
    <string>--app=https://tv.tools.ejfox.com</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.user.tv-kiosk.plist
```

Then **System Settings → Lock Screen → set everything to "Never"** so the mini doesn't snooze the TV.

### Power button trick

Wire a smart plug (Kasa, Hue, etc.) to the Pi/Mac. Now "turn on the TV channel" is a single button or voice command — the box boots, X comes up, kiosk launches, and within ~25 seconds you're back in the loop where everyone else is. The deterministic playhead means you don't miss a beat.

### Apple TV fallback

If you don't want a dedicated box, you can mirror from any Apple device: Safari → `tv.tools.ejfox.com` → AirPlay → your Apple TV (mirror). Works in 10 seconds. Less reliable for always-on because it ties up the source device.

---

## Caveats

- **Age-gated videos won't play** in an unauthenticated iframe. They get marked dead during enrichment.
- **Mobile autoplay requires mute.** The default already passes `mute=1`. Viewers click to unmute.
- **Region locks aren't visible from your VPS's perspective.** A video that works for your VPS might not work for a viewer in another country. The `onError` skip handles it gracefully.
- **YouTube can change.** This depends on the IFrame Player API and `yt-dlp`. Both have been stable for years but aren't promises.
- **Be a good neighbor.** The 1.0–2.5s enrichment delay is on purpose. Don't crank it lower.

---

## File map

```
.
├── README.md
├── scripts/
│   ├── build_playlist.py     # merge CSV + vault sources into playlist.json
│   └── enrich_playlist.py    # politely add title/duration/alive via yt-dlp
├── server/
│   └── main.ts               # the Deno app for smallweb
└── playlist.json             # (gitignored) your private channel data
```

---

## License

MIT. Build your own weird channel.
