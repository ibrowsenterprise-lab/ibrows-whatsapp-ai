"""Daily IBROWS visitor checks: GET/HEAD only, no customer records changed."""
from pathlib import Path
import runpy
from urllib.request import Request, build_opener, HTTPRedirectHandler, urlopen
from urllib.error import HTTPError

# Reuse the production-audited 31-page visitor script, including CSRF,
# responsive checks, hoodie stock, MSJ catalogue, admin and security headers.
runpy.run_path(str(Path(__file__).with_name("audit_v151_public.py")),run_name="__main__")

BASE="https://www.ibrowsenterprise.com"
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
client=build_opener(NoRedirect())
for route in [
    "/admin/service-portfolios",
    "/admin/service-portfolios/design-branding/media",
    "/admin/msj",
    "/admin/leads",
    "/admin/finance",
]:
    request=Request(BASE+route,headers={"User-Agent":"IBROWS-daily-audit/1.0"})
    try:
        with client.open(request,timeout=30) as response:
            status=response.status
    except HTTPError as exc:
        status=exc.code
    assert status in (302,303,307,308,401,403,405),f"Admin GET route {route} exposed HTTP {status}"
    print("PASS ADMIN ACCESS",route,status,flush=True)

# Check that media portfolio links remain public and recognizable.
request=Request(BASE+"/design-branding",headers={"User-Agent":"IBROWS-daily-audit/1.0"})
with urlopen(request,timeout=30) as result:
    html=result.read(2_000_000).decode("utf-8","replace")
assert "IBROWS MEDIA" in html, "Public Design & Branding lost IBROWS Media catalogue"
print("PASS IBROWS MEDIA PUBLIC CATALOGUE",flush=True)
print("DAILY AUDIT COMPLETED",flush=True)
