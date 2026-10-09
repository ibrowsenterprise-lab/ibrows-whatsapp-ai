#!/usr/bin/env python3
"""Add Fatuma Nyirenda, IT Specialist Lead, using the supplied genuine portrait.

Fail closed if the V135 source changed. No existing team records, original
photographs, pricing, security, or application routes are modified.
"""
from pathlib import Path
import ast
import base64
import hashlib
from io import BytesIO
import subprocess
from PIL import Image

ROOT=Path(__file__).resolve().parent.parent
APP=ROOT/"app.py"
PHOTO=ROOT/"tools/assets/fatuma-webp-256.b64"
BASE_SHA="47d4c7ccd80986f92c522486f2b729b2b766b0f3"
SOURCE_IMAGE_SHA256="3f30e95d45285826ce8b40b13a4428edfc63b6d3756b231e5ba7873fd42732ce"
NEW_BUILD="2026-10-09-fatuma-team-v136"

def sha(path):
    return subprocess.check_output(["git","hash-object",str(path)],cwd=ROOT,text=True).strip()

def one_replace(s,old,new):
    if s.count(old)!=1:
        raise RuntimeError(f"Expected one matching anchor, got {s.count(old)}: {old[:90]}")
    return s.replace(old,new,1)

def main():
    source=APP.read_text()
    if f'IBROWS_BUILD_VERSION = "{NEW_BUILD}"' in source:
        assert '"slug":"fatuma-nyirenda"' in source
        print("V136 staff update already present")
        return
    if sha(APP)!=BASE_SHA:
        raise SystemExit("Unexpected app.py source; do not overwrite newer code")
    raw=base64.b64decode(PHOTO.read_text().strip(),validate=True)
    if hashlib.sha256(raw).hexdigest()!=SOURCE_IMAGE_SHA256:
        raise SystemExit("Portrait checksum mismatch; not deploying")
    photo=Image.open(BytesIO(raw)).convert("RGB")
    assert photo.size==(256,256)
    output=BytesIO()
    photo.save(output,format="JPEG",quality=88,optimize=True,progressive=True,subsampling=0)
    jpeg=output.getvalue()
    assert jpeg.startswith(b"\xff\xd8") and jpeg.endswith(b"\xff\xd9")
    encoded=base64.b64encode(jpeg).decode("ascii")

    member=('    {"slug":"fatuma-nyirenda","name":"Fatuma Nyirenda",'
            '"role":"IT Specialist Lead","secondary":"",'
            '"bio":"Leads IT support, systems coordination and technical delivery across IBROWS digital projects."},\n')
    source=one_replace(source,
        ']\nPUBLIC_TEAM_IMAGE_B64 = {',
        member + ']\nPUBLIC_TEAM_IMAGE_B64 = {')
    source=one_replace(source,
        'PUBLIC_TEAM_IMAGE_B64 = {\n',
        'PUBLIC_TEAM_IMAGE_B64 = {\n    \'fatuma-nyirenda\': """'+encoded+'""",\n')
    source=one_replace(source,
        'IBROWS_BUILD_VERSION = "2026-10-09-font-consistency-v135"',
        'IBROWS_BUILD_VERSION = "'+NEW_BUILD+'"')
    source=one_replace(source,
        'print("TYPOGRAPHY V135 READY: system_font=on template_styles=41", flush=True)',
        'print("TYPOGRAPHY V135 READY: system_font=on template_styles=41", flush=True)\n'
        'print("TEAM V136 READY: Fatuma Nyirenda IT Specialist Lead, image=embedded", flush=True)')
    compile(source,str(APP),"exec")
    tree=ast.parse(source)
    members=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=="PUBLIC_TEAM_MEMBERS" for t in n.targets))
    assert len(members)==8 and len({x["slug"] for x in members})==8
    photos=next(n.value for n in tree.body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=="PUBLIC_TEAM_IMAGE_B64" for t in n.targets))
    values=ast.literal_eval(photos)
    assert all(m["slug"] in values for m in members)
    assert base64.b64decode(values["fatuma-nyirenda"])==jpeg
    APP.write_text(source)
    print(f"V136 compiled: {len(members)} team members, photo {len(jpeg)} bytes, app.py {sha(APP)}")

if __name__=="__main__":
    main()
