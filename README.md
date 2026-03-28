# MacBackgrounds

Turn static images into moving macOS wallpapers using AI depth estimation and parallax animation. Everything runs locally on your Mac for free.

## How it works

1. **Depth Anything V2** estimates a depth map from your image
2. **DepthFlow** renders a 2.5D parallax animation using the depth map — the camera gently drifts through the scene, giving the image a cinematic "living" quality
3. **ffmpeg** converts the output to HEVC .mov optimized for macOS

The original image detail is fully preserved — no generative AI modifies your image. The depth model only determines which parts are near/far so the parallax effect looks natural.

## Requirements

All free, all local:

```bash
brew install python@3.13 uv ffmpeg
```

## Quick start

```bash
git clone <this-repo> && cd MacBackgrounds
brew install python@3.13 uv ffmpeg    # skip if already installed
mkdir -p source_photos
```

Drop any image (photo, painting, poster) into `source_photos/`, then:

```bash
./scripts/make_wallpaper.sh source_photos/your_image.jpg
```

That's it. Output lands in `output_videos/`.

### More examples

```bash
# Customize the animation
./scripts/make_wallpaper.sh source_photos/your_image.jpg \
    --style dolly --intensity 1.2 --duration 30

# See all options
./scripts/make_wallpaper.sh --help
```

First run takes a couple of minutes to install DepthFlow + PyTorch to `~/.cache/depthflow-env`. After that, renders take ~40 seconds for a 22-second 4K video.

Output goes to `output_videos/` as an HEVC .mov file.

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--style` | `dolly` | Animation: `dolly`, `orbital`, `horizontal`, `vertical`, `circle`, `zoom` |
| `--intensity` | `1.2` | Parallax depth 0.0–2.0. Higher = more dramatic movement |
| `--width` | `3840` | Output width in pixels |
| `--height` | `2160` | Output height in pixels |
| `--fps` | `30` | Frames per second |
| `--duration` | `22` | Loop duration in seconds |
| `--crf` | `18` | Quality (0–51, lower = better) |
| `--output` | auto | Output filename (without extension) |

### Animation styles

- **dolly** — Camera pushes in and out, creating a breathing depth effect. Best for landscapes with clear foreground/background separation.
- **orbital** — Camera orbits gently around a focal point. Good all-around choice.
- **horizontal** — Side-to-side pan. Good for wide panoramic images.
- **vertical** — Up-and-down movement.
- **circle** — Circular orbit path.
- **zoom** — Zoom in and out.

## Setting as macOS wallpaper

After generating your .mov file, use one of these to set it as your wallpaper:

- **[VideoPaper](https://github.com/Mcrich-LLC/VideoPaper)** (free, macOS 26+) — `brew tap mcrich-llc/homebrew-formulae && brew install --cask VideoPaper`. Videos appear natively in System Settings > Wallpaper.
- **[Backdrop](https://cindori.com/backdrop)** ($9.99) — Most polished option. 4K playback, <0.3% CPU, multi-monitor, lock screen support.
- **[Aerial](https://aerialscreensaver.github.io/)** (free) — Screensaver that plays custom videos alongside Apple's built-in aerials.

## Bonus: Real-ESRGAN upscaler

The `scripts/upscale_frames.py` utility upscales images 4x using Real-ESRGAN. Useful if your source image is low resolution:

```bash
# Install upscaler dependencies
uv sync

# Upscale a single image (put it in a folder)
mkdir -p /tmp/in /tmp/out
cp my_image.png /tmp/in/
uv run python scripts/upscale_frames.py /tmp/in /tmp/out
# Output: /tmp/out/my_image.png at 4x resolution
```

## Tech stack

All open-source, all running locally:

| Tool | Purpose | License |
|------|---------|---------|
| [DepthFlow](https://github.com/BrokenSource/DepthFlow) | Parallax animation rendering | AGPL-3.0 |
| [Depth Anything V2](https://huggingface.co/depth-anything) | Monocular depth estimation | Apache 2.0 (small model) |
| [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) | AI image upscaling | BSD-3 |
| [PyTorch](https://pytorch.org/) | ML inference (MPS on Apple Silicon) | BSD |
| [ffmpeg](https://ffmpeg.org/) | Video encoding | LGPL |
