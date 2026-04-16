from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from web.jobs import JobConfig, JobStore

logger = logging.getLogger(__name__)

# Per-job progress queues for SSE streaming
progress_queues: dict[str, asyncio.Queue] = {}

# Serialize GPU-bound jobs
_processing_semaphore = asyncio.Semaphore(1)


async def _emit(job_id: str, event_type: str, **data):
    queue = progress_queues.get(job_id)
    if queue:
        await queue.put({"type": event_type, **data})


def build_extra_depthflow_args(config: JobConfig) -> list[str]:
    """Build extra DepthFlow CLI args inserted between the preset and encoder."""
    args: list[str] = []
    style = config.style

    # --- Style-specific flags (attach to the preceding preset command) ---

    if config.preset_reverse:
        args.append("--reverse")

    # smooth/linear (dolly, horizontal, vertical, zoom)
    if style in ("dolly", "horizontal", "vertical", "zoom") and config.preset_smooth is not None:
        args.append("--smooth" if config.preset_smooth else "--linear")

    # loop/no-loop (dolly, horizontal, vertical, zoom)
    if style in ("dolly", "horizontal", "vertical", "zoom") and config.preset_loop is not None:
        args.append("--loop" if config.preset_loop else "--no-loop")

    # depth (dolly, orbital)
    if style in ("dolly", "orbital") and config.preset_depth is not None:
        args.extend(["--depth", str(config.preset_depth)])

    # phase
    if style == "circle":
        px = config.circle_phase_x if config.circle_phase_x is not None else 0.0
        py = config.circle_phase_y if config.circle_phase_y is not None else 0.0
        pz = config.circle_phase_z if config.circle_phase_z is not None else 0.0
        if any(v != 0.0 for v in (px, py, pz)):
            args.extend(["--phase", str(px), str(py), str(pz)])
    elif style in ("dolly", "horizontal", "vertical", "zoom") and config.preset_phase is not None:
        args.extend(["--phase", str(config.preset_phase)])

    # zoom (orbital)
    if style == "orbital" and config.preset_zoom is not None:
        args.extend(["--zoom", str(config.preset_zoom)])

    # steady (horizontal, vertical, circle)
    if style in ("horizontal", "vertical", "circle") and config.preset_steady is not None:
        args.extend(["--steady", str(config.preset_steady)])

    # isometric (horizontal, vertical, circle, zoom)
    if style in ("horizontal", "vertical", "circle", "zoom") and config.preset_isometric is not None:
        args.extend(["--isometric", str(config.preset_isometric)])

    # circle amplitudes
    if style == "circle":
        ax = config.circle_amp_x if config.circle_amp_x is not None else 1.0
        ay = config.circle_amp_y if config.circle_amp_y is not None else 1.0
        az = config.circle_amp_z if config.circle_amp_z is not None else 0.0
        if (ax, ay, az) != (1.0, 1.0, 0.0):
            args.extend(["--amplitude", str(ax), str(ay), str(az)])

    # --- State overrides ---
    state_args: list[str] = []

    for field, flag in [
        ("state_height", "-h"),
        ("state_steady", "-s"),
        ("state_focus", "-f"),
        ("state_zoom", "-z"),
        ("state_isometric", "-i"),
        ("state_dolly", "-d"),
        ("state_invert", "-v"),
    ]:
        val = getattr(config, field)
        if val is not None:
            state_args.extend([flag, str(val)])

    if config.state_mirror is not None:
        state_args.append("--mirror" if config.state_mirror else "--no-mirror")

    for field, flag in [
        ("state_offset_x", "--ofx"),
        ("state_offset_y", "--ofy"),
        ("state_center_x", "--cex"),
        ("state_center_y", "--cey"),
        ("state_origin_x", "--orx"),
        ("state_origin_y", "--ory"),
    ]:
        val = getattr(config, field)
        if val is not None:
            state_args.extend([flag, str(val)])

    if state_args:
        args.extend(["state", *state_args])

    # --- Custom oscillators ---
    if config.oscillators:
        try:
            oscillators = json.loads(config.oscillators)
            for osc in oscillators:
                wave = osc.get("type", "sine")
                target = osc.get("target", "nothing")
                args.append(wave)
                args.extend(["-t", target])

                if wave in ("sine", "cosine", "triangle"):
                    if "amplitude" in osc:
                        args.extend(["-a", str(osc["amplitude"])])
                    if "bias" in osc:
                        args.extend(["-b", str(osc["bias"])])
                    if "cycles" in osc:
                        args.extend(["-c", str(osc["cycles"])])
                    if "phase" in osc:
                        args.extend(["-p", str(osc["phase"])])
                elif wave == "linear":
                    for key, flag in [("start", "--start"), ("end", "--end"),
                                      ("low", "--low"), ("high", "--high"),
                                      ("exponent", "--exponent")]:
                        if key in osc:
                            args.extend([flag, str(osc[key])])
                elif wave in ("set", "add"):
                    if "value" in osc:
                        args.extend(["-v", str(osc["value"])])

                if osc.get("cumulative"):
                    args.append("--cumulative")
                if osc.get("reverse"):
                    args.append("--reverse")
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("Invalid oscillators JSON, skipping: %s", config.oscillators)

    # --- Post-processing ---
    if config.vignette_enable:
        args.extend(["vignette",
                      "-i", str(config.vignette_intensity),
                      "-d", str(config.vignette_decay)])

    if config.lens_enable:
        args.extend(["lens",
                      "-i", str(config.lens_intensity),
                      "-d", str(config.lens_decay),
                      "-q", str(config.lens_quality)])

    if config.blur_enable:
        args.extend(["blur",
                      "-i", str(config.blur_intensity),
                      "-a", str(config.blur_start),
                      "-b", str(config.blur_end),
                      "-x", str(config.blur_exponent),
                      "-q", str(config.blur_quality),
                      "-d", str(config.blur_directions)])

    if config.inpaint_enable:
        inpaint_args = ["inpaint"]
        if config.inpaint_black:
            inpaint_args.append("--black")
        inpaint_args.extend(["-l", str(config.inpaint_limit)])
        args.extend(inpaint_args)

    if config.colors_enable:
        args.extend(["colors",
                      "-s", str(config.colors_saturation),
                      "-c", str(config.colors_contrast),
                      "-b", str(config.colors_brightness),
                      "-g", str(config.colors_gamma),
                      "-x", str(config.colors_grayscale),
                      "-n", str(config.colors_sepia)])

    return args


