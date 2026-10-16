"""Verify MSJ's original-image sheet importer without a production database."""
import io
from flask import Flask
from PIL import Image
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import msj_store

rows = {}
class Cursor:
    def __enter__(self):return self
    def __exit__(self,*exc):pass
    def execute(self,query,params=None):
        self.value = None
        if "INSERT INTO msj_merch_designs" in query:
            code,title,desc,price,colours,asset=params
            if code not in rows:
                rows[code]=(title,price,asset)
                self.value=(len(rows),)
        elif query.lstrip().upper().startswith(("SELECT PG_ADVISORY", "CREATE TABLE","CREATE INDEX","ALTER TABLE")):
            pass
        else:
            raise AssertionError(query[:100])
    def fetchone(self):return self.value
class Conn:
    def __enter__(self):return self
    def __exit__(self,*exc):pass
    def cursor(self):return Cursor()
    def commit(self):pass
app=Flask("msj_import_test")
app.secret_key="test"
msj_store.register_msj_store(app,lambda:Conn(),lambda purpose:"usercsrf",
                              lambda:"admincsrf",lambda:None,lambda fn:fn)
client=app.test_client()

def sheet(cols,rows_count,width,height):
    image=Image.new("RGB",(width,height))
    palette=["#014a30","#e8d7b2","#242526","#052b55","#b94e59"]
    from PIL import ImageDraw
    pen=ImageDraw.Draw(image)
    n=0
    for y in range(rows_count):
        for x in range(cols):
            pen.rectangle((x*width//cols,y*height//rows_count,
                (x+1)*width//cols-1,(y+1)*height//rows_count-1),fill=palette[n%len(palette)])
            n+=1
    output=io.BytesIO()
    image.save(output,format="PNG")
    output.seek(0)
    return output

def post_three():
    return client.post("/admin/msj/designs/import-sheets",data={
        "three":(sheet(3,1,900,600),"real-shirt-sheet.png")
    },content_type="multipart/form-data")
r=post_three()
assert r.status_code==302
assert set(rows)=={"MSJ-CLASSIC","MSJ-SCRIPT","MSJ-MODERN"}
assert all(p[1]==25000 and len(p[2])>1000 for p in rows.values())
assert post_three().status_code==302
assert len(rows)==3, "Duplicate import must not create repeated products"

r=client.post("/admin/msj/designs/import-sheets",data={
    "four_a":(sheet(2,2,800,800),"shirt-designs-a.png"),
    "four_b":(sheet(2,2,800,800),"shirt-designs-b.png"),
},content_type="multipart/form-data")
assert r.status_code==302
assert len(rows)==11,len(rows)
for code,(_,price,asset) in rows.items():
    assert price==25000 and asset[:3]==b"\xff\xd8\xff",code
assert set(rows)=={"MSJ-"+s.upper().replace(" ","-") for s in [
    "Classic","Script","Modern","Circle","Handwritten","Label","Retro Flow",
    "Varsity","Stencil","Motion","Vertical"]}
print("PASS: original 3+4+4 design sheets imported as 11 distinct unpublished image-based products; duplicates ignored")
