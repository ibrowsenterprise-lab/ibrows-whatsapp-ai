#!/usr/bin/env python3
"""Unify IBROWS typography without changing routes, branding or code blocks.
Reproducible: verify exact V134 blob before changing source; verify exact V135 blob after.
"""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
BASE_SHA = "0978973680f0cdafa83d1d2742faa24193a8a779"
TARGET_SHA = "47d4c7ccd80986f92c522486f2b729b2b766b0f3"
FONT_STACK = "system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif"
FONT_RULE = ":where(button,input,select,textarea){font-family:inherit;}"

def sha(path):
    return subprocess.check_output(["git","hash-object",str(path)], text=True).strip()

def transform(source):
    families = {
        "Inter,Arial,Helvetica,sans-serif", "Inter,Arial,sans-serif",
        "Arial, Helvetica, sans-serif", "Arial,Helvetica,sans-serif",
        "Arial,sans-serif", "Arial",
    }
    matches = [0]
    def replace(match):
        if match.group(2).strip() not in families:
            return match.group(0)
        matches[0] += 1
        return match.group(1) + FONT_STACK
    new = re.sub(r"(font-family\s*:\s*)([^;\n}]+)", replace, source)
    if matches[0] != 46:
        raise ValueError(f"Expected 46 old font declarations, got {matches[0]}")
    if new.count("</style>") != 41:
        raise ValueError("Expected 41 template stylesheets")
    new = new.replace("</style>", FONT_RULE + "</style>")
    assert new.count(FONT_RULE) == 41
    old_build = 'IBROWS_BUILD_VERSION = "2026-10-09-business-email-intake-v134"'
    new_build = 'IBROWS_BUILD_VERSION = "2026-10-09-font-consistency-v135"'
    if new.count(old_build) != 1:
        raise ValueError("Unexpected V134 build marker")
    new = new.replace(old_build, new_build, 1)
    marker = 'print("BUSINESS EMAIL V134 READY: enquiry=on no_website_required=on quotation_only=on", flush=True)'
    if new.count(marker) != 1:
        raise ValueError("V134 readiness marker not found")
    new = new.replace(marker, marker + '\nprint("TYPOGRAPHY V135 READY: system_font=on template_styles=41", flush=True)', 1)
    return new

def main():
    path = ROOT / "app.py"
    old = sha(path)
    if old == TARGET_SHA:
        print("V135 source already installed and verified")
        return
    if old != BASE_SHA:
        raise SystemExit("Refusing to patch unexpected app.py: " + old)
    result = transform(path.read_text())
    compile(result, str(path), "exec")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as tmp:
        tmp.write(result)
        tmp_path = Path(tmp.name)
    try:
        new_hash = sha(tmp_path)
        if new_hash != TARGET_SHA:
            raise SystemExit("Wrong V135 blob: " + new_hash)
    finally:
        tmp_path.unlink()
    path.write_text(result)
    print("Generated exact V135 app.py blob", new_hash)

if __name__=="__main__":
    main()
