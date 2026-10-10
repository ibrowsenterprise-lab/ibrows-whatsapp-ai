#!/usr/bin/env python3
"""Simulate complete six-step project discovery with in-memory data only.

Compiles ONLY production route functions; does not import app.py, access network,
send mail, create any actual project, or connect to a database.
"""
import ast
from pathlib import Path
from types import SimpleNamespace

source=Path("app.py").read_text(encoding="utf-8")
tree=ast.parse(source)
functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
selected=("project_discovery_create","project_discovery_step","project_discovery_complete")
class DummyForm(dict):
    def getlist(self,name):
        v=self.get(name,[])
        return v if isinstance(v,list) else ([v] if v else [])
class HttpError(Exception):
    pass
request=SimpleNamespace(method="GET",form=DummyForm(),args={})
storage={}
writes=[]
emails=[]
analyzed=[]
activity=[]
def abort(status):
    raise HttpError(status)
def clean(value,limit):
    return str(value or "").strip()[:limit]
def plist(values,**kwargs):
    if isinstance(values,str):values=[values]
    return [str(x) for x in (values or []) if x][:kwargs.get("limit_items",100)]
def csrf(token):
    if request.form.get("csrf_token")!="valid-csrf":
        raise HttpError(400)
def create_project(name,org,role,phone,email,components):
    if storage:
        raise AssertionError("Only one fixture project allowed")
    storage["demo"]={"id":90001,"reference":"IBR-TEST-0001","status":"DRAFT",
        "project_type":"WEBSITE","project_components":components,
        "answers":{},"contact_name":name}
    return "demo"
def lookup(token):return storage.get(token)
def save_answers(token,updates):
    assert token=="demo"
    writes.append(dict(updates))
    storage[token]["answers"].update(updates)
def url_for(name,**kwargs):
    return name+"?"+'&'.join(f"{k}={v}" for k,v in kwargs.items())
def redirect(url):return ("REDIRECT",url)

class FakeCursor:
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,query,params):
        assert "UPDATE project_assessments" in query and storage["demo"]["status"] in {"DRAFT","NEEDS_CLARIFICATION"}
        assert params==(90001,)
        storage["demo"]["status"]="NEW"
    def fetchone(self):return (90001,)
class FakeDb:
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return FakeCursor()
    def commit(self):pass
ns={
    "request":request,"abort":abort,
    "validate_project_discovery_csrf":csrf,
    "_project_clean":clean,"_project_list":plist,
    "_create_project_assessment":create_project,
    "_get_project_by_token":lookup,
    "_update_project_answers":save_answers,
    "_project_component_codes":lambda project:project["project_components"],
    "_project_client_clarifications":lambda project:{},
    "_project_clarification_cycle_id":lambda project:"cycle1",
    "PROJECT_INTEGRATIONS":["WhatsApp","Payment gateway"],
    "PROJECT_COMPONENTS":[("WEBSITE","Website"),("CUSTOMER_PORTAL","Customer Portal")],
    "PROJECT_DISCOVERY_PRICING":{},
    "PROJECT_DISCOVERY_TEMPLATE":"<h1>project test</h1>",
    "PROJECT_DISCOVERY_STEP_TITLES":{i:f"Step {i}" for i in range(1,7)},
    "get_project_discovery_csrf":lambda key:"valid-csrf",
    "render_template_string":lambda *a,**kwargs:("HTML",kwargs),
    "redirect":redirect,"url_for":url_for,
    "get_db":lambda:FakeDb(),
    "_project_activity_insert":lambda *args:activity.append(args),
    "analyze_project_assessment":lambda ident:analyzed.append(ident),
    "send_project_discovery_alert_email":lambda ident:emails.append(ident),
    "quote":lambda message,safe="":message,
}
for name in selected:
    fn=functions[name]
    fn.decorator_list=[]
    exec(compile(ast.Module(body=[fn],type_ignores=[]),f"<{name}>","exec"),ns)

def submit(fn,form,*args):
    request.method="POST"
    request.form=DummyForm({"csrf_token":"valid-csrf",**form})
    return fn(*args)
def assert_step_redirect(result,step):
    assert result[0]=="REDIRECT" and f"step={step}" in result[1],result
def forbidden(call):
    try:call()
    except HttpError as ex:assert ex.args[0] in (400,404),ex
    else:raise AssertionError("Invalid step was not rejected")

