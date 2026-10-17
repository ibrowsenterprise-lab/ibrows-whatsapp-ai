"""Test original MSJ hoodie/cap ZIP import without a real database or customer data."""
import io,sys,zipfile
from pathlib import Path
from flask import Flask
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import msj_store

records={}
class Cursor:
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def execute(self,sql,params=None):
  self.rows=[]
  q=" ".join(sql.lower().split())
  if q.startswith(("select pg_advisory","create table","alter table","create index")):return
  if q.startswith("select code, md5(image_bytes) from msj_merch_designs"):return
  if q.startswith("insert into msj_merch_designs"):
   code,title,description,price,garment,sizes,colour,image,mime=params
   assert mime in ("image/jpeg","image/png"),mime
   assert len(image)>1000,code
   assert garment in msj_store.MSJ_GARMENT_PRICES
   assert price==msj_store.MSJ_GARMENT_PRICES[garment]
   if garment=="Cap":assert sizes=="One Size"
   else:assert sizes=="S,M,L,XL,XXL"
   if code not in records:
    records[code]=dict(title=title,garment=garment,price=price,sizes=sizes,
                       colour=colour,bytes=len(image),published=False)
    self.rows=[(len(records),)]
   return
  raise AssertionError(q[:170])
 def fetchone(self):return self.rows.pop(0) if self.rows else None
 def fetchall(self):return self.rows
class Conn:
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def cursor(self):return Cursor()
 def commit(self):pass
app=Flask("merch_zip_test");app.secret_key="unit-only"
msj_store.register_msj_store(app,lambda:Conn(),lambda _: "csrf",lambda:"admintoken",lambda:None,lambda fn:fn)
client=app.test_client()

specs=["MSJ_Wordmark_Hoodie_Lifestyle.jpg","MSJ_Block_Hoodie.jpg",
       "MSJ_Wordmark_Cap.jpg","MSJ_Block_Cap.jpg","MSJ_Block_Tshirt.jpg"]
def image_blob(label):
 im=Image.new("RGB",(320,320),"white")
 painter=ImageDraw.Draw(im)
 for i in range(320):
  painter.line((0,i,319,i),fill=(i%255,(i*2)%255,(i*3)%255))
 painter.text((16,30),label,fill="white")
 out=io.BytesIO();im.save(out,format="JPEG",quality=90);return out.getvalue()
def zip_mock(extra=False):
 b=io.BytesIO()
 with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as z:
  for filename in specs:z.writestr(filename,image_blob(filename))
  if extra:
   z.writestr("../../outside.txt",b"not approved")
 return b.getvalue()
def post(blob,filename="MSJ_Original_Merchandise_Images.zip"):
 return client.post("/admin/msj/designs/import-merch-zip",
      data={"merch_zip":(io.BytesIO(blob),filename)},content_type="multipart/form-data")
r=post(zip_mock(extra=True))
assert r.status_code==302,r.status_code
assert len(records)==5,records
assert set(records)=={"MSJ-WORDMARK-HOODIE","MSJ-BLOCK-HOODIE",
                       "MSJ-WORDMARK-CAP","MSJ-BLOCK-CAP","MSJ-BLOCK-TSHIRT"}
assert sum(1 for p in records.values() if p["garment"]=="Hoodie")==2
assert sum(1 for p in records.values() if p["garment"]=="Cap")==2
assert records["MSJ-BLOCK-TSHIRT"]["price"]==25000
assert records["MSJ-BLOCK-CAP"]["price"]==20000
assert records["MSJ-BLOCK-HOODIE"]["price"]==50000
assert not any(p["published"] for p in records.values())
r=post(zip_mock());assert r.status_code==302
assert len(records)==5,"Duplicate upload created products"
r=post(b"not a zip")
assert r.status_code==302
assert len(records)==5
r=post(zip_mock(),"malicious.txt")
assert r.status_code==302
assert len(records)==5
assert "/admin/msj/designs/import-merch-zip" in [r.rule for r in app.url_map.iter_rules()]
print("PASS: 5 real-artwork ZIP import slots; correct MK prices and cap/apparel sizes")
print("PASS: all entries unpublished, repeat upload idempotent, path traversal ignored, invalid uploads rejected")

# V149: photo-gallery uploads need no ZIP, allow partial selection, keep stock private.
records.clear()
def direct_photos(**photos):
    payload={field:(io.BytesIO(blob), name) for field,(blob,name) in photos.items()}
    return client.post("/admin/msj/designs/import-merch-images",
                       data=payload,content_type="multipart/form-data")
empty=direct_photos()
assert empty.status_code==302
assert "Choose+at+least+one" in empty.location
assert not records
invalid=direct_photos(wordmark_cap=(b"this is not an image","fake.png"))
assert invalid.status_code==302
assert "Image+import+error" in invalid.location
assert not records
cap=direct_photos(wordmark_cap=(image_blob("Wordmark Cap"),"camera-image.jpg"))
assert cap.status_code==302
assert "MSJ-WORDMARK-CAP" in records and len(records)==1
assert records["MSJ-WORDMARK-CAP"]["sizes"]=="One Size"
assert not records["MSJ-WORDMARK-CAP"]["published"]
hoodies=direct_photos(
   wordmark_hoodie=(image_blob("Wordmark Hoodie"),"upload-1.jpg"),
   block_hoodie=(image_blob("Block Hoodie"),"upload-2.jpg"),
   block_cap=(image_blob("Block Cap"),"upload-3.jpg"),
   block_tshirt=(image_blob("Block Tee"),"upload-4.jpg"))
assert hoodies.status_code==302 and len(records)==5
assert records["MSJ-BLOCK-HOODIE"]["price"]==50000
assert records["MSJ-BLOCK-CAP"]["price"]==20000
assert records["MSJ-BLOCK-TSHIRT"]["price"]==25000
assert all(not row["published"] for row in records.values())
repeat=direct_photos(block_hoodie=(image_blob("new but duplicate"),"another.jpg"))
assert repeat.status_code==302 and len(records)==5
# Invalid second image must reject the whole request before creating the first product.
records.clear()
partly_invalid=direct_photos(
  block_hoodie=(image_blob("Valid Hoodie"),"good.jpg"),
  block_cap=(b"invalid","bad.webp"))
assert partly_invalid.status_code==302
assert not records, "Partial bad uploads must not persist earlier photos"
assert "/admin/msj/designs/import-merch-images" in [r.rule for r in app.url_map.iter_rules()]
print("PASS: individual Android-style photo uploads, correctly assigned prices, no ZIP required")
print("PASS: empty/invalid/partly-invalid uploads rejected; duplicate drafts skipped; published state unchanged")
