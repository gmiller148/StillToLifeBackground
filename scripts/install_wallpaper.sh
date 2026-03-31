#!/bin/bash
# Install a .mov video as a native macOS wallpaper.
#
# Usage:
#   ./scripts/install_wallpaper.sh <video.mov> [display_name]
#
# Examples:
#   ./scripts/install_wallpaper.sh output_videos/yellowstone_final.mov
#   ./scripts/install_wallpaper.sh output_videos/yellowstone_final.mov "Grand Canyon of the Yellowstone"
#
# What it does:
#   1. Copies the .mov to the macOS aerials directory
#   2. Generates a thumbnail from the first frame
#   3. Registers it in the wallpaper manifest (entries.json)
#   4. Saves custom entries separately so a watchdog can re-inject them
#      (macOS overwrites entries.json from Apple's CDN every ~10 days)
#   5. Installs a launchd watchdog agent (one-time) to auto-restore entries
#   6. Restarts WallpaperAgent so it appears immediately
#
# After running, go to System Settings > Wallpaper and look for the
# "Custom" category at the bottom.
#
# Requirements:
#   - macOS Sonoma (14) or later
#   - ffmpeg (brew install ffmpeg)
#   - Input must be a .mov file (HEVC recommended)

set -euo pipefail

INPUT="${1:?Usage: $0 <video.mov> [display_name]}"
DISPLAY_NAME="${2:-$(basename "${INPUT%.*}")}"

if [[ ! -f "$INPUT" ]]; then
    echo "Error: File not found: $INPUT" >&2
    exit 1
fi

if [[ "${INPUT##*.}" != "mov" ]]; then
    echo "Error: Input must be a .mov file. Convert with:" >&2
    echo "  ffmpeg -i input.mp4 -c:v hevc_videotoolbox -b:v 15M -tag:v hvc1 -an output.mov" >&2
    exit 1
fi

if ! command -v ffmpeg &>/dev/null; then
    echo "Error: ffmpeg not found. Install with: brew install ffmpeg" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AERIALS_DIR="$HOME/Library/Application Support/com.apple.wallpaper/aerials"
MANIFEST="$AERIALS_DIR/manifest/entries.json"
CONFIG_DIR="$HOME/.config/custom-wallpapers"
CUSTOM_ENTRIES="$CONFIG_DIR/custom_entries.json"
WATCHDOG_SCRIPT="$CONFIG_DIR/wallpaper_watchdog.py"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/com.stilltolife.wallpaper-watchdog.plist"

if [[ ! -f "$MANIFEST" ]]; then
    echo "Error: Wallpaper manifest not found at $MANIFEST" >&2
    echo "This script requires macOS Sonoma (14) or later." >&2
    exit 1
fi

UUID=$(uuidgen)
CUSTOM_CAT_ID="CUSTOM-STILL-TO-LIFE-00000000"
CUSTOM_SUB_ID="CUSTOM-STILL-TO-LIFE-SUB-0000"

echo "=== Installing wallpaper ==="
echo "  Name: $DISPLAY_NAME"
echo "  UUID: $UUID"

# Copy video
mkdir -p "$AERIALS_DIR/videos" "$AERIALS_DIR/thumbnails"
cp "$INPUT" "$AERIALS_DIR/videos/$UUID.mov"
echo "  Copied video"

# Generate thumbnail
ffmpeg -y -i "$INPUT" \
    -vf "select=eq(n\,0),scale=640:-1" \
    -vframes 1 -update 1 -q:v 2 \
    "$AERIALS_DIR/thumbnails/$UUID.jpg" 2>/dev/null
echo "  Generated thumbnail"

# Build asset and category entries, save to custom_entries.json, and merge into manifest
mkdir -p "$CONFIG_DIR"

python3 << PYEOF
import json, os

manifest_path = "$MANIFEST"
custom_path = "$CUSTOM_ENTRIES"
uuid = "$UUID"
display_name = "$DISPLAY_NAME"
cat_id = "$CUSTOM_CAT_ID"
sub_id = "$CUSTOM_SUB_ID"
videos_dir = os.path.expanduser("~/Library/Application Support/com.apple.wallpaper/aerials/videos")

