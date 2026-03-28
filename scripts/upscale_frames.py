"""Upscale video frames using Real-ESRGAN via spandrel."""
import glob
import os
import sys

import cv2
import numpy as np
import torch
from spandrel import ImageModelDescriptor, ModelLoader


MODEL_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
MODEL_CACHE = os.path.expanduser("~/.cache/realesrgan/RealESRGAN_x4plus.pth")


def download_model():
    if os.path.exists(MODEL_CACHE):
        return MODEL_CACHE
    os.makedirs(os.path.dirname(MODEL_CACHE), exist_ok=True)
    print(f"Downloading model to {MODEL_CACHE}...")
    import urllib.request
    urllib.request.urlretrieve(MODEL_URL, MODEL_CACHE)
    print("Download complete.")
    return MODEL_CACHE


def get_device():
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def upscale_frame(model, img_np, device, tile_size=512):
    """Upscale a single frame. Uses tiling for memory efficiency."""
    img = img_np.astype(np.float32) / 255.0
    img_tensor = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0).to(device)

    h, w = img_tensor.shape[2], img_tensor.shape[3]

    if h <= tile_size and w <= tile_size:
        with torch.no_grad():
            output = model(img_tensor)
    else:
        # Tile-based processing for larger images
        scale = 4
        pad = 10
        output = torch.zeros(1, 3, h * scale, w * scale, device=device)
        count = torch.zeros(1, 1, h * scale, w * scale, device=device)

        for y in range(0, h, tile_size):
            for x in range(0, w, tile_size):
                y1 = max(0, y - pad)
                x1 = max(0, x - pad)
                y2 = min(h, y + tile_size + pad)
                x2 = min(w, x + tile_size + pad)

                tile = img_tensor[:, :, y1:y2, x1:x2]
                with torch.no_grad():
                    tile_out = model(tile)

                out_y1 = (y - y1) * scale
                out_x1 = (x - x1) * scale
                out_h = min(tile_size, h - y) * scale
                out_w = min(tile_size, w - x) * scale

                output[:, :, y*scale:(y*scale)+out_h, x*scale:(x*scale)+out_w] = \
                    tile_out[:, :, out_y1:out_y1+out_h, out_x1:out_x1+out_w]
                count[:, :, y*scale:(y*scale)+out_h, x*scale:(x*scale)+out_w] += 1

        output = output / count.clamp(min=1)

    output = output.squeeze(0).permute(1, 2, 0).clamp(0, 1).cpu().numpy()
    return (output * 255).astype(np.uint8)


def main():
    if len(sys.argv) < 3:
        print("Usage: python upscale_frames.py <input_dir> <output_dir>")
        sys.exit(1)

    input_dir = sys.argv[1]
    output_dir = sys.argv[2]
    os.makedirs(output_dir, exist_ok=True)

    device = get_device()
    print(f"Using device: {device}")

    model_path = download_model()
    model = ModelLoader().load_from_file(model_path)
    assert isinstance(model, ImageModelDescriptor)
    model = model.to(device).eval()
    print(f"Model loaded: scale={model.scale}x")

    frames = sorted(glob.glob(os.path.join(input_dir, "*.png")))
    total = len(frames)
    print(f"Upscaling {total} frames...")

    for i, frame_path in enumerate(frames):
        fname = os.path.basename(frame_path)
        out_path = os.path.join(output_dir, fname)

        img = cv2.imread(frame_path, cv2.IMREAD_COLOR)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        output_rgb = upscale_frame(model, img_rgb, device)
        output_bgr = cv2.cvtColor(output_rgb, cv2.COLOR_RGB2BGR)
        cv2.imwrite(out_path, output_bgr)

        if (i + 1) % 10 == 0 or i == 0 or i == total - 1:
            print(f"  [{i+1}/{total}] {fname}")

    print("Done!")


if __name__ == "__main__":
    main()
