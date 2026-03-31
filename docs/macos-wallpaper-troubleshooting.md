# macOS Custom Wallpaper Troubleshooting

## How the wallpaper system works

macOS stores video wallpapers here:

```
~/Library/Application Support/com.apple.wallpaper/aerials/
├── manifest/
│   └── entries.json      ← Registry of all wallpapers (Apple's + yours)
├── videos/               ← The .mov files (named by UUID)
└── thumbnails/           ← Preview images for the wallpaper picker
```

Custom wallpapers are added by:
1. Placing a `.mov` in `videos/`
2. Adding a thumbnail to `thumbnails/`
3. Adding an entry to `entries.json`

## The persistence problem

macOS fetches a new `manifest.tar` from Apple's CDN (`sylvan.apple.com`) roughly every 10 days. When it does, it **overwrites `entries.json`** with the official version, wiping custom entries. Your video files are never deleted — only the manifest reference is lost.

The schedule is visible in:
```bash
plutil -p ~/Library/Preferences/com.apple.wallpaper.aerial.plist
```

Look for `scheduledUpdateDate` to see when the next refresh will happen.

## The watchdog solution

The install script sets up a launchd agent that watches `entries.json` and re-injects custom entries when macOS resets them.

**Components:**
- `~/.config/custom-wallpapers/custom_entries.json` — durable store of your custom wallpapers
- `~/.config/custom-wallpapers/wallpaper_watchdog.py` — script that merges entries back
- `~/Library/LaunchAgents/com.stilltolife.wallpaper-watchdog.plist` — launchd agent
- `~/.config/custom-wallpapers/watchdog.log` — log file

## Diagnosing issues

### Wallpaper disappeared from System Settings

Check if your custom entries are still in the manifest:

```bash
python3 -c "
import json
with open('$HOME/Library/Application Support/com.apple.wallpaper/aerials/manifest/entries.json') as f:
    d = json.load(f)
custom = [a for a in d['assets'] if 'CUSTOM' in a.get('shotID','')]
print(f'{len(custom)} custom wallpaper(s) in manifest')
for a in custom:
    print(f'  - {a[\"localizedNameKey\"]} ({a[\"id\"]})')
"
```

If none found, the manifest was overwritten. Check if the watchdog is running:

```bash
launchctl list | grep stilltolife
```

If not running, reload it:

```bash
launchctl load ~/Library/LaunchAgents/com.stilltolife.wallpaper-watchdog.plist
```

Then manually trigger re-injection:

```bash
python3 ~/.config/custom-wallpapers/wallpaper_watchdog.py
```

### Wallpaper shows in picker but won't play / shows black

Check the video file exists:

```bash
ls -lh ~/Library/Application\ Support/com.apple.wallpaper/aerials/videos/ | grep -v "^total"
```

Verify the video is valid:

```bash
ffprobe ~/Library/Application\ Support/com.apple.wallpaper/aerials/videos/YOUR-UUID.mov 2>&1 | head -10
```

### Watchdog isn't working

Check the log:

```bash
cat ~/.config/custom-wallpapers/watchdog.log
```

Verify the custom entries store exists:

```bash
cat ~/.config/custom-wallpapers/custom_entries.json | python3 -m json.tool | head -20
```

## Manually re-installing a wallpaper

If everything is broken, re-run the install script:

```bash
./scripts/install_wallpaper.sh output_videos/your_wallpaper.mov "Display Name"
```

This will re-copy the video, regenerate the thumbnail, re-register in the manifest, and ensure the watchdog is running.

## Undo / complete removal

### Remove a single custom wallpaper

