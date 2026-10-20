"""V152 integration test: no real customer records, uploads, or internet."""
from pathlib import Path
import ast
import subprocess
import tempfile

import imageio_ffmpeg
from media_video_compression import compress_portfolio_video, MAX_INPUT_BYTES, MAX_OUTPUT_BYTES

source=Path("app.py").read_text(encoding="utf-8")
ast.parse(source,filename="app.py")
for fragment in [
    "SERVICE_PORTFOLIO_MAX_VIDEO_BYTES = 10 * 1024 * 1024",
    "SERVICE_PORTFOLIO_MAX_COMPRESS_INPUT_BYTES = 30 * 1024 * 1024",
    "SERVICE_PORTFOLIO_MAX_MEDIA_RAW_BATCH_BYTES = 35 * 1024 * 1024",
    "data = compress_portfolio_video(data)",
    'mime_type, extension = "video/mp4", ".mp4"',
    "raw_batch_total += len(data)",
    "batch_total += len(data)",
    "Maximum 6 files, 35 MB source batch and 20 MB stored batch",
    '@app.route("/admin/service-portfolios/design-branding/media", methods=["POST"])',
    "validate_csrf()",
    "ON CONFLICT (service_key,sha256) DO NOTHING",
]:
    assert fragment in source,fragment
assert MAX_INPUT_BYTES==30*1024*1024
assert MAX_OUTPUT_BYTES==10*1024*1024

with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/"source.mp4"
    command=[
        imageio_ffmpeg.get_ffmpeg_exe(),"-hide_banner","-nostdin","-y","-loglevel","error",
        "-f","lavfi","-i","testsrc=size=640x360:rate=15","-t","3",
        "-c:v","mpeg4","-q:v","3",str(path),
    ]
    subprocess.run(command,check=True,timeout=20)
    original=path.read_bytes()
    out=compress_portfolio_video(original)
    assert len(out)<MAX_OUTPUT_BYTES and out[4:8]==b"ftyp"
    assert len(out)<len(original),(len(out),len(original))
    assert len(out)>100
    print("PASS V152 real video transcoding:",len(original),"bytes to",len(out),"bytes")
    try:
        compress_portfolio_video(b"not-a-video")
    except ValueError as exc:
        assert "Could not compress" in str(exc)
    else:
        raise AssertionError("Invalid media must be rejected")

print("PASS V152 bounded real transcoding, original route and CSRF intact")
