"""V135 regression: unified readable fonts, all template CSS and routes."""
import ast,re
from pathlib import Path
from jinja2 import Environment
source=Path("app.py").read_text()
tree=ast.parse(source)
family="system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif"
rule=":where(button,input,select,textarea){font-family:inherit;}"
assert source.count(rule)==41
assert len(re.findall(r"font-family\s*:\s*"+re.escape(family),source))==46
families={v.strip() for v in re.findall(r"font-family\s*:\s*([^;\n}]+)",source)}
assert families=={family,"inherit","ui-monospace,SFMono-Regular,Menlo,monospace","monospace"},families
assert "fonts.googleapis" not in source
styles=[]
for node in tree.body:
    if not isinstance(node,ast.Assign) or not isinstance(node.value,ast.Constant):
        continue
    html=node.value.value
    if not isinstance(html,str) or "<style>" not in html:
        continue
    name=next(t.id for t in node.targets if isinstance(t,ast.Name))
    assert html.count("<style>")==html.count("</style>"),name
    assert html.count(rule)==html.count("<style>"),name
    assert re.search(r"font-family\s*:\s*"+re.escape(family),html),name
    Environment(autoescape=True).parse(html)
    styles.append(name)
assert len(styles)==40,len(styles)
for name in ("PUBLIC_WEBSITE_TEMPLATE","PROJECT_DISCOVERY_TEMPLATE","SERVICE_REQUEST_TEMPLATE","CONSTRUCTION_PORTFOLIO_TEMPLATE","DASHBOARD_TEMPLATE","MONITORING_TEMPLATE","LOGIN_TEMPLATE","SERVICE_PORTFOLIO_ADMIN_TEMPLATE","SERVICE_REQUESTS_ADMIN_TEMPLATE"):
    assert name in styles,name
routes=[dec for fn in tree.body if isinstance(fn,ast.FunctionDef)
        for dec in fn.decorator_list if isinstance(dec,ast.Call)
        and isinstance(dec.func,ast.Attribute) and dec.func.attr=="route"]
assert len(routes)==168,len(routes)
for text in ("CLIENT PRIVACY V132 READY","BUSINESS EMAIL V134 READY","PRICING INTEGRITY V126 READY","def validate_csrf()","WEB_GALLERY_ADMIN_PREVIEW_MAX_SIDE = 640","TYPOGRAPHY V135 READY: system_font=on template_styles=41"):
    assert text in source,text
print("PASS: 40 templates, 41 stylesheets, 46 unified font declarations, 168 routes, all key safeguards")