async def run_pipeline(
    job_id: str,
    image_path: Path,
    config: JobConfig,
    job_store: JobStore,
    project_dir: Path,
):
    progress_queues[job_id] = asyncio.Queue()

    async with _processing_semaphore:
        job_store.update_job(job_id, status="processing")
        await _emit(job_id, "progress", stage="queued", message="Starting processing...", percent=0)

        script = project_dir / "scripts" / "make_wallpaper.sh"
        output_path = project_dir / "data" / "videos" / job_id

        cmd = [
            str(script),
            str(image_path),
            "--style", config.style,
            "--intensity", str(config.intensity),
            "--width", str(config.width),
            "--height", str(config.height),
            "--fps", str(config.fps),
            "--duration", str(config.duration),
            "--crf", str(config.crf),
            "--quality", str(config.render_quality),
            "--output", str(output_path),
        ]

        if config.ssaa is not None:
            cmd.extend(["--ssaa", str(config.ssaa)])
        if config.speed is not None:
            cmd.extend(["--speed", str(config.speed)])

        extra = build_extra_depthflow_args(config)
        if extra:
            cmd.extend(["--", *extra])

        logger.info("Running pipeline: %s", " ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "TERM": "dumb"},
            )

            stderr_lines = []

            async def read_stdout():
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace").strip()
                    if not text:
                        continue
                    logger.debug("stdout: %s", text)

                    if "Setting up DepthFlow" in text:
                        await _emit(job_id, "progress", stage="setup", message="Setting up DepthFlow (first-time install)...", percent=5)
                    elif "Rendering parallax" in text:
                        await _emit(job_id, "progress", stage="rendering", message="Rendering parallax animation...", percent=10)
                    elif "Loading" in text or "Estimating" in text:
                        await _emit(job_id, "progress", stage="rendering", message=text, percent=20)
                    elif "Resized" in text:
                        await _emit(job_id, "progress", stage="rendering", message=text, percent=30)
                    elif "Finished" in text or "Stats" in text:
                        await _emit(job_id, "progress", stage="rendering", message=text, percent=70)
                    elif "Converting" in text:
                        await _emit(job_id, "progress", stage="converting", message="Converting to HEVC .mov...", percent=80)
                    elif "Done!" in text:
                        await _emit(job_id, "progress", stage="finalizing", message="Finalizing...", percent=95)

            async def read_stderr():
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace").strip()
                    if text:
                        stderr_lines.append(text)
                        logger.debug("stderr: %s", text)

            await asyncio.gather(read_stdout(), read_stderr())
            returncode = await process.wait()

            mov_output = Path(str(output_path) + ".mov")

            if returncode != 0 or not mov_output.exists():
                error_msg = "\n".join(stderr_lines[-10:]) if stderr_lines else "Pipeline failed with no error output"
                logger.error("Pipeline failed (exit %d): %s", returncode, error_msg)
                job_store.update_job(job_id, status="failed", error=error_msg)
                await _emit(job_id, "error", message=f"Processing failed: {error_msg}")
            else:
                # Get video metadata
                video_size = mov_output.stat().st_size
                video_duration = None
                try:
                    probe = await asyncio.create_subprocess_exec(
                        "ffprobe", "-v", "quiet",
                        "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(mov_output),
                        stdout=asyncio.subprocess.PIPE,
                    )
                    probe_out, _ = await probe.communicate()
                    video_duration = float(probe_out.decode().strip())
                except Exception:
                    logger.warning("Could not probe video duration")

                job_store.update_job(
                    job_id,
                    status="completed",
                    completed_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                    video_size_bytes=video_size,
                    video_duration_seconds=video_duration,
                )
                complete_data = {"job_id": job_id, "video_url": f"/api/jobs/{job_id}/video"}
                queue = progress_queues.get(job_id)
                if queue:
                    await queue.put({"type": "complete", **complete_data})
                logger.info("Pipeline completed: %s (%d bytes)", mov_output, video_size)

        except Exception as exc:
            error_msg = str(exc)
            logger.exception("Pipeline exception for job %s", job_id)
            job_store.update_job(job_id, status="failed", error=error_msg)
            await _emit(job_id, "error", message=f"Processing failed: {error_msg}")

        finally:
            # Send a sentinel so SSE consumers know to stop, then clean up
            queue = progress_queues.pop(job_id, None)
            if queue:
                # Drain isn't needed; the consumer will see the complete/error event
                pass
