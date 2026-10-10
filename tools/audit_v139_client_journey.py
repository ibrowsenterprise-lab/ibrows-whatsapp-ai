#!/usr/bin/env python3
"""Read-only code audit of client-facing IBROWS routes and forms. Never executes app.py."""
import ast
import json
import re
from pathlib import Path
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parent.parent
SRC=(ROOT/"app.py").read_text(encoding="utf-8")
tree=ast.parse(SRC)
assigns={}
funcs={}
routes=[]
for node in tree.body:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t,ast.Name):
                assigns[t.id]=node.value
    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
        funcs[node.name]=node
        for dec in node.decorator_list:
            if (isinstance(dec,ast.Call) and isinstance(dec.func,ast.Attribute)
                and dec.func.attr=="route" and dec.args
                and isinstance(dec.args[0],ast.Constant)):
                path=dec.args[0].value
                methods=["GET"]
                for kw in dec.keywords:
                    if kw.arg=="methods":
                        try: methods=ast.literal_eval(kw.value)
                        except (ValueError,TypeError): methods=["unknown"]
                routes.append({"path":path,"methods":methods,"function":node.name,
                               "line":node.lineno})
route_by_fn={r["function"]:r for r in routes}
selected_words=("registration","design","restoration","fumigation","cleaning","landscap",
                "agricultur","project-discovery","discovery","scholarship","career","quotation",
                "construction","service-request","service_request","business-email")
selected=[r for r in routes if any(w in str(r["path"]).lower() for w in selected_words)]

class FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms=[]
        self.current=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="form":
            self.current={"method":a.get("method","GET"),"action":a.get("action"),
                          "enctype":a.get("enctype"),
                          "fields":[],"submit_buttons":[]}
            self.forms.append(self.current)
        if self.current is None:return
        if tag in ("input","select","textarea"):
            self.current["fields"].append({"name":a.get("name"),"type":a.get("type",tag),
              "required":"required" in a,"accept":a.get("accept"),"hidden":a.get("type")=="hidden"})
        if tag=="button":
            self.current["submit_buttons"].append(a.get("type"))
    def handle_endtag(self,tag):
        if tag=="form":self.current=None

templates={}
for name,expr in assigns.items():
    if not name.endswith("TEMPLATE") and not name.endswith("_HTML"):
        continue
    try: s=ast.literal_eval(expr)
    except (ValueError,TypeError):continue
    if not isinstance(s,str) or "<form" not in s.lower():continue
    f=FormParser()
    f.feed(s)
    templates[name]={"length":len(s),"forms":f.forms,
        "has_save_confirmation":bool(re.search(r"submitted|successfully|received|saved|reference number",s,re.I)),
        "has_csrf":("csrf_token" in s or "_csrf" in s),
        "has_explicit_label":('<label' in s.lower()),
        "has_status_area":("aria-live" in s or 'role="status"' in s),
        "has_mobile_viewport":("name=\"viewport\"" in s or "name='viewport'" in s),
        "external_links":sorted(set(re.findall(r'href="(https?://[^"]+)"',s)))[:10],
    }

handlers={}
for r in selected:
    node=funcs[r["function"]]
    raw=ast.get_source_segment(SRC,node) or ""
    # Public source snippets, not runtime values. Trim to only relevant code.
    handlers[r["function"]]={
       "route":r["path"],"methods":r["methods"],"line":r["line"],
       "code_excerpt":raw[:6800],
       "has_csrf":("csrf" in raw.lower()),
       "has_database_write":any(q in raw for q in ("commit(", "_create_website_service_request","_create_project", "INSERT INTO")),
       "has_file_check":any(q in raw.lower() for q in ("upload","file","multipart")),
       "has_success_redirect":("redirect(" in raw),
       "has_validation":("error" in raw.lower() or "400" in raw),
    }
report={
  "build": ast.literal_eval(assigns["IBROWS_BUILD_VERSION"]),
  "route_count":len(routes),"relevant_routes":selected,
  "templates":templates,"handlers":handlers,
  "global_keywords":{k:SRC.count(k) for k in (
    "validate_public_service_csrf","_create_website_service_request",
    "POST","consent","upload","Project Discovery","SERVICE_REQUEST_TEMPLATE")},
}
out=ROOT/"tools/reports/v139-journey.json"
out.parent.mkdir(exist_ok=True,parents=True)
out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print("REPORT",out,"size",out.stat().st_size,"routes",len(routes),
      "selected",len(selected),"forms",sum(len(v["forms"]) for v in templates.values()))
for r in selected:print("ROUTE",r["path"],",".join(r["methods"]),r["function"])
