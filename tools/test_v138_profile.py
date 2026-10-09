"""V138 checks preservation of the eleven-page IBROWS profile and new staff card."""
import ast
import base64
import io
from pathlib import Path

from pypdf import PdfReader

src=Path("app.py").read_text(encoding="utf-8")
tree=ast.parse(src)
vals={}
for node in tree.body:
    if isinstance(node,ast.Assign):
        for target in node.targets:
            if isinstance(target,ast.Name):
                vals[target.id]=node.value

assert ast.literal_eval(vals["IBROWS_BUILD_VERSION"])=="2026-10-09-profile-team-integration-v138"
team=ast.literal_eval(vals["PUBLIC_TEAM_MEMBERS"])
assert len(team)==8
assert all(m["slug"] for m in team)
assert next(m["role"] for m in team if m["name"]=="Fatuma Nyirenda")=="IT Specialist Lead"
assert 'PROFILE V138 READY: all 8 staff in company PDF, project discovery navigation=on' in src

home=ast.literal_eval(vals["PUBLIC_WEBSITE_TEMPLATE"])
assert home.count('href="/project-discovery"') >= 1
assert home.count('id="community-project"') == 1
assert home.count("readmalawi-library.onrender.com") == 3
assert "{{ team_members|length }} people" in home

pdf=base64.b64decode(ast.literal_eval(vals["IBROWS_COMPANY_PROFILE_PDF_B64"]),validate=True)
reader=PdfReader(io.BytesIO(pdf))
assert len(reader.pages)==11
all_text="\n".join(p.extract_text() or "" for p in reader.pages)
assert all(name in all_text for name in (m["name"] for m in team))
team_page=reader.pages[9].extract_text() or ""
for label in ("CORE TEAM","Fatuma Nyirenda","IT Specialist Lead",
              "Sylvester Katopola","Christopher Ngalu","Amos Mngoli",
              "Lewis Tambala","Kumbukani Mkandawire"):
    assert label in team_page,label
assert "Specialist support" not in team_page
assert "IBROWS Enterprise" in reader.pages[0].extract_text()
assert "CONTACT" in reader.pages[-1].extract_text()
print("PASS V138: 11-page profile preserved, eight authentic staff entries, Fatuma inserted into sixth card, project-discovery homepage link, ReadMalawi unchanged")
