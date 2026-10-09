"""V134 Business Email & Domain Setup regression tests: no live DB required."""
import ast
import re
from pathlib import Path
from types import SimpleNamespace
from jinja2 import Environment

source = Path("app.py").read_text()
tree = ast.parse(source)
functions = {n.name:n for n in tree.body if isinstance(n, ast.FunctionDef)}
routes = [(f,d) for f in functions.values() for d in f.decorator_list
          if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
          and d.func.attr == "route"]
assert len(routes) == 168, len(routes)
assert 'IBROWS_BUILD_VERSION = "2026-10-09-business-email-intake-v134"' in source
assert 'CLIENT PRIVACY V132 READY' in source
assert 'PRICING INTEGRITY V126 READY' in source
assert '"BUSINESS_EMAIL": "Business Email & Domain Setup"' in source
assert '"/business-email"' in source
assert 'No website required.' in source
assert 'quotation_only=on' in source
assert 'Start here: {IBROWS_PUBLIC_BASE_URL}/business-email' in source

template = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
   and any(isinstance(t,ast.Name) and t.id=="SERVICE_REQUEST_TEMPLATE" for t in n.targets))
discovery = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
   and any(isinstance(t,ast.Name) and t.id=="PROJECT_DISCOVERY_TEMPLATE" for t in n.targets))
assert "Only need a professional business email?" in discovery
renderer = functions["_render_service_request_page"]
config_assignment = next(n for n in renderer.body if isinstance(n,ast.Assign)
   and any(isinstance(t,ast.Name) and t.id=="config" for t in n.targets))
cfg = ast.literal_eval(config_assignment.value.value)["BUSINESS_EMAIL"]
html = Environment(autoescape=True).from_string(template).render(
    **cfg,service_key="BUSINESS_EMAIL",csrf_token="csrf-demo",
    submitted_ref="",submitted_whatsapp="",submission_summary={},
    whatsapp_url="",error="",values={},packages=[],pricing_note="",
    gallery_previews=[],year=2026,url_for=lambda name,**kwargs:"/"+name
)
for token in ('name="preferred_domain"','name="mailbox_count"','name="provider"',
              'name="domain_status"','name="has_website"','name="consent"',
              'value="csrf-demo"','Request Business Email Quotation'):
    assert token in html,token
assert "No website required" in html
assert "MK160,000" not in html  # Quote must be approved after supplier costs are confirmed.

fn = functions["business_email_service"]
fn.decorator_list=[]
forms = {
 "business_name":"ABC Trading", "domain_status":"NO", "has_website":"NO",
 "preferred_domain":"abctrading.com", "mailbox_count":"3",
 "provider":"BASIC","mailbox_names":"info, sales, director",
 "full_name":"Test Client","phone":"+265888000123","email":"client@example.com"
}
request=SimpleNamespace(method="POST",form=dict(forms))
saved=[]
ns=dict(request=request,re=re,
 validate_public_service_csrf=lambda key: None,
 _public_service_common_fields=lambda require_email:("Test Client","+265888000123","client@example.com"),
 _service_clean=lambda value,maxlen:str(value or "").strip()[:maxlen],
 _service_clean_multiline=lambda value,maxlen:str(value or "").strip()[:maxlen],
 _create_website_service_request=lambda *args: (saved.append(args) or "IBR-SR-2026-0099"),
 _render_service_request_page=lambda key,error="",values=None:("FORM",key,error),
 url_for=lambda name,**kw:"/business-email?submitted="+kw.get("submitted",""),
 redirect=lambda url:("REDIRECT",url))
exec(compile(ast.Module(body=[fn],type_ignores=[]),"<route>","exec"),ns)
assert ns["business_email_service"]()[0]=="REDIRECT"
assert saved[0][0]=="BUSINESS_EMAIL" and saved[0][-1]["mailbox_count"]==3
assert saved[0][-1]["quotation_required"] is True
assert saved[0][-1]["domain_registered_to_client"] is True
for field,bad in [("preferred_domain","https://abc.com"),("preferred_domain","abc@site.com"),
                  ("mailbox_count","21"),("provider","UNLISTED"),("has_website","")]:
    request.form={**forms,field:bad}
    assert ns["business_email_service"]()[1]==400,field
    assert len(saved)==1,field
request.method="GET"
assert ns["business_email_service"]()[1]==200
print("PASS: V134 business email questionnaire, routes, website/app links, safe request creation, five invalid cases")
