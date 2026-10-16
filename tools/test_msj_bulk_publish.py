"""Offline Flask regression for the MSJ Publish All feature; no live DB writes."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

from flask import Flask, abort
import msj_store

products=[
    {"id":1,"published":True,"price_mwk":25000,"image_bytes":b"image","title":"Classic","garments":"T-shirt","sizes":"S,M,L"},
    {"id":2,"published":False,"price_mwk":25000,"image_bytes":b"image","title":"Script","garments":"T-shirt","sizes":"S,M,L"},
    {"id":3,"published":False,"price_mwk":25000,"image_bytes":b"image","title":"Modern","garments":"T-shirt","sizes":"S,M,L"},
    {"id":4,"published":False,"price_mwk":0,"image_bytes":b"","title":"","garments":"","sizes":""}
]
calls=[]
class Cursor:
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,sql,params=None):
        query=" ".join(sql.lower().split())
        calls.append(query)
        if query.startswith("select pg_advisory_xact_lock"):self.rows=[];return
        if query.startswith(("create table if not exists","create index if not exists","alter table msj_merch_orders")):self.rows=[];return
        if query.startswith("select count(*) from msj_merch_designs where published=false"):
            self.rows=[(sum(1 for x in products if not x["published"]),)]
            return
        if query.startswith("update msj_merch_designs set published=true"):
            elig=[p for p in products if not p["published"] and p["price_mwk"]>0 and len(p["image_bytes"])>0 and
                  p["title"].strip() and p["garments"].strip() and p["sizes"].strip()]
            for p in elig:p["published"]=True
            self.rows=[(p["id"],) for p in elig];return
        raise AssertionError(f"Unexpected SQL: {query[:200]}")
    def fetchone(self):return self.rows.pop(0) if self.rows else None
    def fetchall(self):r=self.rows;self.rows=[];return r
class Conn:
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def cursor(self):return Cursor()
    def commit(self):pass

csrf_calls=[]
def check_csrf():
    from flask import request
    csrf_calls.append(request.form.get("csrf_token"))
    if request.form.get("csrf_token")!="offline-test":abort(403)

def admin_required(fn):return fn
app=Flask("msj_bulk_test")
app.secret_key="only-for-unit-tests"
msj_store.register_msj_store(app,lambda:Conn(),lambda purpose:"offline",
                             lambda:"offline-test",check_csrf,admin_required)
client=app.test_client()

# No GET operation is allowed to publish items. CSRF rejects missing/incorrect token.
assert client.get("/admin/msj/designs/publish-all").status_code==405
assert client.post("/admin/msj/designs/publish-all").status_code==403
assert sum(p["published"] for p in products)==1

resp=client.post("/admin/msj/designs/publish-all",data={"csrf_token":"offline-test"})
assert resp.status_code==302
assert "Published+2+of+3" in resp.location or "Published%202%20of%203" in resp.location,resp.location
assert [p["published"] for p in products]==[True,True,True,False]
assert "MSJ" in resp.location
assert len([x for x in calls if x.startswith("update msj_merch_designs set published=true")])==1

# Idempotency: the incomplete item is still not published on a repeated request.
resp=client.post("/admin/msj/designs/publish-all",data={"csrf_token":"offline-test"})
assert resp.status_code==302
assert [p["published"] for p in products]==[True,True,True,False]
assert "Published+0+of+1" in resp.location or "Published%200%20of%201" in resp.location,resp.location

# Now fix the invalid draft: one more bulk action publishes exactly one item.
products[3].update(price_mwk=25000,image_bytes=b"valid",title="Circle",garments="T-shirt",sizes="S,M,L")
resp=client.post("/admin/msj/designs/publish-all",data={"csrf_token":"offline-test"})
assert resp.status_code==302
assert all(x["published"] for x in products)
assert "Published+1+MSJ" in resp.location or "Published%201%20MSJ" in resp.location,resp.location
resp=client.post("/admin/msj/designs/publish-all",data={"csrf_token":"offline-test"})
assert resp.status_code==302
assert "already+published" in resp.location or "already%20published" in resp.location
assert len(csrf_calls)==5
print("PASS MSJ: bulk publish changes drafts only, counts accurately, skips incomplete, idempotent and rejects missing CSRF")