# Load or create custom entries store
if os.path.exists(custom_path):
    with open(custom_path) as f:
        custom = json.load(f)
else:
    custom = {"assets": [], "categories": []}

# Build the new asset
new_asset = {
    "id": uuid,
    "accessibilityLabel": display_name,
    "categories": [cat_id],
    "subcategories": [sub_id],
    "includeInShuffle": True,
    "localizedNameKey": display_name,
    "pointsOfInterest": {},
    "preferredOrder": 0,
    "previewImage": "",
    "shotID": "CUSTOM_" + uuid[:8],
    "showInTopLevel": True,
    "url-4K-SDR-240FPS": "file://" + os.path.join(videos_dir, uuid + ".mov")
}

# Ensure custom category exists in our store
custom_cat_ids = [c["id"] for c in custom["categories"]]
if cat_id not in custom_cat_ids:
    custom["categories"].append({
        "id": cat_id,
        "localizedNameKey": "Custom",
        "localizedDescriptionKey": "Custom wallpapers",
        "preferredOrder": 99,
        "previewImage": "",
        "representativeAssetID": uuid,
        "subcategories": [{
            "id": sub_id,
            "localizedNameKey": "StillToLife",
            "localizedDescriptionKey": "Custom parallax wallpapers",
            "preferredOrder": 0,
            "previewImage": "",
            "representativeAssetID": uuid
        }]
    })

# Add asset to our store
custom_asset_ids = [a["id"] for a in custom["assets"]]
if uuid not in custom_asset_ids:
    custom["assets"].append(new_asset)

# Save custom entries (this is the durable store the watchdog reads)
with open(custom_path, "w") as f:
    json.dump(custom, f, indent=2)

# Now merge into the live manifest
with open(manifest_path) as f:
    manifest = json.load(f)

manifest_asset_ids = {a["id"] for a in manifest["assets"]}
manifest_cat_ids = {c["id"] for c in manifest["categories"]}

for asset in custom["assets"]:
    if asset["id"] not in manifest_asset_ids:
        manifest["assets"].append(asset)

for cat in custom["categories"]:
    if cat["id"] not in manifest_cat_ids:
        manifest["categories"].append(cat)

with open(manifest_path, "w") as f:
    json.dump(manifest, f, indent=2)

print(f"  Registered in manifest ({len(manifest['assets'])} total assets)")
print(f"  Saved {len(custom['assets'])} custom entries to {custom_path}")
PYEOF

# Install watchdog script
cp "$SCRIPT_DIR/wallpaper_watchdog.py" "$WATCHDOG_SCRIPT"
chmod +x "$WATCHDOG_SCRIPT"
echo "  Installed watchdog script"

# Install launchd agent (if not already present)
if [[ ! -f "$LAUNCH_AGENT" ]]; then
    mkdir -p "$(dirname "$LAUNCH_AGENT")"
    cat > "$LAUNCH_AGENT" << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.stilltolife.wallpaper-watchdog</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>${WATCHDOG_SCRIPT}</string>
    </array>
    <key>WatchPaths</key>
    <array>
        <string>${AERIALS_DIR}/manifest/entries.json</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>5</integer>
    <key>StandardOutPath</key>
    <string>${CONFIG_DIR}/watchdog.log</string>
    <key>StandardErrorPath</key>
    <string>${CONFIG_DIR}/watchdog.log</string>
</dict>
</plist>
PLISTEOF

    launchctl load "$LAUNCH_AGENT" 2>/dev/null || true
    echo "  Installed wallpaper watchdog (auto-restores entries after macOS resets)"
else
    echo "  Watchdog already installed"
fi

# Restart wallpaper service
killall WallpaperAgent 2>/dev/null || true
killall WallpaperAerialsExtension 2>/dev/null || true
echo "  Restarted WallpaperAgent"

echo ""
echo "=== Done! ==="
echo "  Open System Settings > Wallpaper"
echo "  Look for the \"Custom\" category"
echo "  Select \"$DISPLAY_NAME\""
