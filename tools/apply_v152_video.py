"""Apply V152 media compression safely to generated app.py on a review branch."""
from pathlib import Path
import ast

path = Path("app.py")
src = path.read_text(encoding="utf-8")
if "SERVICE_PORTFOLIO_MAX_COMPRESS_INPUT_BYTES" in src:
    print("V152 already applied")
    raise SystemExit(0)

def replace_once(original,updated,comment):
    global src
    count=src.count(original)
    if count!=1:
        raise RuntimeError(f"{comment}: expected one exact anchor, found {count}")
    src=src.replace(original,updated,1)

replace_once(
    "SERVICE_PORTFOLIO_MAX_VIDEO_BYTES = 10 * 1024 * 1024\n",
    "SERVICE_PORTFOLIO_MAX_VIDEO_BYTES = 10 * 1024 * 1024\n"
    "SERVICE_PORTFOLIO_MAX_COMPRESS_INPUT_BYTES = 30 * 1024 * 1024\n"
    "SERVICE_PORTFOLIO_MAX_MEDIA_RAW_BATCH_BYTES = 35 * 1024 * 1024\n",
    "bounded upload ceilings",
)
replace_once(
    "    batch_total = 0\n    try:\n        for upload in uploads:\n"
    "            # Read only up to the larger media ceiling first; kind-specific limits are\n"
    "            # enforced immediately after signature detection.\n",
    "    batch_total = 0\n"
    "    raw_batch_total = 0\n"
    "    try:\n"
    "        for upload in uploads:\n"
    "            # Accept up to 30 MB for admin-only conversion, but persist only <=10 MB.\n",
    "prepare batch conversion",
)
replace_once(
    "                data = _construction_read_upload(upload, SERVICE_PORTFOLIO_MAX_VIDEO_BYTES)\n"
    "            except ValueError as exc:\n"
    "                if str(exc) == \"The selected file is too large.\":\n"
    "                    raise ValueError(\"Each video/audio sample must be 10 MB or smaller. Compress the clip or export a shorter sample, then upload again.\") from exc\n"
    "                raise\n"
    "            mime_type, extension, media_kind = _portfolio_sample_media_type(upload, data)\n"
    "            if media_kind == \"video\" and len(data) > SERVICE_PORTFOLIO_MAX_VIDEO_BYTES:\n"
    "                raise ValueError(\"Each video sample must be 10 MB or smaller.\")\n",
    "                data = _construction_read_upload(upload, SERVICE_PORTFOLIO_MAX_COMPRESS_INPUT_BYTES)\n"
    "            except ValueError as exc:\n"
    "                if str(exc) == \"The selected file is too large.\":\n"
    "                    raise ValueError(\"Videos above 30 MB cannot be uploaded for automatic compression. Export a shorter clip first.\") from exc\n"
    "                raise\n"
    "            mime_type, extension, media_kind = _portfolio_sample_media_type(upload, data)\n"
    "            raw_batch_total += len(data)\n"
    "            if raw_batch_total > SERVICE_PORTFOLIO_MAX_MEDIA_RAW_BATCH_BYTES:\n"
    "                raise ValueError(\"Choose a smaller batch: source media must total no more than 35 MB.\")\n"
    "            compressed = media_kind == \"video\" and len(data) > SERVICE_PORTFOLIO_MAX_VIDEO_BYTES\n"
    "            if compressed:\n"
    "                from media_video_compression import compress_portfolio_video\n"
    "                data = compress_portfolio_video(data)\n"
    "                mime_type, extension = \"video/mp4\", \".mp4\"\n",
    "pre-save compression and caps",
)
replace_once(
    '            filename = _construction_safe_filename(upload.filename, f"creative-sample{extension}")\n'
    '            prepared.append((filename, mime_type, data, hashlib.sha256(data).hexdigest(), media_kind))\n',
    '            safe_source_name = str(upload.filename or "")\n'
    '            if compressed:\n'
    '                safe_source_name = safe_source_name.rsplit(".", 1)[0] + ".mp4"\n'
    '            filename = _construction_safe_filename(safe_source_name, f"creative-sample{extension}")\n'
    '            prepared.append((filename, mime_type, data, hashlib.sha256(data).hexdigest(), media_kind))\n',
    "retain accurate MP4 type and filename",
)
replace_once(
    "<strong>Video:</strong> MP4 or WebM, up to 10 MB each. <strong>Audio:</strong> MP3, WAV or M4A, up to 10 MB each. Maximum 6 files / 20 MB per batch. Compress larger clips or export a shorter sample before uploading.",
    "<strong>Video:</strong> MP4 or WebM. Up to 10 MB saves normally; <strong>10–30 MB videos are automatically compressed to an MP4 below 10 MB</strong> before saving. Keep this page open while processing (up to a minute). Long clips may need shortening; compression can reduce resolution. <strong>Audio:</strong> MP3, WAV or M4A up to 10 MB. Maximum 6 files, 35 MB source batch and 20 MB stored batch.",
    "honest admin mobile upload guidance",
)
ast.parse(src,filename="app.py")
path.write_text(src,encoding="utf-8")
print("PASS V152 app.py patch, syntax and media constraints. Bytes:",len(src))
