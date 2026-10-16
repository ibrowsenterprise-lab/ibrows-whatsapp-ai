"""MSJ admin draft-first review regression; all database work stays mocked."""
import sys
from pathlib import Path
from flask import Flask
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import msj_store

products=[
 dict(id=1,code="MSJ-CLASSIC",title="MSJ Classic",description="Original shirt",price_mwk=25000,
      garments="T-shirt",sizes="S,M,L,XL,XXL",colours="Green",published=True,image_revision="a"*32),
 dict(id=12,code="MSJ-BLOCK-CAP",title="MSJ Block Cap",description="Real cap",price_mwk=20000,
      garments="Cap",sizes="One Size",colours="Black",published=False,image_revision="b"*32),
 dict(id=13,code="MSJ-WORDMARK-HOODIE",title="MSJ Wordmark Hoodie",description="Real hoodie",
      price_mwk=50000,garments="Hoodie",sizes="S,M,L,XL,XXL",colours="Green",
      published=False,image_revision="c"*32)
]
product_fields=("id","code","title","description","price_mwk","garments","sizes","colours","published","image_revision")
class Column:
 def __init__(self,name):self.name=name
class Cursor:
 def __init__(self):self.rows=[];self.description=[]
 def __enter__(self):return self
 def __exit__(self,*exc):return False
 def execute(self,sql,params=None):
  q=" ".join(sql.lower().split())
  self.rows=[];self.description=[]
  if q.startswith(("select pg_advisory_xact_lock","create table if not exists","alter table msj_merch_orders","create index if not exists")):return
  if q.startswith("select code, md5(image_bytes) from msj_merch_designs"):return
  if "from msj_merch_orders o" in q and "join msj_merch_designs d" in q:
   self.description=[Column(v) for v in ("id","reference")]
   return
  if "from msj_merch_designs" in q and "select id,code,title,description" in q:
   self.description=[Column(k) for k in product_fields]
   self.rows=[tuple(p[k] for k in product_fields) for p in products]
   return
  raise AssertionError(q[:180])
 def fetchall(self):return list(self.rows)
 def fetchone(self):return self.rows.pop(0) if self.rows else None
class Conn:
 def __enter__(self):return self
 def __exit__(self,*exc):return False
 def cursor(self):return Cursor()
 def commit(self):pass
app=Flask("msj_admin_reviews")
app.secret_key="test-only"
msj_store.register_msj_store(app,lambda:Conn(),lambda purpose:"csrf",
    lambda:"admin-csrf",lambda:None,lambda f:f)
client=app.test_client()
r=client.get("/admin/msj")
assert r.status_code==200,(r.status_code,r.data[:600])
html=r.data.decode("utf-8")
assert html.index("<strong>MSJ Wordmark Hoodie</strong>") < html.index("<strong>MSJ Block Cap</strong>") < html.index("<strong>MSJ Classic</strong>")
assert "2 drafts" in html and "1 published" in html
assert "1 T-shirt designs" in html and "1 hoodie designs" in html and "1 cap designs" in html
assert 'href="#merch-import-title"' in html, "Mobile hoodie/cap import shortcut missing"
assert "Choose at least one original MSJ design sheet before importing." in html
assert "Publish All Drafts (2)" in html
assert html.count("Draft — needs approval")==2
assert "Review each image, garment type, sizes and price" in html
assert "MK 50,000" in html and "MK 20,000" in html and "MK 25,000" in html

products[1]["published"]=products[2]["published"]=True
r=client.get("/admin/msj")
assert r.status_code==200
html=r.data.decode("utf-8")
assert "Publish All — No Drafts" in html
assert "3 published" in html and "0 drafts" in html
assert "Draft — needs approval" not in html
print("PASS: MSJ mobile admin sorts unpublished products first, newest drafts above old T-shirts")
print("PASS: draft count, price, explicit review cues and safe no-draft state")