assert_step_redirect(submit(ns["project_discovery_create"],
        {"contact_name":"Customer Test","organisation":"Sample Co","project_components":["WEBSITE","CUSTOMER_PORTAL"]}),2)
assert len(storage)==1 and storage["demo"]["status"]=="DRAFT"
print("PASS create project locally - no external DB")
# Verify Step 6 cannot be used to bypass mandatory prior discovery answers.
last={"consent":"1","monthly_customers":"LT100","staff_users":"2_5",
      "budget_range":"RECOMMEND","timeline":"ONE_THREE","success_criteria":"Working portal for customers"}
assert_step_redirect(submit(ns["project_discovery_step"],last,"demo",6),2)
assert storage["demo"]["status"]=="DRAFT" and not emails
print("PASS Step 6 rejects premature completion and routes to first unfinished stage")

# User selected NO; verify dependent fields are cleared and not spuriously saved.
assert_step_redirect(submit(ns["project_discovery_step"],{
   "existing_system":"NO","current_setup":["Website"],"existing_manager":"PARTNER"}, "demo",2),3)
assert storage["demo"]["answers"]["current_setup"]==[]
assert storage["demo"]["answers"]["existing_manager"]==""
print("PASS Step 2 hides irrelevant existing-system values")

assert_step_redirect(submit(ns["project_discovery_step"],{
  "objective":"Create a customer booking website",
  "website_scope":"NEW","website_features":["Customer dashboard","Secure customer login"],
  "website_languages":"English and Chichewa"}, "demo",3),4)
assert storage["demo"]["answers"]["portal_implied"] is True
print("PASS Step 3 collects website and customer-portal needs")

# Switching YES > NO > YES must preserve semantics while allowing fresh input.
assert_step_redirect(submit(ns["project_discovery_step"],{
   "ai_interest":"YES","ai_features":["Answer FAQs"],"ai_action_mode":"ASSISTED"}, "demo",4),5)
assert storage["demo"]["answers"]["ai_features"]==["Answer FAQs"]
assert_step_redirect(submit(ns["project_discovery_step"],{
   "ai_interest":"NO","ai_features":["Answer FAQs"],"ai_boundaries":"do not retain"}, "demo",4),5)
assert storage["demo"]["answers"]["ai_features"]==[]
assert storage["demo"]["answers"]["ai_boundaries"]==""
assert_step_redirect(submit(ns["project_discovery_step"],{
  "ai_interest":"YES","ai_features":["Summarise requests"]}, "demo",4),5)
assert storage["demo"]["answers"]["ai_features"]==["Summarise requests"]
print("PASS Step 4 NO to YES AI preference re-selection, dependent data cleared appropriately")

assert_step_redirect(submit(ns["project_discovery_step"],{
 "api_availability":"NOT_SURE","hosting_preference":"NOT_SURE",
 "hosting_owner":"NOT_SURE","domain_status":"NOT_SURE",
 "domain_owner":"NOT_SURE","technical_admin_access":"NOT_SURE",
 "compliance_required":"NOT_SURE","integrations":["WhatsApp"],
 "integration_provider_0":"Meta"}, "demo",5),6)
assert storage["demo"]["answers"]["technical_assessment_required"] is True
print("PASS Step 5 accepts not-sure technical answers and flags further review")

# No consent cannot finalize or trigger email.
for bad in ({**last,"consent":""},{**last,"success_criteria":""},
            {**last,"budget_range":"INVALID"}):
    before=len(writes)
    forbidden(lambda b=bad:submit(ns["project_discovery_step"],b,"demo",6))
    assert len(writes)==before and not emails
print("PASS Step 6 rejects missing consent, success criteria, invalid budget")

result=submit(ns["project_discovery_step"],last,"demo",6)
assert result[0]=="REDIRECT" and "project_discovery_complete" in result[1],result
assert storage["demo"]["status"]=="NEW"
assert len(emails)==1 and len(analyzed)==1
assert emails[0]==90001 and analyzed[0]==90001
assert ns["project_discovery_complete"]("demo")[1]==200
print("PASS final submission changes status only once; one review email and one analysis")

# Previously submitted tokens cannot edit/re-submit and must redirect.
assert "project_discovery_complete" in ns["project_discovery_step"]("demo",2)[1]
print("PASS completed submission cannot reopen draft stages")
print("PASS Project Discovery step 1 through 6, guards, AI toggles and unique completion")
