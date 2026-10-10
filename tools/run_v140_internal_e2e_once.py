#!/usr/bin/env python3
"""Exactly ONE authorized IBROWS INTERNAL QA customer enquiry on the official site.

A production record and a normal internal alert will be created.
No payments, domain purchases, jobs, invoices, other integrations, WhatsApp, or customer emails.
Use only the company-owned, publicly advertised test contact.
Do not retry POST on failure. Does not import or modify app.py.
"""
from html.parser import HTMLParser
from urllib import parse, request, error
import re
import sys

BASE="https://www.ibrowsenterprise.com"
PATH="/business-email"
QA_MARKER="IBROWS QA TEST - DO NOT SERVICE"
QA_EMAIL="info@ibrowsenterprise.com"  # public company contact
QA_PHONE="+265882242594"  # IBROWS's own WhatsApp Business number
QA_BUSINESS="IBROWS INTERNAL WEBSITE QA (NOT A CUSTOMER)"
TEST_DESCRIPTION=("INTERNAL IBROWS E2E TEST 2026-10-10. "
                  "This is NOT a genuine customer or request for domain or mailbox creation. "
                  "Do not quote, invoice, contact or perform any work. "
                  "The sole purpose is to verify form save + admin notification; close as test.")

class FormReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields=[]
    def handle_starttag(self,tag,attrs):
        if tag not in {"input","select","textarea"}:return
        a=dict(attrs)
        self.fields.append(a)

def get(path):
    req=request.Request(BASE+path,method="GET",headers={"User-Agent":"IBROWS-Authorized-E2E-Test/1.0"})
    with request.urlopen(req,timeout=35) as res:
        if res.status!=200:raise RuntimeError("GET unsuccessful")
        return res.read(650_000).decode("utf-8","replace")

html=get(PATH)
p=FormReader();p.feed(html)
def inputs(name):return [x for x in p.fields if x.get("name")==name]
csrf=inputs("csrf_token")
assert len(csrf)==1 and len(csrf[0].get("value",""))>=20,"No valid CSRF input"
assert inputs("consent") and inputs("full_name") and inputs("phone") and inputs("email")
assert inputs("business_name") and inputs("mailbox_count") and inputs("domain_status")
if inputs("package_choice"):
    print("STOP: This service includes paid package selection; did not submit any test",flush=True)
    sys.exit(3)
if "IBROWS" not in html:
    raise AssertionError("Unexpected domain content")
# Confirm read-only preflight before any production write.
print("PREFLIGHT PASS: official website form and security token available, no paid package field",flush=True)

form={
    "csrf_token":csrf[0]["value"],"fax_number":"",
    "full_name":QA_MARKER,"phone":QA_PHONE,"email":QA_EMAIL,
    "business_name":QA_BUSINESS,
    "domain_status":"NO","has_website":"NO",
    "preferred_domain":"","mailbox_count":"1",
    "provider":"UNSURE","mailbox_names":"qa-only (not for creation)",
    "notes":TEST_DESCRIPTION,
    "consent":"1",
}
assert "INTERNAL" in form["business_name"] and "QA TEST" in form["full_name"]
assert form["email"].endswith("@ibrowsenterprise.com")
payload=parse.urlencode(form).encode("utf-8")
class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        return None
opener=request.build_opener(NoRedirect())
req=request.Request(BASE+PATH,data=payload,method="POST",headers={
    "Content-Type":"application/x-www-form-urlencoded",
    "User-Agent":"IBROWS-Authorized-E2E-Test/1.0",
    "Origin":BASE,
    "Referer":BASE+PATH,
})
# SINGLE POST: never retry; the service may commit even if the network times out.
try:
    with opener.open(req,timeout=50) as res:
        status, location=res.status,res.headers.get("Location","")
except error.HTTPError as ex:
    status, location=ex.code,ex.headers.get("Location","")
    if status not in (301,302,303):
        print("POST rejected HTTP",status,"(no retry)",flush=True)
        sys.exit(2)
if status not in (301,302,303):
    print("UNEXPECTED POST RESPONSE",status,"(no retry)",flush=True)
    sys.exit(2)
dest=parse.urljoin(BASE+PATH,location)
url=parse.urlsplit(dest)
assert url.scheme=="https" and url.netloc=="www.ibrowsenterprise.com"
qs=parse.parse_qs(url.query)
reference=(qs.get("submitted") or [""])[0]
assert re.fullmatch(r"IBR-SR-[0-9]{4}-[0-9]{4,}",reference),f"Invalid reference returned: {reference!r}"
# GET confirmation; no additional records.
confirmation=get(url.path+"?"+url.query)
if reference not in confirmation:
    raise AssertionError("Reference absent from confirmation page")
print(f"SUBMISSION PASS: one internal QA enquiry created, reference={reference}, HTTP redirect={status}",flush=True)
print("CONFIRMATION PASS: generated request reference displayed on the official site",flush=True)
print("NO PAYMENTS / NO WHATSAPP / NO JOB APPLICATION / NO ADDITIONAL POSTS",flush=True)
