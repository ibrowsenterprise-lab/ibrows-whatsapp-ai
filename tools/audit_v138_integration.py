#!/usr/bin/env python3
"""Read-only structural audit of the production IBROWS monolith.

Does NOT import or execute app.py (no DB, WhatsApp, email, or payment effects).
Reports public UI integration findings as JSON for review before a code change.
"""
import ast
import base64
import io
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = (ROOT / "app.py").read_text(encoding="utf-8")
tree = ast.parse(src)
values = {}
routes = []
for n in tree.body:
    if isinstance(n, (ast.Assign, ast.AnnAssign)):
        targets = n.targets if isinstance(n, ast.Assign) else [n.target]
        for target in targets:
            if isinstance(target, ast.Name):
                values[target.id] = n.value
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for d in n.decorator_list:
            if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                    and d.func.attr == "route" and d.args
                    and isinstance(d.args[0], ast.Constant)):
                routes.append(dict(path=d.args[0].value, handler=n.name))

def literal(key):
    node = values.get(key)
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (TypeError, ValueError, SyntaxError, RecursionError):
        return None

def hasroute(path):
    return any(r["path"] == path for r in routes)

def checks(template, needles):
    if not isinstance(template, str):
        return {"present":False}
    return {n: (n in template) for n in needles}

build = literal("IBROWS_BUILD_VERSION")
team = literal("PUBLIC_TEAM_MEMBERS") or []
photos = literal("PUBLIC_TEAM_IMAGE_B64") or {}
home = literal("PUBLIC_WEBSITE_TEMPLATE")
team_html = literal("TEAM_PAGE_TEMPLATE")
service_html = literal("SERVICE_REQUEST_TEMPLATE")
discovery_html = literal("PROJECT_DISCOVERY_TEMPLATE")
profile_html = literal("IBROWS_COMPANY_PROFILE_TEMPLATE")
report = {
    "build": build,
    "route_count":len(routes),
    "team": [{"name":m.get("name"),"role":m.get("role"),"slug":m.get("slug"),
              "photo_present":m.get("slug") in photos} for m in team],
    "homepage":checks(home,[
        'href="/team"', 'href="/company-profile"', 'href="/project-discovery"',
        'id="community-project"','readmalawi-library.onrender.com',
        '{{ team_members|length }} people']),
    "team_page":checks(team_html,["team_members", "member.slug"]),
    "service_form":checks(service_html,["csrf_token", "consent", "service_key"]),
    "discovery":checks(discovery_html,["step", "csrf_token"]),
    "profile_html":checks(profile_html,["team_members","Fatuma Nyirenda"]),
    "route_presence":{path:hasroute(path) for path in
         ("/","/team","/company-profile","/company-profile.pdf",
          "/project-discovery","/business-registration","/design-branding",
          "/photo-restoration","/landscaping","/fumigation",
          "/business-email","/privacy","/pricing","/admin/login")},
    "all_routes":routes,
    "security_code_markers":{m:m in src for m in
         ("SESSION_COOKIE_HTTPONLY=True","def validate_csrf()",
          "PRICING INTEGRITY V126 READY","WHATSAPP INTEGRITY",
          "WEB_GALLERY_ADMIN_PREVIEW_MAX_SIDE = 640")},
}

pdf_b64 = literal("IBROWS_COMPANY_PROFILE_PDF_B64")
pdfmeta = {"found":isinstance(pdf_b64,str),"pages":None,"contains_fatuma":None,
           "team_names_in_document":[],"error":None}
if isinstance(pdf_b64,str):
    try:
        from pypdf import PdfReader
        pdfdata = base64.b64decode(pdf_b64, validate=True)
        reader = PdfReader(io.BytesIO(pdfdata))
        pagetexts = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pagetexts)
        pdfmeta.update(pages=len(reader.pages),
            contains_fatuma=("fatuma" in text.casefold()),
            team_names_in_document=[m["name"] for m in team if m["name"].casefold() in text.casefold()],
            byte_size=len(pdfdata),
            page_summary=[{"page":i+1,
              "size":[round(float(page.mediabox.width)),round(float(page.mediabox.height))],
              "opening_text":pagetexts[i][:240],
              "team_members":[m["name"] for m in team if m["name"].casefold() in pagetexts[i].casefold()]}
              for i,page in enumerate(reader.pages)])
        staffpages=[(i,sum(m["name"].casefold() in t.casefold() for m in team))
                    for i,t in enumerate(pagetexts)]
        staffpages.sort(key=lambda p:p[1],reverse=True)
        if staffpages and staffpages[0][1]>=3:
            import fitz
            doc=fitz.open(stream=pdfdata,filetype="pdf")
            img=doc[staffpages[0][0]].get_pixmap(matrix=fitz.Matrix(1.1,1.1),alpha=False)
            from PIL import Image
            preview=Image.open(io.BytesIO(img.tobytes("png"))).convert("RGB")
            preview.thumbnail((1050,1300))
            buf=io.BytesIO()
            preview.save(buf,"JPEG",quality=78,optimize=True)
            (ROOT/"tools/reports/v138-existing-team-page.jpg.b64").write_text(
                base64.b64encode(buf.getvalue()).decode("ascii"), encoding="ascii")
            pdfmeta["team_page_preview"] = staffpages[0][0]+1
    except Exception as e:
        pdfmeta["error"] = f"{type(e).__name__}: {str(e)[:150]}"
report["profile_pdf"] = pdfmeta

notices=[]
if len(team)!=8 or len(photos)!=8 or any(not m["photo_present"] for m in report["team"]):
    notices.append("Public staff roster or portraits not aligned")
if isinstance(pdf_b64,str) and pdfmeta["contains_fatuma"] is False:
    notices.append("Embedded company profile PDF does not mention latest staff member Fatuma")
if not report["homepage"].get('id="community-project"',False):
    notices.append("ReadMalawi section is missing")
for path,ok in report["route_presence"].items():
    if not ok:
        notices.append(f"Expected exact route missing: {path} (check alias or methods)")
report["notices"]=notices
out=ROOT/"tools/reports/v138-integration-audit.json"
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print(f"IBROWS V138 AUDIT | build={build} | routes={len(routes)} | team={len(team)}")
print(f"Profile PDF: {pdfmeta}")
print(f"Audit notices: {notices}")
print(f"Audit stored at {out.relative_to(ROOT)}")
