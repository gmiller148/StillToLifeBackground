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
#   4. Restarts WallpaperAgent so it appears immediately
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

AERIALS_DIR="$HOME/Library/Application Support/com.apple.wallpaper/aerials"
MANIFEST="$AERIALS_DIR/manifest/entries.json"

if [[ ! -f "$MANIFEST" ]]; then
    echo "Error: Wallpaper manifest not found at $MANIFEST" >&2
    echo "This script requires macOS Sonoma (14) or later." >&2
    exit 1
fi

UUID=$(uuidgen)

echo "=== Installing wallpaper ==="
echo "  Name: $DISPLAY_NAME"
echo "  UUID: $UUID"

# Copy video
cp "$INPUT" "$AERIALS_DIR/videos/$UUID.mov"
echo "  Copied video"

# Generate thumbnail
mkdir -p "$AERIALS_DIR/thumbnails"
ffmpeg -y -i "$INPUT" \
    -vf "select=eq(n\,0),scale=640:-1" \
    -vframes 1 -update 1 -q:v 2 \
    "$AERIALS_DIR/thumbnails/$UUID.jpg" 2>/dev/null
echo "  Generated thumbnail"

# Add to manifest
python3 << PYEOF
import json, os

manifest_path = os.path.expanduser("$MANIFEST")
with open(manifest_path) as f:
    d = json.load(f)

UUID = "$UUID"
DISPLAY_NAME = "$DISPLAY_NAME"
CUSTOM_CAT_ID = "CUSTOM-STILL-TO-LIFE-00000000"
CUSTOM_SUB_ID = "CUSTOM-STILL-TO-LIFE-SUB-0000"

# Add custom category if it doesn't exist
cat_ids = [c["id"] for c in d["categories"]]
if CUSTOM_CAT_ID not in cat_ids:
    d["categories"].append({
        "id": CUSTOM_CAT_ID,
        "localizedNameKey": "Custom",
        "localizedDescriptionKey": "Custom wallpapers",
        "preferredOrder": len(d["categories"]),
        "previewImage": "",
        "representativeAssetID": UUID,
        "subcategories": [{
            "id": CUSTOM_SUB_ID,
            "localizedNameKey": "StillToLife",
            "localizedDescriptionKey": "Custom parallax wallpapers",
            "preferredOrder": 0,
            "previewImage": "",
            "representativeAssetID": UUID
        }]
    })

# Add asset
asset_ids = [a["id"] for a in d["assets"]]
if UUID not in asset_ids:
    video_path = os.path.expanduser("~/Library/Application Support/com.apple.wallpaper/aerials/videos/" + UUID + ".mov")
    d["assets"].append({
        "id": UUID,
        "accessibilityLabel": DISPLAY_NAME,
        "categories": [CUSTOM_CAT_ID],
        "subcategories": [CUSTOM_SUB_ID],
        "includeInShuffle": True,
        "localizedNameKey": DISPLAY_NAME,
        "pointsOfInterest": {},
        "preferredOrder": 0,
        "previewImage": "",
        "shotID": "CUSTOM_" + UUID[:8],
        "showInTopLevel": True,
        "url-4K-SDR-240FPS": "file://" + video_path
    })

with open(manifest_path, "w") as f:
    json.dump(d, f, indent=2)

print(f"  Registered in manifest ({len(d['assets'])} total assets)")
PYEOF

# Restart wallpaper service
killall WallpaperAgent 2>/dev/null || true
echo "  Restarted WallpaperAgent"

echo ""
echo "=== Done! ==="
echo "  Open System Settings > Wallpaper"
echo "  Look for the \"Custom\" category"
echo "  Select \"$DISPLAY_NAME\""
