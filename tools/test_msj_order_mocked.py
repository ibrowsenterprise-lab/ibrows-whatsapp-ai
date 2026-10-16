"""End-to-end MSJ request using fake DB/email; never write real orders or send notifications."""
import os,sys,uuid
from pathlib import Path
from types import SimpleNamespace
from flask import Flask
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import msj_store

product={"id":22,"code":"MSJ-BLOCK-CAP","title":"MSJ Block Cap","description":"Black cap original",
 "price_mwk":20000,"garments":"Cap","sizes":"One Size","colours":"Black","published":True,
 "image_revision":"abcdef1234567890"}
order_rows={}
state={"next":1,"fail_notification_db":False,"mail":[]}
class Desc:
 def __init__(self,name):self.name=name
class Cur:
 def __init__(self):self.rows=[];self.description=[]
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def execute(self,sql,params=None):
  q=" ".join(sql.lower().split());self.rows=[];self.description=[]
  if q.startswith(("select pg_advisory_xact_lock","create table","alter table","create index")):return
  if q.startswith("select code, md5(image_bytes) from msj_merch_designs"):return
  if q.startswith("select id,code,title,description,price_mwk") and "from msj_merch_designs where id=" in q:
   names=list(product)
   self.description=[Desc(n) for n in names]
   self.rows=[tuple(product[k] for k in names)] if params[0]==22 else []
   return
  if "select count(*) from msj_merch_orders" in q:self.rows=[(0,)];return
  if "insert into msj_merch_orders" in q:
   (token,name,phone,email,location,garment,size,colour,quantity,notes,total,design_id)=params
   assert design_id==22 and garment=="Cap" and size=="One Size"
   assert total==20000*quantity
   ident=state["next"];state["next"]+=1
   order_rows[ident]=dict(token=token,name=name,phone=phone,email=email,location=location,garment=garment,
     size=size,colour=colour,quantity=quantity,notes=notes,total=total,status="NEW",ref="",alert=None)
   self.rows=[(ident,)];return
  if q.startswith("update msj_merch_orders set reference="):
   ref,ident=params;order_rows[ident]["ref"]=ref;return
  if q.startswith("update msj_merch_orders set notification_status="):
   if state["fail_notification_db"]:raise RuntimeError("Simulated alert DB failure")
   status,error,ident=params;order_rows[ident]["alert"]=status;return
  if q.startswith("select o.reference,d.title,o.garment"):
   match=[o for o in order_rows.values() if o["token"]==params[0]]
   self.rows=[(o["ref"],product["title"],o["garment"],o["colour"],o["size"],o["quantity"],o["status"]) for o in match]
   return
  raise AssertionError(q[:175])
 def fetchone(self):return self.rows.pop(0) if self.rows else None
 def fetchall(self):return list(self.rows)
class Conn:
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def cursor(self):return Cur()
 def commit(self):pass
app=Flask("msj_e2e_mock")
app.secret_key="tests-only"
msj_store.register_msj_store(app,lambda:Conn(),lambda name:"test-csrf",lambda:"admin-csrf",lambda:None,lambda f:f)
client=app.test_client()
os.environ["BREVO_API_KEY"]="test-only-key"
os.environ["NOTIFICATION_EMAIL"]="internal@example.invalid"
def mock_post(url,headers,json,timeout):
 assert "brevo" in url and json["to"][0]["email"]=="internal@example.invalid"
 state["mail"].append(json)
 return SimpleNamespace(status_code=201)
msj_store.requests.post=mock_post

def submit(**changes):
 d={"csrf_token":"test-csrf","garment":"Cap","size":"One Size","colour":"Misty purple",
    "quantity":"2","buyer_name":"MSJ Test Customer","phone":"+265123456789",
    "email":"buyer@example.invalid","location":"Lilongwe","consent":"1"}
 d.update(changes)
 return client.post("/msj/design/22",data=d,follow_redirects=False)

get=client.get("/msj/design/22")
assert get.status_code==200
assert b"MSJ Block Cap" in get.data and b"MK 20,000" in get.data
assert b"One Size" in get.data and b"XXL" not in get.data

for wrong in ({"size":"XL"},{"quantity":"31"},{"consent":"0"},{"csrf_token":"bad"}):
 r=submit(**wrong)
 assert r.status_code in (400,403),(wrong,r.status_code)
assert len(order_rows)==0

r=submit()
assert r.status_code==303,r.status_code
assert len(order_rows)==1
assert order_rows[1]["total"]==40000
assert order_rows[1]["colour"]=="Misty purple"
assert order_rows[1]["alert"]=="SENT"
assert len(state["mail"])==1
assert "MSJ-" in order_rows[1]["ref"] and "Misty purple" in state["mail"][0]["textContent"]
receipt=client.get(r.location)
assert receipt.status_code==200
assert b"Misty purple" in receipt.data and b"No payment" in receipt.data

# Simulate a notification failure *after* a committed order: customer still sees success.
state["fail_notification_db"]=True
r=submit(quantity="3",colour="Gold")
assert r.status_code==303
assert len(order_rows)==2
assert order_rows[2]["total"]==60000
assert client.get(r.location).status_code==200
assert len(state["mail"])==2
# After a validation error, retain the customer's chosen garment and size.
# Otherwise a hoodie order can silently turn into a T-shirt on resubmission.
product.update(garments="T-shirt,Hoodie,Cap", sizes="S,M,L,XL,XXL,One Size", price_mwk=20000)
r=submit(garment="Hoodie", size="M", phone="bad", quantity="2")
assert r.status_code == 400, r.status_code
html=r.data.decode("utf-8")
assert '<option value="Hoodie" selected>' in html, "Customer garment selection was lost"
assert '<option value="M" selected>' in html, "Customer size selection was lost"
assert 'name="quantity" type="number" value="2"' in html, "Customer quantity was lost"
assert len(order_rows)==2, "Invalid retry must not create an order"
print("PASS: invalid mixed-garment request keeps Hoodie, M and quantity for safe correction")

print("PASS end-to-end mocked MSJ request: size/colour/price/consent validation, order saved, admin alert, receipt")
print("PASS post-commit notification failure does not cause duplicate-order encouragement")