```bash
# 1. Find the UUID
python3 -c "
import json
with open('$HOME/.config/custom-wallpapers/custom_entries.json') as f:
    d = json.load(f)
for a in d['assets']:
    print(f'{a[\"id\"]}  {a[\"localizedNameKey\"]}')
"

# 2. Remove the video and thumbnail (replace UUID below)
UUID="YOUR-UUID-HERE"
rm -f ~/Library/Application\ Support/com.apple.wallpaper/aerials/videos/$UUID.mov
rm -f ~/Library/Application\ Support/com.apple.wallpaper/aerials/thumbnails/$UUID.jpg

# 3. Remove from custom entries store
python3 -c "
import json, os
path = os.path.expanduser('~/.config/custom-wallpapers/custom_entries.json')
with open(path) as f:
    d = json.load(f)
d['assets'] = [a for a in d['assets'] if a['id'] != '$UUID']
with open(path, 'w') as f:
    json.dump(d, f, indent=2)
print(f'Removed. {len(d[\"assets\"])} wallpapers remaining.')
"

# 4. Remove from live manifest
python3 -c "
import json, os
path = os.path.expanduser('~/Library/Application Support/com.apple.wallpaper/aerials/manifest/entries.json')
with open(path) as f:
    d = json.load(f)
d['assets'] = [a for a in d['assets'] if a['id'] != '$UUID']
with open(path, 'w') as f:
    json.dump(d, f, indent=2)
"

# 5. Restart
killall WallpaperAgent 2>/dev/null
```

### Remove everything (full undo)

```bash
# 1. Remove all custom videos and thumbnails
python3 -c "
import json, os
path = os.path.expanduser('~/.config/custom-wallpapers/custom_entries.json')
with open(path) as f:
    d = json.load(f)
for a in d['assets']:
    uuid = a['id']
    for f in [
        os.path.expanduser(f'~/Library/Application Support/com.apple.wallpaper/aerials/videos/{uuid}.mov'),
        os.path.expanduser(f'~/Library/Application Support/com.apple.wallpaper/aerials/thumbnails/{uuid}.jpg'),
    ]:
        if os.path.exists(f):
            os.remove(f)
            print(f'Removed {f}')
"

# 2. Remove custom entries from live manifest
python3 -c "
import json, os
manifest = os.path.expanduser('~/Library/Application Support/com.apple.wallpaper/aerials/manifest/entries.json')
with open(manifest) as f:
    d = json.load(f)
d['assets'] = [a for a in d['assets'] if 'CUSTOM' not in a.get('shotID','')]
d['categories'] = [c for c in d['categories'] if c['id'] != 'CUSTOM-STILL-TO-LIFE-00000000']
with open(manifest, 'w') as f:
    json.dump(d, f, indent=2)
print('Cleaned manifest')
"

# 3. Unload and remove the watchdog
launchctl unload ~/Library/LaunchAgents/com.stilltolife.wallpaper-watchdog.plist 2>/dev/null
rm -f ~/Library/LaunchAgents/com.stilltolife.wallpaper-watchdog.plist

# 4. Remove config directory
rm -rf ~/.config/custom-wallpapers

# 5. Restart
killall WallpaperAgent 2>/dev/null

echo "All custom wallpapers removed. System restored to default."
```

## Key file locations reference

| File | Purpose |
|------|---------|
| `~/Library/Application Support/com.apple.wallpaper/aerials/manifest/entries.json` | Live wallpaper manifest (gets overwritten by macOS) |
| `~/Library/Application Support/com.apple.wallpaper/aerials/videos/` | Video files (safe, never overwritten) |
| `~/Library/Application Support/com.apple.wallpaper/aerials/thumbnails/` | Thumbnails (safe, never overwritten) |
| `~/Library/Preferences/com.apple.wallpaper.aerial.plist` | Manifest refresh schedule |
| `~/.config/custom-wallpapers/custom_entries.json` | Your custom entries (durable store) |
| `~/.config/custom-wallpapers/wallpaper_watchdog.py` | Watchdog script |
| `~/.config/custom-wallpapers/watchdog.log` | Watchdog activity log |
| `~/Library/LaunchAgents/com.stilltolife.wallpaper-watchdog.plist` | launchd agent definition |
