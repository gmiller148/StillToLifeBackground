from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def install_as_wallpaper(
    video_path: Path,
    display_name: str,
    project_dir: Path,
) -> tuple[bool, str]:
    """Install a .mov as a macOS wallpaper. Returns (success, message)."""
    script = project_dir / "scripts" / "install_wallpaper.sh"

    if not video_path.exists():
        return False, f"Video file not found: {video_path}"

    cmd = [str(script), str(video_path), display_name]
    logger.info("Installing wallpaper: %s", " ".join(cmd))

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        if process.returncode != 0:
            error = stderr_text.strip() or stdout_text.strip() or "Unknown error"
            logger.error("Install failed (exit %d): %s", process.returncode, error)
            return False, error

        logger.info("Wallpaper installed: %s", display_name)
        return True, "Wallpaper installed. Open System Settings > Wallpaper and look for the Custom category."

    except Exception as exc:
        logger.exception("Install exception")
        return False, str(exc)
