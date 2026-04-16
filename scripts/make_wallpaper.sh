#!/bin/bash
# Turn a static image into a moving macOS wallpaper using DepthFlow parallax.
#
# Usage:
#   ./scripts/make_wallpaper.sh <image> [options]
#
# Examples:
#   ./scripts/make_wallpaper.sh source_photos/painting.jpg
#   ./scripts/make_wallpaper.sh source_photos/painting.jpg --style dolly --intensity 1.2
#   ./scripts/make_wallpaper.sh source_photos/painting.jpg --style circle --duration 30 --fps 60
#
# Requirements (all free, all local):
#   - Python 3.12 or 3.13 (brew install python@3.13)
#   - uv (brew install uv)
#   - ffmpeg (brew install ffmpeg)
#
# What it does:
#   1. Estimates depth from the image using Depth Anything V2
#   2. Renders a 2.5D parallax animation with DepthFlow
#   3. Converts to HEVC .mov optimized for macOS wallpaper use

set -euo pipefail

# --- Defaults ---
STYLE="dolly"
INTENSITY="1.2"
WIDTH="3840"
HEIGHT="2160"
FPS="30"
DURATION="22"
CRF="18"
QUALITY="60"
SSAA=""
SPEED=""
OUTPUT_NAME=""
VENV_DIR="${HOME}/.cache/depthflow-env"
DEPTHFLOW_EXTRA=()

# --- Parse args ---
INPUT=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --style)     STYLE="$2"; shift 2 ;;
        --intensity) INTENSITY="$2"; shift 2 ;;
        --width)     WIDTH="$2"; shift 2 ;;
        --height)    HEIGHT="$2"; shift 2 ;;
        --fps)       FPS="$2"; shift 2 ;;
        --duration)  DURATION="$2"; shift 2 ;;
        --crf)       CRF="$2"; shift 2 ;;
        --output)    OUTPUT_NAME="$2"; shift 2 ;;
        --quality)   QUALITY="$2"; shift 2 ;;
        --ssaa)      SSAA="$2"; shift 2 ;;
        --speed)     SPEED="$2"; shift 2 ;;
        --)          shift; DEPTHFLOW_EXTRA=("$@"); break ;;
        --help|-h)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            echo ""
            echo "Options:"
            echo "  --style STR       Animation style: dolly, orbital, horizontal, vertical, circle, zoom (default: dolly)"
            echo "  --intensity NUM   Parallax intensity 0.0-4.0 (default: 1.2)"
            echo "  --width NUM       Output width (default: 3840)"
            echo "  --height NUM      Output height (default: 2160)"
            echo "  --fps NUM         Frames per second (default: 30)"
            echo "  --duration NUM    Loop duration in seconds (default: 22)"
            echo "  --crf NUM         Quality 0-51, lower=better (default: 18)"
            echo "  --quality NUM     Render quality 0-100 (default: 60)"
            echo "  --ssaa NUM        Super-sampling AA factor 0-4 (default: none)"
            echo "  --speed NUM       Time speed factor (default: 1)"
            echo "  --output NAME     Output filename without extension (default: derived from input)"
            echo "  --               Everything after this is passed directly to DepthFlow"
            exit 0
            ;;
        -*) echo "Unknown option: $1" >&2; exit 1 ;;
        *)  INPUT="$1"; shift ;;
    esac
done

if [[ -z "$INPUT" ]]; then
    echo "Error: No input image specified." >&2
    echo "Usage: $0 <image> [options]" >&2
    exit 1
fi

if [[ ! -f "$INPUT" ]]; then
    echo "Error: File not found: $INPUT" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR/output_videos"
mkdir -p "$OUTPUT_DIR"

if [[ -z "$OUTPUT_NAME" ]]; then
    OUTPUT_NAME="$(basename "${INPUT%.*}")_wallpaper"
fi

# Determine output paths (support absolute paths for web app)
if [[ "$OUTPUT_NAME" == /* ]]; then
    MP4_OUTPUT="${OUTPUT_NAME}.mp4"
    MOV_OUTPUT="${OUTPUT_NAME}.mov"
    mkdir -p "$(dirname "$OUTPUT_NAME")"
else
    MP4_OUTPUT="$OUTPUT_DIR/${OUTPUT_NAME}.mp4"
    MOV_OUTPUT="$OUTPUT_DIR/${OUTPUT_NAME}.mov"
fi

# --- Check dependencies ---
for cmd in ffmpeg python3.13; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Error: $cmd not found. Install with: brew install ${cmd/python3.13/python@3.13}" >&2
        exit 1
    fi
done

if ! command -v uv &>/dev/null; then
    echo "Error: uv not found. Install with: brew install uv" >&2
    exit 1
fi

# --- Set up DepthFlow environment (cached, only installs once) ---
if [[ ! -f "$VENV_DIR/bin/depthflow" ]]; then
    echo "=== Setting up DepthFlow (one-time install) ==="
    rm -rf "$VENV_DIR"
    uv venv --python 3.13 "$VENV_DIR" 2>/dev/null
    VIRTUAL_ENV="$VENV_DIR" uv pip install torch torchvision depthflow 2>&1 | tail -3
    echo "  Installed to $VENV_DIR"
fi

# --- Render parallax video ---
echo "=== Rendering parallax animation ==="
echo "  Input:     $INPUT"
echo "  Style:     $STYLE (intensity $INTENSITY)"
echo "  Output:    ${WIDTH}x${HEIGHT} @ ${FPS}fps, ${DURATION}s"

DEPTHFLOW="$VENV_DIR/bin/depthflow"

# Build main command args
MAIN_ARGS=(-w "$WIDTH" -h "$HEIGHT" -f "$FPS" -t "$DURATION" --quality "$QUALITY" -o "$MP4_OUTPUT")
[[ -n "$SSAA" ]] && MAIN_ARGS+=(--ssaa "$SSAA")
[[ -n "$SPEED" ]] && MAIN_ARGS+=(--speed "$SPEED")

"$DEPTHFLOW" \
    input -i "$INPUT" \
    "$STYLE" --intensity "$INTENSITY" \
    "${DEPTHFLOW_EXTRA[@]}" \
    h264 --preset slow --crf "$CRF" \
    main "${MAIN_ARGS[@]}" 2>&1 | grep -E "(Loading|Estimating|Resized|Finished|Stats|error)" || true

if [[ ! -f "$MP4_OUTPUT" ]]; then
    echo "Error: DepthFlow rendering failed." >&2
    exit 1
fi

# --- Convert to HEVC .mov for macOS ---
echo "=== Converting to macOS-optimized HEVC .mov ==="

ffmpeg -y -i "$MP4_OUTPUT" \
    -c:v hevc_videotoolbox -b:v 15M -tag:v hvc1 -an \
    "$MOV_OUTPUT" 2>/dev/null

rm -f "$MP4_OUTPUT"

DURATION_ACTUAL=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$MOV_OUTPUT")
SIZE=$(du -h "$MOV_OUTPUT" | cut -f1)
RESOLUTION=$(ffprobe -v quiet -show_entries stream=width,height -of csv=p=0 "$MOV_OUTPUT")

echo ""
echo "=== Done! ==="
echo "  Output:     $MOV_OUTPUT"
echo "  Resolution: $RESOLUTION"
echo "  Duration:   ${DURATION_ACTUAL}s"
echo "  Size:       $SIZE"
echo ""
echo "Preview: open \"$MOV_OUTPUT\""
