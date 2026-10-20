"""Bounded, server-side compression of oversized IBROWS admin video samples.

This module does not publish or persist media. The caller must authenticate, check
CSRF, validate MIME signatures and enforce the final database upload limit.
"""
import os
import subprocess
import tempfile
from pathlib import Path

MAX_INPUT_BYTES = 30 * 1024 * 1024
MAX_OUTPUT_BYTES = 10 * 1024 * 1024
MAX_PROCESS_SECONDS = 55


def compress_portfolio_video(data, max_output_bytes=MAX_OUTPUT_BYTES):
    """Re-encode MP4/WebM sample to mobile-compatible MP4 below storage limit.

    No silent trimming: when quality/duration cannot fit the budget, the caller
    receives an actionable error and the original asset remains unchanged.
    """
    if not isinstance(data, bytes) or not data:
        raise ValueError("Choose a video file to compress.")
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("Video exceeds the 30 MB compression limit. Export a shorter clip first.")
    if max_output_bytes <= 0 or max_output_bytes > MAX_OUTPUT_BYTES:
        raise ValueError("Invalid compressed video storage limit.")

    # ffmpeg binary is supplied by pinned imageio-ffmpeg wheel, no shell invoked.
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        executable = get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError) as exc:
        raise ValueError("Video compression is temporarily unavailable. Try a video below 10 MB.") from exc

    with tempfile.TemporaryDirectory(prefix="ibrows-media-") as temp:
        source = Path(temp) / "original"
        result = Path(temp) / "compressed.mp4"
        source.write_bytes(data)
        command = [
            executable, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
            "-threads", "1", "-filter_threads", "1", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a:0?",
            "-vf", "scale=960:960:force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-crf", "31",
            "-maxrate", "900k", "-bufsize", "1800k",
            "-c:a", "aac", "-b:a", "64k", "-ac", "2",
            "-movflags", "+faststart", "-map_metadata", "-1",
            str(result),
        ]
        try:
            proc = subprocess.run(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                timeout=MAX_PROCESS_SECONDS, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(
                "This clip took too long to compress. Please export a shorter video."
            ) from exc
        if proc.returncode != 0 or not result.is_file():
            raise ValueError(
                "Could not compress this video. Please use a valid MP4/WebM clip or shorten it."
            )
        size = result.stat().st_size
        if size < 100 or size > max_output_bytes:
            raise ValueError(
                "The video cannot fit under 10 MB at acceptable settings. "
                "Shorten the clip and try again."
            )
        output = result.read_bytes()
    # Validate MP4 magic rather than trusting the transcoder's extension.
    if len(output) < 12 or output[4:8] != b"ftyp":
        raise ValueError("The compressed video output was invalid.")
    return output
