"""Read-only, live IBROWS production audit. GET only: never submits customer data."""
import time
import os
from html.parser import HTMLParser
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, unquote

BASE = "https://www.ibrowsenterprise.com"
PAGES = [
 "/", "/career-jobs", "/scholarships-opportunities", "/cleaning",
 "/design-branding", "/design-branding/enquiry", "/landscaping",
 "/landscaping/enquiry", "/landscaping/preview",
 "/construction", "/construction/enquiry", "/construction/design-quote",
 "/construction/tender-boq-support", "/business-registration",
 "/business-email", "/photo-restoration", "/fumigation", "/fumigation/gallery",
 "/agriculture", "/car-wash", "/company-profile", "/team", "/pricing",
 "/project-discovery", "/privacy", "/terms", "/data-deletion",
 "/msj", "/msj?garment=T-shirt", "/msj?garment=Cap",
 "/msj?garment=Hoodie",
]
ENQUIRY_FORMS = {
 "/career-jobs", "/scholarships-opportunities", "/cleaning",
 "/design-branding/enquiry", "/landscaping/enquiry", "/landscaping/preview",
 "/construction/enquiry", "/construction/design-quote", "/construction/tender-boq-support",
 "/business-registration", "/business-email", "/photo-restoration", "/fumigation", "/agriculture"
}
opener = build_opener()
class Parse(HTMLParser):
 def __init__(self):
  super().__init__()
  self.forms = 0
  self.inputs = set()
  self.links = set()
  self.viewport = False
  self.title = []
  self._in_title = False
 def handle_starttag(self, tag, attrs):
  d = dict(attrs)
  if tag == "meta" and d.get("name") == "viewport": self.viewport = True
  if tag == "form": self.forms += 1
  if tag in ("input", "textarea", "select") and d.get("name"): self.inputs.add(d["name"])
  if tag == "a" and d.get("href"): self.links.add(d["href"])
  if tag == "title": self._in_title = True
 def handle_endtag(self, tag):
  if tag == "title": self._in_title = False
 def handle_data(self, data):
  if self._in_title: self.title.append(data)

def fetch(path):
 url=BASE + path
 last=None
 for i in range(3):
  try:
   req=Request(url,headers={"User-Agent":"IBROWS-V151-Visitor-ReadOnly/1.0","Accept":"text/html"})
   with opener.open(req,timeout=30) as resp:
    return resp.status,resp.read(1_600_000).decode("utf-8","replace"),{k.lower():v for k,v in resp.headers.items()}
  except HTTPError as exc:
   return exc.code,exc.read(10_000).decode("utf-8","replace"),{k.lower():v for k,v in exc.headers.items()}
  except (URLError,TimeoutError,OSError) as exc:
   last=str(exc)
   if i<2:time.sleep(4)
 raise RuntimeError(last)

# A PR audit tests the currently deployed website. New headers are required
# on main only, after waiting for Render auto-deploy to finish.
require_nosniff = os.getenv("GITHUB_REF") == "refs/heads/main"
if require_nosniff:
 for attempt in range(24):
  try:
   _, _, probe_headers = fetch("/")
   if probe_headers.get("x-content-type-options", "").lower()=="nosniff":
    print("PASS production security header ready",flush=True)
    break
  except Exception:
   pass
  print("Waiting for production deployment to serve security headers",attempt+1,flush=True)
  time.sleep(6)

# HTTP header field names are case-insensitive.
assert {k.lower():v for k,v in {"X-Content-Type-Options":"nosniff"}.items()}["x-content-type-options"] == "nosniff"
errors=[];warnings=[];checked=0
def check(condition,msg):
 if not condition:errors.append(msg)
for path in PAGES:
 try:
  status,body,headers=fetch(path)
  if status!=200:
   errors.append(f"{path}: HTTP {status}")
   print("FAIL",path,"HTTP",status,flush=True)
   continue
  p=Parse();p.feed(body)
  check(p.viewport,f"{path} missing responsive viewport")
  check(bool("".join(p.title).strip()),f"{path} missing document title")
  if path in ENQUIRY_FORMS:
   check(p.forms>0 and "csrf_token" in p.inputs and "consent" in p.inputs,
         f"{path} missing enquiry form, CSRF or consent")
  if path=="/project-discovery":
   check(p.forms>0 and "contact_name" in p.inputs and "project_components" in p.inputs,
         "/project-discovery missing multi-stage customer intake")
  if path=="/design-branding":
   check(any("/msj" in x for x in p.links),"/design-branding missing MSJ collection link")
  if path=="/msj":
   check("Mulungu Si Jemusi" in body and "/msj/design/" in body,
         "/msj missing published merchandise designs")
  if path=="/msj?garment=Hoodie":
   check("Hoodies temporarily out of stock" in body,
         "Hoodie category lacks out-of-stock notice")
   check("/msj/design/" not in body, "Hoodie category offers item orders while out of stock")
  if path=="/msj?garment=Cap":
   check("MSJ Wordmark Cap" in body and "MK 20,000" in body,
         "Cap listing or MK20,000 price missing")
  if path=="/msj?garment=T-shirt":
   check("MK 25,000" in body, "T-shirt price missing")
  if path=="/team":
   check("Fatuma Nyirenda" in body, "/team missing IT lead")
  if path=="/":
   check("ReadMalawi" in body and "Start a Project" in body,
         "Home missing community or project discovery")
  if headers.get("x-content-type-options","").lower()!="nosniff":
   msg=f"{path}: X-Content-Type-Options nosniff missing"
   if require_nosniff: errors.append(msg)
   else: warnings.append(msg)
  checked+=1
  print("PASS",path,"HTTP",status,"forms",p.forms,flush=True)
 except Exception as exc:
  errors.append(f"{path}: {type(exc).__name__}: {str(exc)[:110]}")
  print("FAIL",path,type(exc).__name__,str(exc)[:110],flush=True)

# Anonymous access checks do not follow a login redirect into a privileged admin.
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self, req, fp, code, msg, headers, newurl):return None
anonymous=build_opener(NoRedirect())
for path in ["/admin/msj","/admin/leads","/admin/finance","/admin/projects"]:
 try:
  req=Request(BASE+path,headers={"User-Agent":"IBROWS-V151-Visitor-ReadOnly/1.0"})
  try:
   with anonymous.open(req,timeout=25) as r:status=r.status
  except HTTPError as ex:status=ex.code
  check(status in (302,303,307,308,401,403),f"{path}: anonymous HTTP {status} (should not expose admin)")
  print(("PASS" if status in (302,303,307,308,401,403) else "FAIL"),"anon",path,"HTTP",status,flush=True)
 except Exception as exc:
  errors.append(f"{path}: anonymous check error {type(exc).__name__}: {str(exc)[:100]}")
# Safe 404 check: non-existing product cannot become an order form.
try:
 status,_,_=fetch("/msj/design/99999999")
 check(status==404,f"Unknown MSJ product should 404 but was HTTP {status}")
 print("PASS" if status==404 else "FAIL","nonexistent MSJ product",status,flush=True)
except Exception as exc: errors.append(f"Unknown MSJ product failed: {str(exc)[:100]}")
print("V151 RESULTS", "pages_checked",checked,"of",len(PAGES),
      "errors",len(errors),"warnings",len(warnings),flush=True)
for e in errors:print("ERROR",e,flush=True)
for w in warnings[:5]:print("WARNING",w,flush=True)
if errors:raise SystemExit(1)
