import ast,json,re
from pathlib import Path
s=Path("app.py").read_text()
tree=ast.parse(s)
names=("design_branding_portfolio","admin_service_portfolios","admin_design_media_upload","_create_website_service_request","_init_service_portfolio_tables","get_db","require_admin","is_admin_logged_in","admin_required","get_public_service_csrf","validate_public_service_csrf")
selections={}
for n in tree.body:
  if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
    if n.name in names or (n.name.startswith("admin_") and ("service_portfolio" in n.name or "design" in n.name)):
      selections[n.name]=ast.get_source_segment(s,n)[:5500]
templates={}
for n in tree.body:
  if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name):
    name=n.targets[0].id
    if name in ("DESIGN_BRANDING_PORTFOLIO_TEMPLATE","DESIGN_BRANDING_TEMPLATE","SERVICE_PORTFOLIO_TEMPLATE","PUBLIC_WEBSITE_TEMPLATE","SERVICE_PORTFOLIO_ADMIN_TEMPLATE"):
      try:
        v=ast.literal_eval(n.value)
        if isinstance(v,str):
          templates[name]={"len":len(v),"head":v[:2500],"foot":v[-3500:],
            "msj_mentions":len(re.findall(r"\bMSJ\b",v,re.I))}
      except Exception:pass
routes=[]
for n in tree.body:
 if isinstance(n,ast.FunctionDef):
  for d in n.decorator_list:
   if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr=="route":
    if d.args and isinstance(d.args[0],ast.Constant):
     route=d.args[0].value
     if any(q in str(route) for q in ("branding","service-portfolio","admin","design","shop")):
      routes.append({"route":route,"fn":n.name,"decorators":[ast.unparse(x)[:160] for x in n.decorator_list]})
locs={}
for word in ["def get_db(", "def admin_required(", "def _require_admin(", "SESSION_COOKIE","def init_db(", "DESIGN_BRANDING","BRANDING","@app.route('/design-branding'","app = Flask("]:
 locs[word]=[{"line":s[:m.start()].count("\n")+1,"excerpt":s[max(0,m.start()-300):m.start()+550]} for m in list(re.finditer(re.escape(word),s))[:3]]
report={"functions":selections,"templates":templates,"routes":routes,"snippets":locs,
        "requirements":Path("requirements.txt").read_text()}
Path("tools/msj_site_audit.json").write_text(json.dumps(report,indent=2))
print("Saved site audit",len(report["functions"]),len(routes),len(templates))
