#!/usr/bin/env python3
"""Isolated customer POST/GET simulation. No DB import, external messaging or network.

Compile only the selected production Flask route functions (decorators removed).
Stub persistence and uploads. Assert valid submissions generate one save request,
invalid submissions generate none, and GET remains read-only.
"""
import ast
import re
from pathlib import Path
from types import SimpleNamespace

SOURCE=Path("app.py").read_text(encoding="utf-8")
TREE=ast.parse(SOURCE)
FUNCS={n.name:n for n in TREE.body if isinstance(n,ast.FunctionDef)}
class Form(dict):
    def getlist(self, key):
        v=self.get(key, [])
        return v if isinstance(v,list) else ([v] if v else [])
class Upload:
    filename="site.jpeg"
class Request:
    method="GET"
    form=Form()
    files={"site_photo":Upload()}

BASE={"full_name":"Test Customer","phone":"+265888000000",
      "email":"test@example.invalid","consent":"1"}
CASES={
 "career_jobs_service":(
    {"support_needed":"CV_COVER","target_role":"IT Officer",
     "current_location":"Lilongwe","work_preference":"MALAWI",
     "experience_level":"MID","has_cv":"YES"},"target_role"),
 "scholarships_opportunities_service":(
    {"support_needed":"SEARCH","study_level":"MASTERS","field_of_study":"IT",
     "current_qualification":"Bachelor degree","nationality_residence":"Malawi",
     "funding_preference":"EITHER"},"field_of_study"),
 "cleaning_service":(
    {"location":"Area 25","property_type":"HOUSE","cleaning_type":"GENERAL",
     "frequency":"ONCE"},"location"),
 "design_branding_service":(
    {"service_needed":"GRAPHIC_DESIGN","design_type":"Poster",
     "platform_use":"Facebook"},"design_type"),
 "landscaping_service":(
    {"location":"Lilongwe","site_status":"NEW",
     "work_needed":"MAINTENANCE"},"site_status"),
 "construction_service":(
    {"project_type":"HOUSE","location":"Lilongwe",
     "work_category":"NEW_BUILD","project_stage":"IDEA",
     "notes":"Build a new house"},"project_stage"),
 "landscaping_preview_service":(
    {"location":"Area 25","preview_goal":"FULL_MAKEOVER",
     "style_preference":"MODERN","desired_features":["LAWN"]},"preview_goal"),
 "construction_design_service":(
    {"request_type":"CONCEPT","project_type":"HOUSE",
     "location":"Lilongwe","existing_stage":"IDEA",
     "cost_priority":"BALANCED","notes":"Prepare concept and estimate"},"request_type"),
 "construction_tender_service":(
    {"support_needed":"BOQ_PREP","tender_title":"Sample Tender",
     "tender_stage":"STARTING","boq_status":"NEED_PREP",
     "company_docs_status":"READY","notes":"Scope assessment"},"tender_stage"),
 "business_registration_service":(
    {"business_name":"Example Business","support_needed":"NEW_REGISTRATION",
     "has_valid_id":"YES","has_ppda":"NOT_APPLICABLE",
     "has_mra_tpin":"NO"},"business_name"),
 "business_email_service":(
    {"business_name":"Example Business","domain_status":"NO",
     "has_website":"NO","preferred_domain":"examplemw.com",
     "mailbox_count":"2","provider":"BASIC",
     "mailbox_names":"info, sales"},"mailbox_count"),
 "photo_restoration_service":(
    {"image_permission":"1","instructions":"Remove scratches, preserve face",
     "restoration_goals":["CLARITY"]},"image_permission"),
 "fumigation_service":(
    {"location":"Area 25","premises_type":"HOUSE",
     "pest_problem":"Cockroaches"},"pest_problem"),
 "agriculture_service":(
    {"trade_type":"SELL_TO_IBROWS","commodity":"Maize",
     "quantity":"20","quantity_unit":"50KG_BAGS",
     "location":"Lilongwe","transport_available":"NO"},"quantity"),
}
assert len(CASES)==14

req=Request()
state={"writes":[],"csrf":[]}
def clean(s, size):
    return str(s or "").strip()[:size]
def cs(key):
    state["csrf"].append(key)
    if req.form.get("csrf_token")!="dummy":
        raise ValueError("Invalid CSRF")
def capture(*args,**kwargs):
    state["writes"].append((args,kwargs))
    return "IBR-SR-TEST-0001"
def url_for(name,**params):
    return "/"+name+"?submitted="+str(params.get("submitted",""))
def renderer(key,error="",values=None):
    return ("FORM",key,error)

ns={
  "request":req,"re":re,
  "_public_service_common_fields":lambda require_email=False:("Test Customer","+265888000000","test@example.invalid"),
  "_service_clean":clean,"_service_clean_multiline":clean,
  "validate_public_service_csrf":cs,
  "_create_website_service_request":capture,
  "_render_service_request_page":renderer,
  "_service_optional_image_upload":lambda name:[],
  "_service_optional_tender_documents":lambda name:[],
  "_service_image_upload_batch":lambda name,**kwargs:[{"demo":True}]*5,
  "_service_read_image_upload":lambda upload:{"demo":True},
  "PHOTO_RESTORATION_MIN_FILES":5,
  "PHOTO_RESTORATION_MAX_FILES":30,
  "PHOTO_RESTORATION_MAX_BATCH_BYTES":10_000_000,
  "url_for":url_for,
  "redirect":lambda url:("REDIRECT",url),
}
for name in CASES:
    fn=FUNCS[name]
    fn.decorator_list=[]
    exec(compile(ast.Module(body=[fn],type_ignores=[]),"<isolated-client-route>","exec"),ns)

checks=0
for name,(valid,invalid_key) in CASES.items():
    handler=ns[name]
    state["writes"].clear();state["csrf"].clear()
    req.method="GET";req.form=Form()
    got=handler()
    assert got[1]==200,(name,"GET",got)
    assert not state["writes"] and not state["csrf"],(name,"GET caused writes")
    checks+=1

    req.method="POST";req.form=Form({**BASE,**valid,"csrf_token":"dummy"})
    got=handler()
    assert got[0]=="REDIRECT",(name,"POST VALID",got)
    assert "submitted=IBR-SR-TEST-0001" in got[1],(name,"confirmation reference",got)
    assert len(state["writes"])==1,(name,"save count",state["writes"])
    assert state["csrf"],(name,"CSRF omitted")
    args,_kwargs=state["writes"][0]
    assert len(args)>=5 and args[0] and args[4],(name,"bad capture")
    checks+=1

    state["writes"].clear()
    bad=dict(BASE,**valid,csrf_token="dummy")
    del bad[invalid_key]
    req.form=Form(bad)
    got=handler()
    assert got[1]==400,(name,"POST INVALID",got)
    assert not state["writes"],(name,"saved invalid POST")
    checks+=1

    state["writes"].clear()
    bad=dict(BASE,**valid,csrf_token="invalid")
    req.form=Form(bad)
    try:
        handler()
    except ValueError:
        assert not state["writes"],(name,"CSRF violation wrote to DB")
    else:
        raise AssertionError(f"{name} accepted an invalid CSRF token")
    checks+=1
    print("PASS",name,"GET valid POST invalid POST invalid-CSRF guard",flush=True)
print("PASS",checks,"isolated checks over",len(CASES),"customer entry workflows")
