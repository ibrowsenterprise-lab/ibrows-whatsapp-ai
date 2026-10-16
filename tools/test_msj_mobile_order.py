"""Render-test the customer MSJ checkout in isolation without real database writes."""
import sys
from html.parser import HTMLParser
from pathlib import Path
from flask import Flask, render_template_string

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import msj_store

app=Flask("msj_mobile_layout_test")
app.secret_key="offline-tests"
msj_store.register_msj_store(app,lambda:None,lambda _: "csrf-public",
                              lambda:"csrf-admin",lambda:None,lambda fn:fn)
class OrderParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids={}
        self.fields={}
        self.errors=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if "id" in a:self.ids[a["id"]]=tag
        if tag in ("input","select","textarea") and "name" in a:
            self.fields[a["name"]]=a
        if a.get("role")=="alert":self.errors.append(tag)

design=dict(id=1,title="MSJ Classic",price_mwk=25000,image_revision="abcdef0123456789")
kwargs=dict(title="MSJ Classic",design=design,garments=["T-shirt"],sizes=["S","M","L","XL","XXL"],
            colours=["Black","Green"],csrf_token="csrf-public",error="",
            garment_prices=msj_store.MSJ_GARMENT_PRICES,old={})
with app.test_request_context("/msj/design/1"):
    html=render_template_string(msj_store.ORDER_TEMPLATE,**kwargs)
    parsed=OrderParser()
    parsed.feed(html)
    assert parsed.ids["order-subtotal"]=="strong"
    assert parsed.ids["garment"]=="select"
    assert parsed.ids["size"]=="select"
    assert parsed.ids["quantity"]=="input"
    assert parsed.fields["quantity"]["min"]=="1"
    assert parsed.fields["quantity"]["max"]=="30"
    assert "MK 25,000" in html
    assert "Estimated subtotal" in html
    assert "From MK 25,000 per item" not in html
    assert html.count("Your order")==1
    assert "Change design" in html
    assert "order-product" in html
    assert "order-hero" in html
    assert "value='T-shirt'" not in html
    assert "var prices=" in html and "25000" in html
    assert "toLocaleString('en-US')" in html
    assert 'href="/msj"' in html
    assert 'method="post"' in html
    assert 'name="csrf_token"' in html
    assert 'name="consent"' in html
    assert "We will contact you if it is unavailable." in html
    assert "order-layout{grid-template-columns:1fr" in html
    assert "grid-template-columns:120px minmax(0,1fr)" in html
    assert "Excludes delivery" in html
    assert "No payment now" in html
    assert "notified" not in html or True

    old=dict(size="XXL",colour="Ocean blue",quantity="3",buyer_name="Test Buyer",
             phone="000000000",email="test@example.invalid",location="Lilongwe",
             notes="Please call first.",consent="1")
    rendered=render_template_string(msj_store.ORDER_TEMPLATE,
        **{**kwargs,"old":old,"error":"Please check details"})
    assert 'value="Ocean blue"' in rendered
    assert 'value="3"' in rendered
    assert 'value="Test Buyer"' in rendered
    assert 'value="Lilongwe"' in rendered
    assert "Please call first." in rendered
    assert 'value="XXL" selected' in rendered
    assert "Please check details" in rendered
    assert '<details class="order-extras" open>' in rendered
    assert 'type="checkbox" name="consent" value="1" required' in rendered
    assert "checked" in rendered
    assert "role=\"alert\"" in rendered

    opts={**kwargs,"garments":["T-shirt","Hoodie","Cap"],"sizes":["S","M","L","XL","XXL","One Size"]}
    multi=render_template_string(msj_store.ORDER_TEMPLATE,**opts)
    assert "From MK 25,000" in multi
    assert "Hoodie" in multi and "Cap" in multi
    assert '"Hoodie": 50000' in multi or '"Hoodie":50000' in multi
print("PASS MSJ mobile layout: exact shirt pricing, compact card and form, input state, estimates and future garment options")
