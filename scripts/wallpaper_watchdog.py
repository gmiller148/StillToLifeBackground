#!/usr/bin/env python3
"""Re-inject custom wallpaper entries when macOS overwrites the manifest.

macOS periodically fetches a new manifest.tar from Apple's CDN and
overwrites ~/Library/Application Support/com.apple.wallpaper/aerials/manifest/entries.json,
wiping any custom entries. This script merges them back in.

Designed to be triggered by a launchd WatchPaths agent.
"""
import json
import os
import subprocess
import sys
import time

CONFIG_DIR = os.path.expanduser("~/.config/custom-wallpapers")
CUSTOM_ENTRIES = os.path.join(CONFIG_DIR, "custom_entries.json")
MANIFEST = os.path.expanduser(
    "~/Library/Application Support/com.apple.wallpaper/aerials/manifest/entries.json"
)
LOG_FILE = os.path.join(CONFIG_DIR, "watchdog.log")
LOCKFILE = os.path.join(CONFIG_DIR, ".watchdog.lock")


def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def main():
    # Debounce: skip if we wrote the manifest less than 10 seconds ago
    if os.path.exists(LOCKFILE):
        lock_age = time.time() - os.path.getmtime(LOCKFILE)
        if lock_age < 10:
            return

    if not os.path.exists(CUSTOM_ENTRIES):
        log(f"No custom entries file at {CUSTOM_ENTRIES}, nothing to do")
        return

    if not os.path.exists(MANIFEST):
        log(f"Manifest not found at {MANIFEST}")
        return

    with open(CUSTOM_ENTRIES) as f:
        custom = json.load(f)

    with open(MANIFEST) as f:
        manifest = json.load(f)

    custom_assets = custom.get("assets", [])
    custom_categories = custom.get("categories", [])

    if not custom_assets:
        return

    # Check if custom entries are already present
    existing_ids = {a["id"] for a in manifest.get("assets", [])}
    missing_assets = [a for a in custom_assets if a["id"] not in existing_ids]

    existing_cat_ids = {c["id"] for c in manifest.get("categories", [])}
    missing_categories = [c for c in custom_categories if c["id"] not in existing_cat_ids]

    if not missing_assets and not missing_categories:
        return

    # Verify video files still exist before injecting
    videos_dir = os.path.expanduser(
        "~/Library/Application Support/com.apple.wallpaper/aerials/videos"
    )
    valid_assets = []
    for asset in missing_assets:
        video_path = os.path.join(videos_dir, asset["id"] + ".mov")
        if os.path.exists(video_path):
            valid_assets.append(asset)
        else:
            log(f"Skipping {asset['id']} — video file missing")

    if not valid_assets and not missing_categories:
        return

    # Merge custom entries back in
    manifest["assets"].extend(valid_assets)
    manifest["categories"].extend(missing_categories)

    # Write lockfile before writing manifest (debounce)
    with open(LOCKFILE, "w") as f:
        f.write(str(time.time()))

    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)

    log(f"Re-injected {len(valid_assets)} assets, {len(missing_categories)} categories")

    # Restart WallpaperAgent
    subprocess.run(["killall", "WallpaperAgent"], capture_output=True)
    subprocess.run(["killall", "WallpaperAerialsExtension"], capture_output=True)
    log("Restarted WallpaperAgent")


if __name__ == "__main__":
    main()
