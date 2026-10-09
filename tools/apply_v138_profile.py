#!/usr/bin/env python3
"""Finish IBROWS 2026 company-profile integration without replacing its design.

Only changes the already-vacant sixth staff card on page 10 of the existing
company profile PDF, a public home navigation link, and the build marker.
The seven original records, original portraits and 168 app routes are retained.
Fails closed when app.py is not the audited V137 Git blob.
"""
import ast
import base64
import io
import subprocess
from pathlib import Path

import fitz
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.py"
BASE_BLOB = "7c0bd9947d09d4e7fa7f18ec0a05f110e78dd7ed"
BUILD = "2026-10-09-profile-team-integration-v138"

def git_blob():
    return subprocess.check_output(["git","hash-object",str(APP)],text=True,cwd=ROOT).strip()

def replace_one(source, old, new):
    count = source.count(old)
    if count != 1:
        raise AssertionError(f"Expected exactly one anchor; got {count}: {old[:100]!r}")
    return source.replace(old,new,1)

def literal_assignment(tree, name):
    matches = [
        n.value for n in tree.body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)
    ]
    if len(matches)!=1:
        raise AssertionError(f"Expected one top-level {name}: {len(matches)}")
    return matches[0]

def insert_centered(page, text, rect, font, size, color, label):
    rest = page.insert_textbox(fitz.Rect(rect), text, fontname=font,
                               fontsize=size, color=color, align=1,
                               overlay=True)
    if rest < 0:
        raise AssertionError(f"{label} did not fit: remaining={rest}")

def main():
    src=APP.read_text(encoding="utf-8")
    if f'IBROWS_BUILD_VERSION = "{BUILD}"' in src:
        print("V138 company profile integration already installed")
        return
    if git_blob()!=BASE_BLOB:
        raise SystemExit("App version changed since audit; stopping to prevent overwrite")
    tree=ast.parse(src)
    pdfnode=literal_assignment(tree,"IBROWS_COMPANY_PROFILE_PDF_B64")
    original_b64=ast.literal_eval(pdfnode)
    photos=ast.literal_eval(literal_assignment(tree,"PUBLIC_TEAM_IMAGE_B64"))
    staff=ast.literal_eval(literal_assignment(tree,"PUBLIC_TEAM_MEMBERS"))
    assert len(staff)==8 and len(photos)==8
    assert next(m for m in staff if m["slug"]=="fatuma-nyirenda")["role"]=="IT Specialist Lead"
    orig_pdf=base64.b64decode(original_b64,validate=True)
    doc=fitz.open(stream=orig_pdf,filetype="pdf")
    assert len(doc)==11, "Do not blindly modify a changed company profile"
    page=doc[9]
    old_text=page.get_text()
    assert "CORE TEAM" in old_text and "Specialist support" in old_text
    assert "Kumbukani Mkandawire" in old_text and "Fatuma Nyirenda" not in old_text
    assert abs(page.rect.width-595)<2 and abs(page.rect.height-842)<2

    # Reuse the existing vacant right-bottom support panel. Other content on
    # page 10 and all other PDF pages remains in place, rather than regenerating
    # the company profile or portraits.
    right_panel=fitz.Rect(378,318,549,495)
    page.add_redact_annot(right_panel,fill=(1,1,1),cross_out=False)
    page.apply_redactions(images=0,graphics=0,text=0)
    page.draw_rect(right_panel,color=(0.19,0.39,0.32),fill=(1,1,1),width=0.7,overlay=True)
    portrait=base64.b64decode(photos["fatuma-nyirenda"],validate=True)
    assert portrait.startswith(b"\xff\xd8") and portrait.endswith(b"\xff\xd9")
    page.insert_image(fitz.Rect(412,326,515,429),stream=portrait,keep_proportion=True,overlay=True)
    insert_centered(page,"Fatuma Nyirenda", (384,433,544,446),
                    "hebo",9.6,(0.10,0.18,0.16),"staff name")
    insert_centered(page,"IT Specialist Lead",(384,448,544,460),
                    "hebo",8.3,(0.13,0.40,0.32),"staff role")
    insert_centered(page,
        "Leads IT support, systems coordination and technical delivery across IBROWS digital projects.",
        (384,462,544,492),"helv",7.15,(0.29,0.32,0.32),"staff bio")

    finished=doc.tobytes(garbage=4,deflate=True)
    doc.close()
    reader=PdfReader(io.BytesIO(finished))
    assert len(reader.pages)==11
    final_team_text=reader.pages[9].extract_text()
    for person in ("Sylvester Katopola","Christopher Ngalu","Amos Mngoli",
                   "Lewis Tambala","Kumbukani Mkandawire","Fatuma Nyirenda",
                   "IT Specialist Lead"):
        assert person in final_team_text,person
    assert "Specialist support" not in final_team_text

    # Exact AST string literal substitution avoids touching any other Python.
    original_source_literal=ast.get_source_segment(src,pdfnode)
    assert original_source_literal and src.count(original_source_literal)==1
    new_base64=base64.b64encode(finished).decode("ascii")
    src=replace_one(src,original_source_literal,repr(new_base64))
    src=replace_one(src,
        'IBROWS_BUILD_VERSION = "2026-10-09-readmalawi-community-v137"',
        f'IBROWS_BUILD_VERSION = "{BUILD}"')
    src=replace_one(src,
        '<a href="/company-profile">Company Profile</a>\n        <a href="#community-project">Community</a>',
        '<a href="/company-profile">Company Profile</a>\n        <a href="/project-discovery">Start a Project</a>\n        <a href="#community-project">Community</a>')
    readiness='print("TEAM V136 READY: Fatuma Nyirenda IT Specialist Lead, image=embedded", flush=True)'
    src=replace_one(src,readiness,
        readiness+'\nprint("PROFILE V138 READY: all 8 staff in company PDF, project discovery navigation=on", flush=True)')
    compile(src,str(APP),"exec")
    assert src.count('href="/project-discovery"') >= 1
    APP.write_text(src,encoding="utf-8")
    print(f"V138 generated: 11-page profile, 8 team members, {len(finished)} PDF bytes, blob={git_blob()}")

if __name__=="__main__":
    main()
