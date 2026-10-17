"""Mock DB customer tests for category browsing and garment-specific sizing."""
from flask import Flask
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import msj_store

products=[
 dict(id=1,code="MSJ-CLASSIC",title="MSJ Classic",description="Green wordmark T-shirt",
      price_mwk=25000,garments="T-shirt",sizes="S,M,L,XL,XXL",colours="Green",
      published=True,image_revision="ab"*16),
 dict(id=2,code="MSJ-BLOCK-HOODIE",title="MSJ Block Hoodie",description="Black MSJ hoodie",
      price_mwk=50000,garments="Hoodie",sizes="S,M,L,XL,XXL",colours="Black",
      published=True,image_revision="bc"*16),
 dict(id=3,code="MSJ-BLOCK-CAP",title="MSJ Block Cap",description="Black MSJ cap",
      price_mwk=20000,garments="Cap",sizes="One Size",colours="Black",
      published=True,image_revision="cd"*16),
]
fields=("id","code","title","description","price_mwk","garments","sizes","colours","published","image_revision")
class Column:
 def __init__(self,name):self.name=name
class Cursor:
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def execute(self,sql,params=None):
  q=" ".join(sql.lower().split())
  self.rows=[];self.description=[]
  if q.startswith(("select pg_advisory","create table","create index","alter table")):return
  if q.startswith("select code, md5(image_bytes) from msj_merch_designs"):return
  if "from msj_merch_designs" in q and "select id,code,title,description,price_mwk" in q:
   self.description=[Column(k) for k in fields]
   if "where id=%s" in q:
    rows=[p for p in products if p["id"]==params[0]]
   else:rows=products
   self.rows=[tuple(p[k] for k in fields) for p in rows if "published=true" not in q or p["published"]]
   return
  raise AssertionError(q[:150])
 def fetchall(self):return list(self.rows)
 def fetchone(self):return self.rows.pop(0) if self.rows else None
class Conn:
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def cursor(self):return Cursor()
 def commit(self):pass
app=Flask("msj_categories")
app.secret_key="unit-secret"
msj_store.register_msj_store(app,lambda:Conn(),lambda code:"csrf",lambda:"adm",lambda:None,lambda f:f)
client=app.test_client()
def get(path):
 r=client.get(path)
 assert r.status_code==200,(path,r.status_code,r.data[:150])
 return r.data.decode("utf-8")
allpage=get("/msj")
for p in products:assert p["title"] in allpage
assert allpage.count("Select design")==3
tee=get("/msj?garment=T-shirt")
assert "MSJ Classic" in tee and "MSJ Block Hoodie" not in tee and "MSJ Block Cap" not in tee
assert tee.count("Select design")==1
hoodie=get("/msj?garment=Hoodie")
assert "MSJ Block Hoodie" in hoodie and "MK 50,000" in hoodie
assert "MSJ Classic" not in hoodie
cap=get("/msj?garment=Cap")
assert "MSJ Block Cap" in cap and "MK 20,000" in cap
assert "MSJ Block Hoodie" not in cap
assert 'aria-current="page"' in cap
fallback=get("/msj?garment=anything")
assert fallback.count("Select design")==3
caporder=get("/msj/design/3")
assert 'value="One Size"' in caporder
assert 'value="XXL"' not in caporder
assert "MK 20,000" in caporder
hoodieorder=get("/msj/design/2")
assert 'value="XXL"' in hoodieorder
assert 'value="One Size"' not in hoodieorder
assert "MK 50,000" in hoodieorder
shirtorder=get("/msj/design/1")
assert "MK 25,000" in shirtorder
# If no hoodie design is published, customers must see the true stock situation.
products[1]["published"]=False
empty_hoodie=get("/msj?garment=Hoodie")
assert "Hoodies temporarily out of stock" in empty_hoodie
assert "not currently available for ordering" in empty_hoodie
assert "Select design" not in empty_hoodie
index_without_hoodies=get("/msj")
assert "Hoodies (Out of stock)" in index_without_hoodies
assert "MSJ Block Hoodie" not in index_without_hoodies
assert "MSJ Classic" in index_without_hoodies and "MSJ Block Cap" in index_without_hoodies
assert client.get("/msj/design/2").status_code==404, "Unpublished hoodie should not be orderable"
products[1]["published"]=True
assert "Hoodies (Out of stock)" not in get("/msj"), "Restocked catalogue should clear old message"
print("PASS: empty hoodie catalogue clearly says out of stock; no hoodie order link")
print("PASS garment filters show exactly the right original MSJ products")
print("PASS cap orders are One Size; hoodie S-XXL; garment-specific prices match")
