"""MSJ (Mulungu Si Jemusi) apparel order-request shop for IBROWS Enterprise.

No online payment capture, automatic fulfillment, or imaginary stock. All designs
are uploaded and explicitly published by an IBROWS administrator.
"""
import hashlib
import io
import os
import re
import secrets
import uuid
from datetime import datetime
from functools import wraps

import requests
from flask import Blueprint, Response, abort, redirect, render_template_string, request, session, url_for
from PIL import Image, ImageOps, UnidentifiedImageError

SHOP_CSS = """
:root{--ink:#17392b;--cream:#f6f0e5;--wine:#671b2c;--line:#ded8cc;--muted:#5d655f}
*{box-sizing:border-box}body{margin:0;background:#fcfaf6;color:#202820;font-family:system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif;line-height:1.55}
a{color:inherit}.wrap{max-width:1100px;width:calc(100% - 36px);margin:auto}
header{background:#17392b;color:white}.header-inner{min-height:72px;display:flex;gap:16px;flex-wrap:wrap;align-items:center;justify-content:space-between}
.brand{color:white;text-decoration:none;font-size:1.12rem;font-weight:850;letter-spacing:.02em}.navlinks{display:flex;gap:14px;flex-wrap:wrap;font-size:.9rem}
.navlinks a{text-decoration:none;color:#f6f0e5}.hero{background:var(--cream);padding:55px 0 46px;border-bottom:1px solid var(--line)}
.eyebrow{letter-spacing:.13em;font-size:.75rem;font-weight:850;text-transform:uppercase;color:var(--wine)}
h1{font-family:Georgia,serif;font-weight:500;font-size:clamp(2.6rem,7vw,5rem);line-height:1.08;letter-spacing:-.04em;margin:8px 0 14px}
h2{font-family:Georgia,serif;font-size:1.85rem;font-weight:500;margin:0 0 10px}.lede{max-width:640px;color:var(--muted)}
.section{padding:36px 0 64px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:24px}
.product{overflow:hidden;border:1px solid var(--line);background:white;border-radius:5px}
.product img{width:100%;aspect-ratio:4/3;display:block;object-fit:contain;background:#f2f0eb}
.product-content{padding:18px}.product-content p{margin:6px 0 15px;color:var(--muted);font-size:.9rem}
.price{font-weight:800}.button{display:inline-flex;align-items:center;justify-content:center;min-height:45px;border-radius:3px;padding:0 19px;
background:var(--ink);border:1px solid var(--ink);font-weight:800;color:white;text-decoration:none;cursor:pointer;font-size:.95rem}
.button.secondary{color:var(--ink);background:transparent}.notice{border:1px solid var(--line);background:white;padding:20px}
.pane{background:white;padding:25px;border:1px solid var(--line);border-radius:5px;max-width:800px}
label{display:block;margin:15px 0 5px;font-weight:750;font-size:.88rem}input,select,textarea{padding:11px 12px;min-height:42px;width:100%;border:1px solid #b9c5bc;border-radius:3px;font:inherit;background:white;color:#1a2921}
input[type=checkbox]{min-height:0;width:auto}textarea{min-height:100px;resize:vertical}.two{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.note{color:var(--muted);font-size:.87rem}.error{background:#fff2ef;border:1px solid #bc5b43;padding:12px;color:#752818}
.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.88rem}td,th{text-align:left;border-bottom:1px solid var(--line);padding:12px 8px;vertical-align:top}
select.small{min-width:140px}footer{border-top:1px solid var(--line);padding:20px 0;color:var(--muted);font-size:.85rem}
@media(max-width:640px){.two{grid-template-columns:1fr}.hero{padding:38px 0}.pane{padding:18px}}
"""
BASE_START = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} | Mulungu Si Jemusi · IBROWS Enterprise</title>
<style>""" + SHOP_CSS + """</style></head><body>
<header><div class="wrap header-inner">
<a href="/msj" class="brand">MSJ <span style="font-weight:400">/ Mulungu Si Jemusi</span></a>
<nav class="navlinks"><a href="/msj">Collection</a><a href="/design-branding">IBROWS Branding</a><a href="/">IBROWS Home</a></nav>
</div></header>"""
BASE_END = """<footer><div class="wrap">Mulungu Si Jemusi (MSJ) · An IBROWS Enterprise clothing line.
<p>Orders are requests pending availability and confirmation. No payment is collected on this website.</p></div></footer></body></html>"""

CATALOG_TEMPLATE=BASE_START+"""
<section class="hero"><div class="wrap"><div class="eyebrow">The MSJ Collection</div>
<h1>Mulungu Si Jemusi.</h1><p class="lede">Wear the message. Explore original MSJ artwork and request the clothing design you want.
Every order is reviewed by our team before payment, printing or delivery is arranged.</p></div></section>
<main class="section"><div class="wrap">
{% if products %}<div class="grid">{% for p in products %}
<article class="product"><a href="{{ url_for('msj.order_design', design_id=p.id) }}" aria-label="Choose {{ p.title }}">
<img src="{{ url_for('msj.design_image', design_id=p.id) }}" alt="{{ p.title }} – official Mulungu Si Jemusi artwork" loading="lazy"></a>
<div class="product-content"><div class="eyebrow">{{ p.code }}</div><h2>{{ p.title }}</h2>
<p>{{ p.description or 'Original MSJ clothing artwork.' }}</p>
<div class="price">MK {{ '{:,.0f}'.format(p.price_mwk) }} / item</div>
<p>Choose garment, size, colour and quantity on the order page.</p>
<a class="button" href="{{ url_for('msj.order_design', design_id=p.id) }}">Select design</a></div></article>{% endfor %}</div>
{% else %}<div class="notice"><h2>Collection being prepared</h2>
<p>The original MSJ artwork is being prepared for ordering. Prices and garment availability will appear here once confirmed.
No payments or orders are being taken yet.</p></div>{% endif %}
</div></main>""" + BASE_END

ORDER_TEMPLATE=BASE_START+"""
<section class="hero"><div class="wrap"><div class="eyebrow">Request MSJ Merchandise</div><h1>{{ design.title }}</h1>
<p class="lede">Your artwork choice is reserved for this request only after IBROWS confirms availability. You will not be charged now.</p></div></section>
<main class="section"><div class="wrap">
<div class="two" style="grid-template-columns:minmax(0,1fr) minmax(0,1.35fr);align-items:start">
<div class="product"><img src="{{ url_for('msj.design_image',design_id=design.id) }}" alt="Original {{ design.title }} artwork"><div class="product-content">
<p>{{ design.description }}</p><strong>MK {{ '{:,.0f}'.format(design.price_mwk) }} per item</strong>
<p>Artwork preview is not necessarily a finished garment mock-up.</p></div></div>
<div class="pane">{% if error %}<p class="error" role="alert">{{ error }}</p>{% endif %}
<h2>Place an order request</h2>
<form method="post" action="{{ url_for('msj.order_design',design_id=design.id) }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<input type="text" name="fax_number" tabindex="-1" autocomplete="off" style="position:absolute;left:-9999px" aria-hidden="true">
<div class="two"><div><label for="garment">Clothing type *</label><select id="garment" name="garment" required>
{% for v in garments %}<option value="{{ v }}">{{ v }}</option>{% endfor %}</select></div>
<div><label for="size">Size *</label><select id="size" name="size" required>
{% for v in sizes %}<option value="{{ v }}">{{ v }}</option>{% endfor %}</select></div></div>
<div class="two"><div><label for="colour">Colour *</label><select id="colour" name="colour" required>
{% for v in colours %}<option value="{{ v }}">{{ v }}</option>{% endfor %}</select></div>
<div><label for="quantity">Quantity *</label><input id="quantity" name="quantity" type="number" value="1" min="1" max="30" required></div></div>
<p class="note">The listed amount is an estimate for the selected quantity. IBROWS confirms stock, garment options and final delivery costs before accepting payment.</p>
<div class="two"><div><label for="buyer_name">Full name *</label><input id="buyer_name" name="buyer_name" maxlength="160" required></div>
<div><label for="phone">Phone / WhatsApp *</label><input id="phone" name="phone" maxlength="50" inputmode="tel" required></div></div>
<div class="two"><div><label for="email">Email (optional)</label><input id="email" type="email" name="email" maxlength="180"></div>
<div><label for="location">Area / delivery town *</label><input id="location" name="location" maxlength="160" required></div></div>
<label for="notes">Notes or custom instructions (optional)</label><textarea id="notes" name="notes" maxlength="1200" placeholder="Preferred fit, delivery details or questions"></textarea>
<label><input type="checkbox" name="consent" value="1" required> I agree that IBROWS may use my details to respond to this merchandise request.</label>
<p class="note">No payment is collected at this stage. IBROWS will contact you to confirm the final order and payment instructions.</p>
<button class="button" type="submit">Send order request</button></form>
</div></div></div></main>""" + BASE_END

COMPLETE_TEMPLATE=BASE_START+"""
<section class="hero"><div class="wrap"><div class="eyebrow">Request received</div><h1>Thank you.</h1>
<p class="lede">Your MSJ merchandise request has been recorded. IBROWS will review the design and availability before confirming a payment or delivery arrangement.</p></div></section>
<main class="section"><div class="wrap"><div class="pane">
<h2>Your order reference</h2><p style="font-size:1.4rem;font-weight:850">{{ reference }}</p>
<p>{{ design_title }} · {{ garment }} · {{ colour }} · {{ size }} · quantity {{ quantity }}</p>
<p><strong>Status:</strong> Pending IBROWS confirmation. No payment has been received or requested by this form.</p>
<a class="button secondary" href="/msj">Back to MSJ Collection</a>
</div></div></main>""" + BASE_END

ADMIN_TEMPLATE=BASE_START+"""
<section class="hero"><div class="wrap"><div class="eyebrow">IBROWS ADMIN / MSJ</div>
<h1>Merchandise management</h1><p>Upload real MSJ artwork, publish confirmed products and review orders. Payments must be verified separately in the IBROWS ledger.</p>
<p><a class="button secondary" href="/admin">Back to admin</a></p></div></section>
<main class="section"><div class="wrap">
{% if message %}<div class="notice" role="status">{{ message }}</div>{% endif %}
<div class="pane"><h2>Add MSJ design</h2><form method="post" action="{{ url_for('msj.admin_add') }}" enctype="multipart/form-data">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<div class="two"><div><label>Design title *</label><input name="title" required maxlength="120" placeholder="MSJ Classic"></div>
<div><label>Internal design code *</label><input name="code" required maxlength="30" placeholder="MSJ-CLASSIC"></div></div>
<label>Description</label><input name="description" maxlength="300" placeholder="Official cream artwork on deep green">
<label>Original artwork image (PNG, JPEG or WebP) *</label><input type="file" name="image" accept="image/png,image/jpeg,image/webp" required>
<p class="note">Upload only your authentic artwork or approved product photograph. Maximum 5 MB. We resize for the web without redesigning the artwork.</p>
<div class="two"><div><label>Price per item in MWK *</label><input name="price_mwk" type="number" min="1" max="10000000" required>
</div><div><label>Available garment types (comma-separated) *</label><input name="garments" placeholder="T-shirt, Hoodie" required></div></div>
<div class="two"><div><label>Sizes (comma-separated) *</label><input name="sizes" placeholder="S, M, L, XL, 2XL" required></div>
<div><label>Available colours (comma-separated) *</label><input name="colours" placeholder="Black, White" required></div></div>
<button class="button" type="submit">Save unpublished design</button></form></div>
<h2 style="margin-top:38px">Catalogue</h2>
{% if products %}<div class="table-wrap"><table><thead><tr><th>Design</th><th>Price</th><th>Status</th><th>Update</th></tr></thead><tbody>
{% for p in products %}<tr><td><img src="{{ url_for('msj.design_image',design_id=p.id) }}" width="110" alt=""><div><strong>{{ p.title }}</strong><br>{{ p.code }}</div></td>
<td>MK {{ '{:,.0f}'.format(p.price_mwk) }}</td><td>{{ 'Published' if p.published else 'Draft' }}</td>
<td><form method="post" action="{{ url_for('msj.admin_toggle',design_id=p.id) }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<button class="button secondary" type="submit">{{ 'Unpublish' if p.published else 'Publish' }}</button></form></td></tr>{% endfor %}
</tbody></table></div>{% else %}<p>No designs yet. Add the real MSJ Classic and Varsity artwork above.</p>{% endif %}
<h2 style="margin-top:38px">Customer orders</h2>
{% if orders %}<div class="table-wrap"><table><thead><tr><th>Reference</th><th>Customer</th><th>Selection</th><th>Estimated</th><th>Status</th></tr></thead><tbody>
{% for o in orders %}<tr><td><strong>{{ o.reference }}</strong><br><small>{{ o.created_at }}</small></td>
<td>{{ o.buyer_name }}<br>{{ o.phone }}<br>{{ o.email or '' }}<br>{{ o.location }}</td>
<td>{{ o.title }}<br>{{ o.garment }} · {{ o.size }} · {{ o.colour }}<br>Qty {{ o.quantity }}<br>{{ o.notes }}</td>
<td>MK {{ '{:,.0f}'.format(o.estimated_total) }}<br><small>Email: {{ o.notification_status }}</small></td>
<td><form method="post" action="{{ url_for('msj.admin_status',order_id=o.id) }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<select name="status" aria-label="Update order status">
{% for status in ['NEW','CONTACTED','QUOTED','CONFIRMED','IN_PRODUCTION','FULFILLED','CANCELLED'] %}
<option value="{{ status }}" {% if o.status == status %}selected{% endif %}>{{ status.replace('_',' ').title() }}</option>{% endfor %}
</select><button class="button secondary" type="submit">Save</button></form></td></tr>{% endfor %}
</tbody></table></div>{% else %}<p>No orders have been placed.</p>{% endif %}
</div></main>""" + BASE_END


def register_msj_store(app, get_db, public_csrf, admin_csrf, validate_admin_csrf, admin_required):
    bp=Blueprint("msj",__name__)
    initialized=False

    def connect_setup():
        nonlocal initialized
        if initialized:return
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(451108320)")
                cur.execute("""CREATE TABLE IF NOT EXISTS msj_merch_designs (
                    id BIGSERIAL PRIMARY KEY,
                    code VARCHAR(30) UNIQUE NOT NULL,
                    title VARCHAR(120) NOT NULL,
                    description VARCHAR(300) NOT NULL DEFAULT '',
                    price_mwk INTEGER NOT NULL CHECK (price_mwk > 0),
                    garments TEXT NOT NULL,
                    sizes TEXT NOT NULL,
                    colours TEXT NOT NULL,
                    image_bytes BYTEA NOT NULL,
                    image_mime VARCHAR(30) NOT NULL,
                    published BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
                cur.execute("""CREATE TABLE IF NOT EXISTS msj_merch_orders (
                    id BIGSERIAL PRIMARY KEY,
                    reference VARCHAR(32) UNIQUE,
                    token UUID UNIQUE NOT NULL,
                    design_id BIGINT NOT NULL REFERENCES msj_merch_designs(id),
                    buyer_name VARCHAR(160) NOT NULL,
                    phone VARCHAR(50) NOT NULL,
                    email VARCHAR(180),
                    location VARCHAR(160) NOT NULL,
                    garment VARCHAR(50) NOT NULL,
                    size VARCHAR(24) NOT NULL,
                    colour VARCHAR(50) NOT NULL,
                    quantity SMALLINT NOT NULL CHECK (quantity BETWEEN 1 AND 30),
                    notes VARCHAR(1200) NOT NULL DEFAULT '',
                    estimated_total INTEGER NOT NULL,
                    status VARCHAR(24) NOT NULL DEFAULT 'NEW',
                    notification_status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
                    notification_error VARCHAR(120),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_msj_orders_time ON msj_merch_orders (created_at DESC)")
            conn.commit()
        initialized=True

    def csv_choices(raw):
        out=[]
        for s in (raw or "").split(","):
            s=s.strip()[:50]
            if s and s not in out:out.append(s)
        return out[:20]

    def product_rows(published_only=True):
        connect_setup()
        sql="SELECT id,code,title,description,price_mwk,garments,sizes,colours,published FROM msj_merch_designs"
        if published_only:sql+=" WHERE published=TRUE"
        sql+=" ORDER BY id DESC"
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                names=[x.name for x in cur.description]
                return [dict(zip(names,r)) for r in cur.fetchall()]

    def product_by_id(ident,public=True):
        connect_setup()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT id,code,title,description,price_mwk,garments,sizes,colours,published
                    FROM msj_merch_designs WHERE id=%s"""+(" AND published=TRUE" if public else ""), (ident,))
                row=cur.fetchone()
                if not row:return None
                return dict(zip([x.name for x in cur.description],row))

    def image_sanitize(upload):
        if not upload or not upload.filename:raise ValueError("Please upload approved MSJ artwork.")
        raw=upload.stream.read(5*1024*1024+1)
        if len(raw)>5*1024*1024:raise ValueError("Keep artwork files at 5 MB or smaller.")
        try:
            im=Image.open(io.BytesIO(raw))
            if im.format not in {"PNG","JPEG","WEBP"}:raise ValueError("Artwork must be PNG, JPEG or WebP.")
            if im.width*im.height>18_000_000:raise ValueError("Artwork image dimensions are too large.")
            im=ImageOps.exif_transpose(im)
            im.thumbnail((1600,1600), Image.Resampling.LANCZOS)
            b=io.BytesIO()
            if im.mode in ("RGBA","P","LA"):
                im=im.convert("RGBA")
                im.save(b,"PNG",optimize=True)
                mime="image/png"
            else:
                im=im.convert("RGB")
                im.save(b,"JPEG",quality=92,optimize=True)
                mime="image/jpeg"
            return b.getvalue(),mime
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValueError(f"Please upload a valid MSJ artwork image: {exc}") from exc

    def render(page,**kwargs):
        return render_template_string(page,**kwargs)

    @bp.route("/msj",methods=["GET"])
    def catalog():
        return render(CATALOG_TEMPLATE,title="MSJ Clothing Collection",products=product_rows())

    @bp.route("/msj/design/<int:design_id>/image",methods=["GET"])
    def design_image(design_id):
        connect_setup()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT image_bytes,image_mime,published FROM msj_merch_designs WHERE id=%s",(design_id,))
                row=cur.fetchone()
        if row is None or (not row[2] and not session.get("admin_authenticated")):abort(404)
        response=Response(bytes(row[0]),content_type=row[1])
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Cache-Control"]="public, max-age=3600" if row[2] else "private, no-store"
        return response

    @bp.route("/msj/design/<int:design_id>",methods=["GET","POST"])
    def order_design(design_id):
        p=product_by_id(design_id)
        if not p:abort(404)
        garment_choices=csv_choices(p["garments"])
        size_choices=csv_choices(p["sizes"])
        colour_choices=csv_choices(p["colours"])
        if request.method=="GET":
            return render(ORDER_TEMPLATE,title=p["title"],design=p,garments=garment_choices,
                          sizes=size_choices,colours=colour_choices,csrf_token=public_csrf("MSJ_ORDER"),error="")
        supplied=str(request.form.get("csrf_token") or "")
        if not supplied or not secrets.compare_digest(supplied,public_csrf("MSJ_ORDER")):abort(403)
        if request.form.get("fax_number"):abort(400)
        try:
            garment=request.form.get("garment","")[:50]
            size=request.form.get("size","")[:24]
            colour=request.form.get("colour","")[:50]
            if garment not in garment_choices or size not in size_choices or colour not in colour_choices:
                raise ValueError("Select a valid garment, colour and size.")
            quantity=int(request.form.get("quantity","0"))
            if not 1<=quantity<=30:raise ValueError("Order quantity must be between 1 and 30.")
            buyer_name=str(request.form.get("buyer_name","")).strip()[:160]
            phone=str(request.form.get("phone","")).strip()[:50]
            email=str(request.form.get("email","")).strip().lower()[:180]
            location=str(request.form.get("location","")).strip()[:160]
            notes=str(request.form.get("notes","")).strip()[:1200]
            if len(buyer_name)<2 or len(re.sub(r"\D","",phone))<7 or len(location)<2:
                raise ValueError("Enter your name, a valid contact number and your town.")
            if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email):
                raise ValueError("Please enter a valid email or leave it blank.")
            if request.form.get("consent")!="1":
                raise ValueError("Please consent to IBROWS processing your order request.")
            token=uuid.uuid4()
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""SELECT COUNT(*) FROM msj_merch_orders
                        WHERE phone=%s AND created_at > NOW() - INTERVAL '1 hour'""",(phone,))
                    if cur.fetchone()[0]>=3:
                        raise ValueError("You've sent several requests recently. Please contact IBROWS to follow up.")
                    cur.execute("""INSERT INTO msj_merch_orders(token,design_id,buyer_name,phone,email,location,
                         garment,size,colour,quantity,notes,estimated_total)
                         SELECT %s,id,%s,%s,%s,%s,%s,%s,%s,%s,%s,price_mwk*%s
                         FROM msj_merch_designs WHERE id=%s AND published=TRUE
                         RETURNING id""", (str(token),buyer_name,phone,email or None,location,
                                garment,size,colour,quantity,notes,quantity,design_id))
                    inserted=cur.fetchone()
                    if not inserted:raise ValueError("That design is currently unavailable.")
                    oid=inserted[0]
                    ref=f"MSJ-{datetime.utcnow().year}-{oid:05d}"
                    cur.execute("UPDATE msj_merch_orders SET reference=%s WHERE id=%s",(ref,oid))
                conn.commit()
            send_notification(oid,ref,p,garment,size,colour,quantity,buyer_name,phone,location)
            return redirect(url_for("msj.complete",token=token),code=303)
        except (ValueError,TypeError):
            return render(ORDER_TEMPLATE,title=p["title"],design=p,garments=garment_choices,
                 sizes=size_choices,colours=colour_choices,csrf_token=public_csrf("MSJ_ORDER"),
                 error="Please check your selected garment, contact details, quantity and consent."),400

    def send_notification(order_id,reference,p,garment,size,colour,quantity,buyer_name,phone,location):
        key=os.getenv("BREVO_API_KEY","").strip()
        recipient=os.getenv("NOTIFICATION_EMAIL","").strip()
        sender=os.getenv("BREVO_SENDER_EMAIL","").strip() or "info@ibrowsenterprise.com"
        error="Brevo email not configured"
        sent=False
        if key and recipient:
            try:
                response=requests.post("https://api.brevo.com/v3/smtp/email",
                    headers={"api-key":key,"Content-Type":"application/json"},
                    json={"sender":{"email":sender,"name":"IBROWS Enterprise"},
                          "to":[{"email":recipient}],
                          "subject":f"MSJ merchandise order request {reference}",
                          "textContent":f"INTERNAL IBROWS MSJ ORDER\nReference: {reference}\nDesign: {p['title']}\nGarment: {garment}\nSize: {size}\nColour: {colour}\nQuantity: {quantity}\nBuyer: {buyer_name}\nPhone: {phone}\nTown: {location}\nReview in IBROWS Admin /admin/msj. No payment verified."},timeout=8)
                sent=200<=response.status_code<300
                if not sent:error=f"Brevo HTTP {response.status_code}"
            except Exception as exc:
                error=type(exc).__name__
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE msj_merch_orders
                        SET notification_status=%s,notification_error=%s,updated_at=NOW()
                        WHERE id=%s""",("SENT" if sent else "FAILED",None if sent else error,order_id))
            conn.commit()

    @bp.route("/msj/order/<uuid:token>",methods=["GET"])
    def complete(token):
        connect_setup()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT o.reference,d.title,o.garment,o.colour,o.size,o.quantity
                    FROM msj_merch_orders o JOIN msj_merch_designs d ON d.id=o.design_id
                    WHERE o.token=%s""",(str(token),))
                r=cur.fetchone()
        if not r:abort(404)
        return render(COMPLETE_TEMPLATE,title="Order request received",reference=r[0],
                      design_title=r[1],garment=r[2],colour=r[3],size=r[4],quantity=r[5])

    @bp.route("/admin/msj",methods=["GET"])
    @admin_required
    def admin_index():
        connect_setup()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT o.id,o.reference,o.created_at,o.buyer_name,o.phone,o.email,o.location,
                    o.garment,o.size,o.colour,o.quantity,o.notes,o.estimated_total,o.status,
                    o.notification_status,d.title FROM msj_merch_orders o
                    JOIN msj_merch_designs d ON d.id=o.design_id
                    ORDER BY o.id DESC LIMIT 200""")
                keys=[x.name for x in cur.description]
                orders=[dict(zip(keys,r)) for r in cur.fetchall()]
        return render(ADMIN_TEMPLATE,title="MSJ Admin",products=product_rows(False),
                      orders=orders,csrf_token=admin_csrf(),
                      message=request.args.get("message","")[:180])

    @bp.route("/admin/msj/designs/add",methods=["POST"])
    @admin_required
    def admin_add():
        validate_admin_csrf()
        try:
            title=str(request.form.get("title","")).strip()[:120]
            code=str(request.form.get("code","")).strip().upper()[:30]
            desc=str(request.form.get("description","")).strip()[:300]
            price=int(request.form.get("price_mwk","0"))
            garments=",".join(csv_choices(request.form.get("garments","")))
            sizes=",".join(csv_choices(request.form.get("sizes","")))
            colours=",".join(csv_choices(request.form.get("colours","")))
            if not title or not re.fullmatch(r"[A-Z0-9_-]{3,30}",code) or not 1<=price<=10_000_000:
                raise ValueError("Enter a design title, unique code and positive price.")
            if not garments or not sizes or not colours:raise ValueError("Set the available garment types, sizes and colours.")
            image_bytes,mime=image_sanitize(request.files.get("image"))
            connect_setup()
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""INSERT INTO msj_merch_designs
                        (code,title,description,price_mwk,garments,sizes,colours,image_bytes,image_mime)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (code,title,desc,price,garments,sizes,colours,image_bytes,mime))
                conn.commit()
            msg="Design saved as draft. Publish only after confirming available stock and pricing."
        except (ValueError,TypeError) as exc:
            msg=str(exc)
        return redirect(url_for("msj.admin_index",message=msg))

    @bp.route("/admin/msj/designs/<int:design_id>/publish",methods=["POST"])
    @admin_required
    def admin_toggle(design_id):
        validate_admin_csrf()
        connect_setup()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE msj_merch_designs SET published=NOT published WHERE id=%s RETURNING published",(design_id,))
                row=cur.fetchone()
            conn.commit()
        if not row:abort(404)
        return redirect(url_for("msj.admin_index",message="Design publication updated."))

    @bp.route("/admin/msj/orders/<int:order_id>/status",methods=["POST"])
    @admin_required
    def admin_status(order_id):
        validate_admin_csrf()
        allowed={"NEW","CONTACTED","QUOTED","CONFIRMED","IN_PRODUCTION","FULFILLED","CANCELLED"}
        status=request.form.get("status","").upper()
        if status not in allowed:abort(400)
        connect_setup()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE msj_merch_orders SET status=%s,updated_at=NOW()
                    WHERE id=%s RETURNING id""",(status,order_id))
                row=cur.fetchone()
            conn.commit()
        if not row:abort(404)
        return redirect(url_for("msj.admin_index",message="Order status saved. Verify payments separately."))

    app.register_blueprint(bp)
