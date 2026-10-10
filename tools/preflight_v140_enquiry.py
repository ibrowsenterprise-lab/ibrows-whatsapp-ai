#!/usr/bin/env python3
"""Read-only inventory of real production service-form package requirements."""
import urllib.request
from html.parser import HTMLParser
BASE="https://www.ibrowsenterprise.com"
paths=["/business-registration","/fumigation","/agriculture","/cleaning","/landscaping/enquiry","/construction/enquiry","/business-email","/scholarships-opportunities","/career-jobs","/photo-restoration","/design-branding/enquiry"]
class Scan(HTMLParser):
    def __init__(self):super().__init__();self.fields={};self.choices=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in {"input","select","textarea"} and "name" in a:
            self.fields[a["name"]]=self.fields.get(a["name"],0)+1
            if a["name"]=="package_choice":
                self.choices.append(a.get("value",""))
for path in paths:
    try:
        req=urllib.request.Request(BASE+path,headers={"User-Agent":"IBROWS-ReadOnly-Scan/1.0"})
        with urllib.request.urlopen(req,timeout=35) as resp:html=resp.read(500000).decode("utf8","replace")
        p=Scan();p.feed(html)
        print("PREFLIGHT",path,
              "package_field",p.fields.get("package_choice",0),
              "choices",",".join(p.choices)[:100],
              "csrf",p.fields.get("csrf_token",0),
              "consent",p.fields.get("consent",0),flush=True)
    except Exception as e:
        print("ERROR",path,type(e).__name__,str(e)[:100],flush=True)
