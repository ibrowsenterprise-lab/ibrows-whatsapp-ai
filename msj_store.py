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
from msj_catalogue_repair import repair_ms_j_misassigned_sheet_images

# Confirmed MSJ prices and apparel sizes. Amounts are in Malawi kwacha.
MSJ_GARMENT_PRICES = {"T-shirt": 25000, "Hoodie": 50000, "Cap": 20000}
MSJ_APPAREL_SIZES = ("S", "M", "L", "XL", "XXL")
MSJ_CAP_SIZE = "One Size"

MSJ_MERCH_SPECS = {
            "MSJ_Wordmark_Hoodie_Lifestyle.jpg":
                ("MSJ-WORDMARK-HOODIE","MSJ Wordmark Hoodie","Hoodie","Forest green",
                 "Original MSJ wordmark green hoodie shown in a collection lifestyle mockup. Other accessories in photo are not included."),
            "MSJ_Block_Hoodie.jpg":
                ("MSJ-BLOCK-HOODIE","MSJ Block Hoodie","Hoodie","Black",
                 "Original black hoodie mockup with the bold MSJ block logo."),
            "MSJ_Wordmark_Cap.jpg":
                ("MSJ-WORDMARK-CAP","MSJ Wordmark Cap","Cap","Black",
                 "Original black cap with white MSJ wordmark patch, cropped from the original collection mockup."),
            "MSJ_Block_Cap.jpg":
                ("MSJ-BLOCK-CAP","MSJ Block Cap","Cap","Black",
                 "Original black cap mockup with embroidered MSJ block logo."),
            "MSJ_Block_Tshirt.jpg":
                ("MSJ-BLOCK-TSHIRT","MSJ Block T-shirt","T-shirt","Black",
                 "Original black T-shirt mockup with the bold MSJ block logo.")
        }
MSJ_MERCH_PHOTO_FIELDS = (
    ("wordmark_hoodie", "Wordmark hoodie (green lifestyle photo)", "MSJ_Wordmark_Hoodie_Lifestyle.jpg"),
    ("block_hoodie", "Block logo hoodie (black)", "MSJ_Block_Hoodie.jpg"),
    ("wordmark_cap", "Wordmark cap (black with white patch)", "MSJ_Wordmark_Cap.jpg"),
    ("block_cap", "Block logo cap (black)", "MSJ_Block_Cap.jpg"),
    ("block_tshirt", "Block logo T-shirt (black)", "MSJ_Block_Tshirt.jpg"),
)


def msj_product_options(garments):
    """Calculate the advertised price strictly from approved garment prices."""
    choices = [g.strip() for g in (garments or "").split(",") if g.strip()]
    if not choices or any(g not in MSJ_GARMENT_PRICES for g in choices):
        raise ValueError("Available merchandise must be T-shirt, Hoodie or Cap.")
    return min(MSJ_GARMENT_PRICES[g] for g in choices)


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
.pane{background:white;padding:25px;border:1px solid var(--line);border-radius:5px;max-width:800px}.order-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.35fr);align-items:start;gap:20px}
label{display:block;margin:15px 0 5px;font-weight:750;font-size:.88rem}input,select,textarea{padding:11px 12px;min-height:42px;width:100%;border:1px solid #b9c5bc;border-radius:3px;font:inherit;background:white;color:#1a2921}
input[type=checkbox]{min-height:0;width:auto}textarea{min-height:100px;resize:vertical}.two{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.note{color:var(--muted);font-size:.87rem}.error{background:#fff2ef;border:1px solid #bc5b43;padding:12px;color:#752818}
.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.88rem}td,th{text-align:left;border-bottom:1px solid var(--line);padding:12px 8px;vertical-align:top}
select.small{min-width:140px}
.bulk-panel{border:1px solid #ccd9cd;border-radius:6px;background:#eff5ee;padding:18px 20px;margin:15px 0 20px}
.bulk-panel h3{margin:0 0 8px;font-size:1.18rem}
.bulk-panel p{margin:0 0 12px;color:var(--muted)}
.bulk-panel form{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.bulk-panel button:disabled{opacity:.55;cursor:not-allowed}
.shop-filters{display:flex;flex-wrap:wrap;gap:9px;margin:0 0 22px}.shop-filter{border:1px solid #c7d6ca;border-radius:30px;padding:7px 17px;text-decoration:none;font-weight:700;font-size:.87rem;background:#fff}.shop-filter[aria-current="page"]{background:var(--ink);color:#fff;border-color:var(--ink)}.shop-empty{border:1px solid var(--line);padding:24px;background:#fff}.shop-product-type{font-size:.83rem;color:var(--muted);font-weight:730;margin:4px 0}.admin-merch-import{margin-top:22px;border:1px solid #cddacc;background:#f7faf4;border-radius:6px;padding:20px}.admin-merch-import input{max-width:520px}
footer{border-top:1px solid var(--line);padding:20px 0;color:var(--muted);font-size:.85rem}
@media(max-width:640px){
.two,.order-layout{grid-template-columns:1fr}.hero{padding:38px 0}.pane{padding:18px}
.catalog-table,.catalog-table tbody,.catalog-table tr,.catalog-table td{display:block;width:100%}
.catalog-table thead{display:none}
.catalog-table tr{padding:14px;border:1px solid var(--line);border-radius:6px;background:white;margin-bottom:12px}
.catalog-table td{padding:8px 0;border:0;white-space:normal}
.catalog-table td[data-label]::before{content:attr(data-label);display:block;font-size:.7rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:3px}
.catalog-table td img{max-width:180px;height:auto}
.catalog-table td .button{min-height:44px}
.bulk-panel{padding:15px}
.bulk-panel .button{width:100%}
}
"""
SHOP_CSS += """
/* Compact order page on mobile */
.order-hero{padding:24px 0 20px}.order-hero h1{font-size:clamp(1.9rem,4vw,2.7rem);line-height:1.12;letter-spacing:-.02em;margin:6px 0 10px}.order-hero .lede{font-size:.94rem;margin:0}
.order-section{padding:18px 0 42px}.order-layout{grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr);gap:17px}.order-product{align-self:start}.order-product img{aspect-ratio:1/1}.order-product .product-content{padding:12px 15px}.order-product .product-content p{margin:4px 0 8px}.order-pane{max-width:none;padding:20px}.order-pane h2{font-family:system-ui,sans-serif;font-size:1.25rem;font-weight:750}.order-pane label{margin-top:10px}.order-pane .two{gap:10px}.order-help{font-size:.8rem;color:var(--muted);line-height:1.4;margin:4px 0}.order-total{display:flex;align-items:center;justify-content:space-between;gap:12px;background:#f5f6f2;border:1px solid #e2e8de;padding:10px 12px;margin:13px 0 6px;border-radius:4px}.order-total>strong{font-size:1.27rem;white-space:nowrap;color:var(--ink)}.order-consent{display:flex;align-items:flex-start;gap:10px;font-weight:500!important;font-size:.83rem}.order-consent input{width:18px;height:18px;min-height:0;flex:0 0 auto;margin-top:4px}.order-pane button[type=submit]{width:100%;min-height:48px}.order-pane summary{cursor:pointer;font-weight:700;padding:8px 0}.order-extras{margin-top:10px;border-top:1px solid var(--line)}
@media(max-width:760px){.order-layout{grid-template-columns:1fr;gap:14px}.order-hero{padding:18px 0}.order-hero h1{font-size:2rem}.order-section{padding:14px 0 35px}.order-product{display:grid;grid-template-columns:120px minmax(0,1fr);align-items:center}.order-product img{width:120px;height:132px;object-fit:contain;aspect-ratio:auto}.order-product .product-content{padding:9px 12px}.order-product .product-content p{font-size:.81rem}.order-pane{padding:17px}.order-pane .two{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.order-pane [data-full-mobile]{grid-column:1/-1}}
@media(max-width:360px){.order-product{grid-template-columns:95px minmax(0,1fr)}.order-product img{width:95px;height:120px}.order-pane .two{grid-template-columns:1fr}.order-pane [data-full-mobile]{grid-column:auto}}
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
Every order is reviewed by our team before payment, printing or delivery is arranged. Request any colour you like; IBROWS will notify you if your preferred colour is unavailable.</p></div></section>
<main class="section"><div class="wrap">
<nav class="shop-filters" aria-label="Shop by merchandise type">
<a class="shop-filter" href="{{ url_for('msj.catalog') }}" {% if not garment_filter %}aria-current="page"{% endif %}>All designs</a>
{% for category in ['T-shirt','Hoodie','Cap'] %}
<a class="shop-filter" href="{{ url_for('msj.catalog', garment=category) }}" {% if garment_filter==category %}aria-current="page"{% endif %}>{{ {'T-shirt':'T-shirts','Hoodie':'Hoodies','Cap':'Caps'}[category] }}{% if category == 'Hoodie' and not hoodies_listed %} (Out of stock){% endif %}</a>
{% endfor %}
</nav>
{% if products %}<div class="grid">{% for p in products %}
<article class="product"><a href="{{ url_for('msj.order_design', design_id=p.id) }}" aria-label="Choose {{ p.title }}">
<img src="{{ url_for('msj.design_image', design_id=p.id, v=p.image_revision[:12]) }}" alt="{{ p.title }} – official Mulungu Si Jemusi artwork" loading="lazy"></a>
<div class="product-content"><div class="eyebrow">{{ p.code }}</div><h2>{{ p.title }}</h2>
<p>{{ p.description or 'Original MSJ clothing artwork.' }}</p>
<div class="price">{% if ',' not in p.garments %}MK {{ '{:,.0f}'.format(p.price_mwk) }}{% else %}From MK {{ '{:,.0f}'.format(p.price_mwk) }}{% endif %}</div>
<p>Available: {{ p.garments }}. Choose size, preferred colour and quantity when ordering.</p>
<a class="button" href="{{ url_for('msj.order_design', design_id=p.id) }}">Select design</a></div></article>{% endfor %}</div>
{% else %}<div class="notice">
{% if garment_filter == 'Hoodie' %}
<h2>Hoodies temporarily out of stock</h2>
<p>MSJ hoodies are not currently available for ordering. Please check back once stock has been confirmed.</p>
{% else %}
<h2>Collection being prepared</h2>
<p>{% if garment_filter %}We're preparing more MSJ {{ {'T-shirt':'T-shirts','Cap':'caps'}[garment_filter] }} for the collection. Check back after new designs are approved.{% else %}New MSJ designs are being prepared. Only approved products are available to request.{% endif %}</p>
{% endif %}
</div>{% endif %}
</div></main>""" + BASE_END

ORDER_TEMPLATE=BASE_START+"""
<section class="hero order-hero"><div class="wrap"><div class="eyebrow">MSJ / Order request</div><h1>{{ design.title }}</h1>
<p class="lede">Choose your size and preferred colour. We confirm availability before payment.</p></div></section>
<main class="section order-section"><div class="wrap">
<div class="order-layout">
<div class="product order-product"><img src="{{ url_for('msj.design_image',design_id=design.id, v=design.image_revision[:12]) }}" alt="Original {{ design.title }} artwork"><div class="product-content">
<p><strong>{{ design.title }}</strong></p><strong class="price">{% if garments|length == 1 %}MK {{ '{:,.0f}'.format(garment_prices[garments[0]]) }}{% else %}From MK {{ '{:,.0f}'.format(design.price_mwk) }}{% endif %}</strong>
<p>{{ garments|join(' / ') }} · Choose any colour.</p><a href="/msj" style="font-size:.82rem;font-weight:750">Change design</a></div></div>
<div class="pane order-pane">{% if error %}<p class="error" role="alert">{{ error }}</p>{% endif %}
<h2>Your order</h2>
<form method="post" action="{{ url_for('msj.order_design',design_id=design.id) }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<input type="text" name="fax_number" tabindex="-1" autocomplete="off" style="position:absolute;left:-9999px" aria-hidden="true">
<div class="two"><div><label for="garment">Clothing type *</label><select id="garment" name="garment" required>
{% for v in garments %}<option value="{{ v }}" {% if old.get('garment')==v %}selected{% endif %}>{{ v }}</option>{% endfor %}</select></div>
<div><label for="size">Size *</label><select id="size" name="size" required>
{% for v in sizes %}<option value="{{ v }}" {% if old.get('size')==v %}selected{% endif %}>{{ v }}</option>{% endfor %}</select></div></div>
<script>
(function () {
  function syncSize() {
    var garment = document.getElementById("garment");
    var size = document.getElementById("size");
    if (!garment || !size) return;
    var cap = garment.value === "Cap";
    for (var i = 0; i < size.options.length; i++) {
      var option = size.options[i];
      var allowed = cap ? option.value === "One Size" : option.value !== "One Size";
      option.disabled = !allowed;
      option.hidden = !allowed;
    }
    if (!size.options[size.selectedIndex] || size.options[size.selectedIndex].disabled) {
      for (var j = 0; j < size.options.length; j++) {
        if (!size.options[j].disabled) { size.selectedIndex = j; break; }
      }
    }
  }
  var garment = document.getElementById("garment");
  if (garment) { garment.addEventListener("change", syncSize); syncSize(); }
})();
</script>
<div class="two"><div><label for="colour">Preferred colour *</label>
<input id="colour" name="colour" type="text" list="msj-colour-ideas" maxlength="50" value="{{ old.get('colour','') }}" placeholder="e.g. Forest green or wine red" required autocomplete="off">
<datalist id="msj-colour-ideas">{% for v in colours %}<option value="{{ v }}">{% endfor %}</datalist>
<p class="order-help">Any colour is welcome. We will contact you if it is unavailable.</p></div>
<div><label for="quantity">Quantity *</label><input id="quantity" name="quantity" type="number" value="{{ old.get('quantity','1') }}" min="1" max="30" required></div></div>
<div class="order-total" aria-live="polite">
<div><strong>Estimated subtotal</strong><p class="order-help">Excludes delivery · No payment now</p></div>
<strong id="order-subtotal">MK {{ '{:,.0f}'.format(garment_prices[garments[0]]) }}</strong>
</div>
<div class="two"><div><label for="buyer_name">Full name *</label><input id="buyer_name" name="buyer_name" maxlength="160" required value="{{ old.get('buyer_name','') }}"></div>
<div><label for="phone">Phone / WhatsApp *</label><input id="phone" name="phone" maxlength="50" inputmode="tel" required value="{{ old.get('phone','') }}"></div></div>
<div class="two"><div><label for="email">Email (optional)</label><input id="email" type="email" name="email" maxlength="180" value="{{ old.get('email','') }}"></div>
<div><label for="location">Area / delivery town *</label><input id="location" name="location" maxlength="160" required value="{{ old.get('location','') }}"></div></div>
<details class="order-extras" {% if old.get('notes') %}open{% endif %}>
<summary>Special instructions (optional)</summary>
<label for="notes">Order notes</label>
<textarea id="notes" name="notes" maxlength="1200" placeholder="Preferred fit, delivery questions or other details">{{ old.get('notes','') }}</textarea>
</details>
<label class="order-consent"><input type="checkbox" name="consent" value="1" required
{% if old.get('consent')=='1' %}checked{% endif %}>
<span>I agree that IBROWS may use my contact details to respond to this order request.</span></label>
<p class="order-help">IBROWS checks size and colour before confirming production, delivery or payment.</p>
<button class="button" type="submit">Send order request</button></form>
</div></div></div></main>
<script>
/* V143_SUBTOTAL_READY: price display mirrors backend's fixed garment pricing. */
(function(){
  var garment=document.getElementById('garment');
  var quantity=document.getElementById('quantity');
  var subtotal=document.getElementById('order-subtotal');
  var prices={{ garment_prices|tojson }};
  if(!garment || !quantity || !subtotal) return;
  function updateTotal(){
    var count=Number(quantity.value);
    var unit=prices[garment.value];
    if(!Number.isInteger(count) || count<1 || count>30 || !unit){
      subtotal.textContent='Check selection';return;
    }
    subtotal.textContent='MK '+(unit*count).toLocaleString('en-US');
  }
  garment.addEventListener('change',updateTotal);
  quantity.addEventListener('input',updateTotal);
  updateTotal();
})();
</script>""" + BASE_END

COMPLETE_TEMPLATE=BASE_START+"""
<section class="hero"><div class="wrap"><div class="eyebrow">Request received</div><h1>Thank you.</h1>
<p class="lede">Your MSJ merchandise request has been recorded. IBROWS will review the design and availability before confirming a payment or delivery arrangement.</p></div></section>
<main class="section"><div class="wrap"><div class="pane">
<h2>Your order reference</h2><p style="font-size:1.4rem;font-weight:850">{{ reference }}</p>
<p>{{ design_title }} · {{ garment }} · {{ colour }} · {{ size }} · quantity {{ quantity }}</p>
<p><strong>Status:</strong> {{ order_status.replace('_',' ').title() }}. No payment has been received or requested by this form.</p>
{% if order_status=='COLOUR_UNAVAILABLE' %}<p class="error" role="status">Your requested colour {{ colour }} is currently unavailable. IBROWS will contact you about an alternative. No payment or production will go ahead without your approval.</p>
{% else %}<p>Your requested colour will be checked before the order is confirmed.</p>{% endif %}
<a class="button secondary" href="/msj">Back to MSJ Collection</a>
</div></div></main>""" + BASE_END

ADMIN_TEMPLATE=BASE_START+"""
<section class="hero"><div class="wrap"><div class="eyebrow">IBROWS ADMIN / MSJ</div>
<h1>Merchandise management</h1><p>Upload real MSJ artwork, publish confirmed products and review orders. Payments must be verified separately in the IBROWS ledger.</p>
<p><a class="button secondary" href="/admin">Back to admin</a> <a class="button" href="#merch-import-title">Import hoodies &amp; caps</a></p></div></section>
<main class="section"><div class="wrap">
<p class="note" role="status">Catalogue: {{ garment_counts["T-shirt"] }} T-shirt designs · {{ garment_counts["Hoodie"] }} hoodie designs · {{ garment_counts["Cap"] }} cap designs. Only published designs are orderable.</p>
{% if message %}<div class="notice" role="status">{{ message }}</div>{% endif %}
<div class="pane"><h2>Add MSJ design</h2><form method="post" action="{{ url_for('msj.admin_add') }}" enctype="multipart/form-data">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<div class="two"><div><label>Design title *</label><input name="title" required maxlength="120" placeholder="MSJ Classic"></div>
<div><label>Internal design code *</label><input name="code" required maxlength="30" placeholder="MSJ-CLASSIC"></div></div>
<label>Description</label><input name="description" maxlength="300" placeholder="Official cream artwork on deep green">
<label>Original artwork image (PNG, JPEG or WebP) *</label><input type="file" name="image" accept="image/png,image/jpeg,image/webp" required>
<p class="note">Upload only your authentic artwork or approved product photograph. Maximum 5 MB. We resize for the web without redesigning the artwork.</p>
<p class="note">Confirmed MSJ prices: T-shirt MK25,000 · Hoodie MK50,000 · Cap MK20,000. Pricing is calculated automatically for each order.</p>
<label>Available garment types (comma-separated) *</label><input name="garments" placeholder="T-shirt, Hoodie, Cap" required>
<div class="two"><div><label>Sizes (comma-separated) *</label><input name="sizes" value="S,M,L,XL,XXL,One Size" required></div>
<div><label>Suggested colours (optional)</label><input name="colours" placeholder="Black, White, Green"></div></div>
<p class="note">These colours are suggestions. Customers can request any colour, and IBROWS confirms availability individually.</p>
<button class="button" type="submit">Save unpublished design</button></form></div>
<div class="pane" style="margin-top:28px"><h2>Import your 11 MSJ T-shirt designs</h2>
<p class="note">Upload the three original MSJ mock-up sheets you shared earlier. We will crop each design directly from your originals—no replacement logos or invented graphics. Imported items start as private drafts for your approval.</p>
<form method="post" action="{{ url_for('msj.admin_import_sheets') }}" enctype="multipart/form-data"
onsubmit="if (!this.querySelector('input[name=three]').files.length &amp;&amp; !this.querySelector('input[name=four_a]').files.length &amp;&amp; !this.querySelector('input[name=four_b]').files.length) { window.alert('Choose at least one original MSJ design sheet before importing.'); return false; }">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<label>Classic / Script / Modern (3-shirt image)</label>
<input type="file" name="three" accept="image/png,image/jpeg,image/webp">
<label>Circle / Handwritten / Label / Retro Flow (4-shirt image)</label>
<input type="file" name="four_a" accept="image/png,image/jpeg,image/webp">
<label>Varsity / Stencil / Motion / Vertical (4-shirt image)</label>
<input type="file" name="four_b" accept="image/png,image/jpeg,image/webp">
<p class="note">Use the originals, not cropped screenshots. At least one sheet is required. Already imported designs are skipped safely.</p>
<button class="button" type="submit">Import MSJ original designs as drafts</button></form></div>
<section class="admin-merch-import" aria-labelledby="merch-import-title">
<h2 id="merch-import-title">Add MSJ hoodies &amp; caps from your phone</h2>
<p>Choose one or more original MSJ photos directly from your phone gallery. <strong>No ZIP needed.</strong> Match each photo to its labelled item below. Unselected items are skipped, and duplicates are not created.</p>
<form method="post" action="{{ url_for('msj.admin_import_merch_images') }}" enctype="multipart/form-data"
onsubmit="if(!Array.from(this.querySelectorAll('input[type=file]')).some(function(el){return el.files.length>0;})){window.alert('Choose at least one merchandise photo.');return false;}">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
{% for field,label,filename in merch_photo_fields %}
<label for="msj-photo-{{ field }}">{{ label }}</label>
<input id="msj-photo-{{ field }}" type="file" name="{{ field }}" accept="image/png,image/jpeg,image/webp">
{% endfor %}
<p class="note">PNG, JPG or WebP · up to 5 MB per image. Every photo is saved as a <strong>private draft</strong> with the confirmed price and sizes. Verify the photo matches its label before publishing.</p>
<button class="button" type="submit">Import selected photos as drafts</button>
</form>
<details style="margin-top:20px">
<summary style="cursor:pointer;font-weight:750;padding:8px 0">Or upload an original merchandise ZIP</summary>
<p class="note">Optional bulk import for your original five named mockup files. Use ZIP only if you already have one.</p>
<form method="post" action="{{ url_for('msj.admin_import_merch_zip') }}" enctype="multipart/form-data">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<label for="msj-merch-zip">Original merchandise ZIP (.zip, max 8 MB)</label>
<input id="msj-merch-zip" type="file" name="merch_zip" accept=".zip,application/zip" required>
<button class="button secondary" type="submit" style="margin-top:12px">Import ZIP as drafts</button>
</form></details></section>
<h2 style="margin-top:38px">Catalogue</h2>
<div class="bulk-panel" aria-label="MSJ catalogue publication controls">
<h3>Catalogue review &amp; publishing</h3>
<p><strong>{{ published_count }} published</strong> · <strong>{{ draft_count }} drafts</strong> · {{ products|length }} total.</p>
{% if draft_count > 0 %}<p>New drafts appear first in the catalogue below. Review each image, garment type, sizes and price before publishing. You can publish each design individually or publish all after reviewing.</p>{% endif %}
{% if draft_count > 0 %}
<form method="post" action="{{ url_for('msj.admin_bulk_publish') }}"
onsubmit="return window.confirm('Publish all {{ draft_count }} MSJ drafts? Only do this after reviewing the artwork, design names, sizes and prices. Published items immediately become visible and orderable by visitors.');">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<button class="button" type="submit">Publish All Drafts ({{ draft_count }})</button>
<span class="note">One confirmation publishes eligible unpublished designs only. Existing published designs remain unchanged.</span>
</form>
{% else %}
<p role="status">All {{ published_count }} designs are currently published. New imported artwork can be published in one action here.</p>
<button class="button" type="button" disabled aria-disabled="true">Publish All — No Drafts</button>
{% endif %}
</div>
{% if products %}<div class="table-wrap"><table class="catalog-table"><thead><tr><th>Design</th><th>Price</th><th>Status</th><th>Update</th></tr></thead><tbody>
{% for p in products %}<tr><td data-label="Design"><img src="{{ url_for('msj.design_image',design_id=p.id, v=p.image_revision[:12]) }}" width="110" alt=""><div><strong>{{ p.title }}</strong><br>{{ p.code }}</div></td>
<td data-label="Price">MK {{ '{:,.0f}'.format(p.price_mwk) }}</td><td data-label="Status"><strong>{{ 'Published' if p.published else 'Draft — needs approval' }}</strong></td>
<td data-label="Update"><form method="post" action="{{ url_for('msj.admin_toggle',design_id=p.id) }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<button class="button secondary" type="submit">{{ 'Unpublish' if p.published else 'Publish' }}</button></form>
<details style="margin-top:10px"><summary>Edit sizes, colours or artwork</summary><form method="post" action="{{ url_for('msj.admin_update',design_id=p.id) }}" enctype="multipart/form-data">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<label>Description</label><input name="description" maxlength="300" value="{{ p.description }}">
<label>Garments</label><input name="garments" value="{{ p.garments }}" required>
<label>Sizes</label><input name="sizes" value="{{ p.sizes }}" required>
<label>Suggested colours (optional)</label><input name="colours" value="{{ p.colours }}">
<p class="note">Customers may request any colour even if it is not listed above.</p>
<label>Replace artwork (optional)</label><input type="file" name="image" accept="image/png,image/jpeg,image/webp">
<button class="button secondary" type="submit" style="margin-top:8px">Save changes</button></form></details>
</td></tr>{% endfor %}
</tbody></table></div>{% else %}<p>No designs yet. Add the real MSJ Classic and Varsity artwork above.</p>{% endif %}
<h2 style="margin-top:38px">Customer orders</h2>
{% if orders %}<div class="table-wrap"><table><thead><tr><th>Reference</th><th>Customer</th><th>Selection</th><th>Estimated</th><th>Status</th></tr></thead><tbody>
{% for o in orders %}<tr><td><strong>{{ o.reference }}</strong><br><small>{{ o.created_at }}</small></td>
<td>{{ o.buyer_name }}<br>{{ o.phone }}<br>{{ o.email or '' }}<br>{{ o.location }}</td>
<td>{{ o.title }}<br>{{ o.garment }} · {{ o.size }} · {{ o.colour }}<br>Qty {{ o.quantity }}<br>{{ o.notes }}</td>
<td>MK {{ '{:,.0f}'.format(o.estimated_total) }}<br><small>Admin email: {{ o.notification_status }}</small>
{% if o.status == 'COLOUR_UNAVAILABLE' %}<br><small><strong>Buyer alert:</strong> {{ o.colour_alert_status }}</small>{% endif %}</td>
<td><form method="post" action="{{ url_for('msj.admin_status',order_id=o.id) }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<select name="status" aria-label="Update order status">
{% for status in ['NEW','CONTACTED','COLOUR_UNAVAILABLE','QUOTED','CONFIRMED','IN_PRODUCTION','FULFILLED','CANCELLED'] %}
<option value="{{ status }}" {% if o.status == status %}selected{% endif %}>{{ status.replace('_',' ').title() }}</option>{% endfor %}
</select><button class="button secondary" type="submit">Save status</button></form>
{% if o.notification_status == 'FAILED' %}
<form method="post" action="{{ url_for('msj.admin_retry_order_notification',order_id=o.id) }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<button class="button secondary" type="submit">Retry internal order email</button></form>
{% endif %}
{% if o.status == 'COLOUR_UNAVAILABLE' %}
{% if o.colour_alert_status in ['MANUAL_REQUIRED','FAILED'] %}
<p class="note">{% if o.email %}Email notice failed. Please retry or contact the buyer directly.{% else %}No email provided: please notify the buyer by phone or WhatsApp.{% endif %}</p>
<a class="button secondary" href="tel:{{ o.phone }}" style="margin:4px 0">Call customer</a>
<form method="post" action="{{ url_for('msj.admin_colour_contacted',order_id=o.id) }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<button class="button secondary" type="submit">Mark manually notified</button></form>
{% endif %}
{% if o.colour_alert_status == 'FAILED' and o.email %}
<form method="post" action="{{ url_for('msj.admin_retry_colour_notice',order_id=o.id) }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<button class="button secondary" type="submit">Retry buyer email</button></form>
{% endif %}
{% endif %}</td></tr>{% endfor %}
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
                    colour_alert_status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
                    colour_alert_error VARCHAR(160),
                    colour_alert_sent_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
                cur.execute("ALTER TABLE msj_merch_orders ADD COLUMN IF NOT EXISTS colour_alert_status VARCHAR(24) NOT NULL DEFAULT 'PENDING'")
                cur.execute("ALTER TABLE msj_merch_orders ADD COLUMN IF NOT EXISTS colour_alert_error VARCHAR(160)")
                cur.execute("ALTER TABLE msj_merch_orders ADD COLUMN IF NOT EXISTS colour_alert_sent_at TIMESTAMPTZ")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_msj_orders_time ON msj_merch_orders (created_at DESC)")
                repair_result=repair_ms_j_misassigned_sheet_images(cur)
                if repair_result=="repaired":
                    app.logger.info("MSJ artwork alignment fixed for eight original 4-shirt designs.")
                elif repair_result=="changed_skip":
                    app.logger.warning("MSJ artwork differs from known originals; guarded correction skipped.")
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
        sql="SELECT id,code,title,description,price_mwk,garments,sizes,colours,published,md5(image_bytes) AS image_revision FROM msj_merch_designs"
        if published_only:sql+=" WHERE published=TRUE"
        sql+=" ORDER BY id ASC"
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                names=[x.name for x in cur.description]
                return [dict(zip(names,r)) for r in cur.fetchall()]

    def product_by_id(ident,public=True):
        connect_setup()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT id,code,title,description,price_mwk,garments,sizes,colours,published,
                    md5(image_bytes) AS image_revision FROM msj_merch_designs WHERE id=%s"""+(" AND published=TRUE" if public else ""), (ident,))
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
        garment_filter=(request.args.get("garment") or "").strip()
        if garment_filter not in ("T-shirt","Hoodie","Cap"): garment_filter=""
        all_products=product_rows()
        products=[p for p in all_products if garment_filter in csv_choices(p["garments"])] if garment_filter else all_products
        return render(CATALOG_TEMPLATE,title="MSJ Clothing Collection",products=products,
                      garment_filter=garment_filter,
                      hoodies_listed=any("Hoodie" in csv_choices(p["garments"]) for p in all_products))

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
        response.headers["Cache-Control"]="public, max-age=600" if row[2] else "private, no-store"
        return response

    @bp.route("/msj/design/<int:design_id>",methods=["GET","POST"])
    def order_design(design_id):
        p=product_by_id(design_id)
        if not p:abort(404)
        garment_choices=csv_choices(p["garments"])
        size_choices=[s for s in MSJ_APPAREL_SIZES if s in csv_choices(p["sizes"])]
        if "Cap" in garment_choices: size_choices.append(MSJ_CAP_SIZE)
        colour_choices=csv_choices(p["colours"])
        if request.method=="GET":
            return render(ORDER_TEMPLATE,title=p["title"],design=p,garments=garment_choices,
                          sizes=size_choices,colours=colour_choices,csrf_token=public_csrf("MSJ_ORDER"),error="",garment_prices=MSJ_GARMENT_PRICES,old={})
        supplied=str(request.form.get("csrf_token") or "")
        if not supplied or not secrets.compare_digest(supplied,public_csrf("MSJ_ORDER")):abort(403)
        if request.form.get("fax_number"):abort(400)
        try:
            garment=request.form.get("garment","")[:50]
            size=request.form.get("size","")[:24]
            colour=" ".join((request.form.get("colour") or "").replace(chr(0),"").split())[:50]
            if garment not in garment_choices or garment not in MSJ_GARMENT_PRICES:
                raise ValueError("Select a valid garment.")
            valid_sizes = (MSJ_CAP_SIZE,) if garment == "Cap" else MSJ_APPAREL_SIZES
            if size not in size_choices or size not in valid_sizes:
                raise ValueError("Select an available garment size.")
            if len(colour)<2 or not any(c.isalpha() for c in colour):
                raise ValueError("Enter the colour you prefer.")
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
                         SELECT %s,id,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                         FROM msj_merch_designs WHERE id=%s AND published=TRUE
                         RETURNING id""", (str(token),buyer_name,phone,email or None,location,
                                garment,size,colour,quantity,notes,MSJ_GARMENT_PRICES[garment]*quantity,design_id))
                    inserted=cur.fetchone()
                    if not inserted:raise ValueError("That design is currently unavailable.")
                    oid=inserted[0]
                    ref=f"MSJ-{datetime.utcnow().year}-{oid:05d}"
                    cur.execute("UPDATE msj_merch_orders SET reference=%s WHERE id=%s",(ref,oid))
                conn.commit()
            try:
                send_notification(oid,ref,p,garment,size,colour,quantity,buyer_name,phone,location)
            except Exception:
                # Order was already committed. Do not tell the customer it failed or
                # invite a duplicate submission just because an alert failed.
                app.logger.exception("MSJ order %s saved but staff notification failed",ref)
            return redirect(url_for("msj.complete",token=token),code=303)
        except (ValueError,TypeError):
            return render(ORDER_TEMPLATE,title=p["title"],design=p,garments=garment_choices,
                 sizes=size_choices,colours=colour_choices,csrf_token=public_csrf("MSJ_ORDER"),
                 garment_prices=MSJ_GARMENT_PRICES,old=request.form,error="Please check your selected garment, contact details, quantity and consent."),400

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
                cur.execute("""SELECT o.reference,d.title,o.garment,o.colour,o.size,o.quantity,o.status
                    FROM msj_merch_orders o JOIN msj_merch_designs d ON d.id=o.design_id
                    WHERE o.token=%s""",(str(token),))
                r=cur.fetchone()
        if not r:abort(404)
        return render(COMPLETE_TEMPLATE,title="Order request received",reference=r[0],
                      design_title=r[1],garment=r[2],colour=r[3],size=r[4],quantity=r[5],order_status=r[6])

    @bp.route("/admin/msj",methods=["GET"])
    @admin_required
    def admin_index():
        connect_setup()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT o.id,o.reference,o.created_at,o.buyer_name,o.phone,o.email,o.location,
                    o.garment,o.size,o.colour,o.quantity,o.notes,o.estimated_total,o.status,
                    o.notification_status,o.colour_alert_status,d.title FROM msj_merch_orders o
                    JOIN msj_merch_designs d ON d.id=o.design_id
                    ORDER BY o.id DESC LIMIT 200""")
                keys=[x.name for x in cur.description]
                orders=[dict(zip(keys,r)) for r in cur.fetchall()]
        products=product_rows(False)
        # Review unapproved uploads first, especially on narrow mobile screens.
        products.sort(key=lambda p:(bool(p["published"]),-int(p["id"])))
        published_count=sum(1 for p in products if p["published"])
        garment_counts={g:sum(g in csv_choices(p["garments"]) for p in products) for g in MSJ_GARMENT_PRICES}
        return render(ADMIN_TEMPLATE,title="MSJ Admin",products=products,garment_counts=garment_counts,
                      published_count=published_count,draft_count=len(products)-published_count,
                      orders=orders,merch_photo_fields=MSJ_MERCH_PHOTO_FIELDS,csrf_token=admin_csrf(),
                      message=request.args.get("message","")[:180])

    def insert_merch_drafts(chosen):
        """Create unpublished, conflict-safe MSJ drafts; never overwrite existing artwork."""
        inserted=skipped=0
        connect_setup()
        with get_db() as conn:
            with conn.cursor() as cur:
                for (code,title,garment,colour,description),image,mime in chosen:
                    sizes="One Size" if garment=="Cap" else ",".join(MSJ_APPAREL_SIZES)
                    price=MSJ_GARMENT_PRICES[garment]
                    cur.execute("""INSERT INTO msj_merch_designs
                        (code,title,description,price_mwk,garments,sizes,colours,
                         image_bytes,image_mime,published)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE)
                        ON CONFLICT (code) DO NOTHING RETURNING id""",
                        (code,title,description,price,garment,sizes,colour,image,mime))
                    if cur.fetchone():inserted+=1
                    else:skipped+=1
            conn.commit()
        return inserted,skipped

    @bp.route("/admin/msj/designs/import-merch-images",methods=["POST"])
    @admin_required
    def admin_import_merch_images():
        """Accept one or several phone-gallery images, assigned to explicit product slots."""
        validate_admin_csrf()
        try:
            chosen=[]
            for field,label,filename in MSJ_MERCH_PHOTO_FIELDS:
                uploaded=request.files.get(field)
                if not uploaded or not uploaded.filename:continue
                image,mime=image_sanitize(uploaded)
                chosen.append((MSJ_MERCH_SPECS[filename],image,mime))
            if not chosen:
                raise ValueError("Choose at least one original merchandise photo (PNG, JPG or WebP).")
            inserted,skipped=insert_merch_drafts(chosen)
            msg=(f"Imported {inserted} MSJ photos as private drafts; "
                 f"{skipped} already existed. Review your pictures before publishing.")
        except (ValueError,TypeError,UnidentifiedImageError,OSError) as exc:
            msg="Image import error: "+str(exc)[:150]
        return redirect(url_for("msj.admin_index",message=msg))

    @bp.route("/admin/msj/designs/import-merch-zip",methods=["POST"])
    @admin_required
    def admin_import_merch_zip():
        """Use only the user's known uploaded original mockup filenames; never unpack ZIP paths."""
        from zipfile import ZipFile, BadZipFile
        from types import SimpleNamespace
        validate_admin_csrf()
        try:
            uploaded=request.files.get("merch_zip")
            if not uploaded or not uploaded.filename or not uploaded.filename.lower().endswith(".zip"):
                raise ValueError("Select your original MSJ merchandise ZIP file.")
            raw=uploaded.stream.read(8*1024*1024+1)
            if len(raw)>8*1024*1024:
                raise ValueError("The ZIP file must not exceed 8 MB.")
            chosen=[]
            with ZipFile(io.BytesIO(raw)) as archive:
                infos=archive.infolist()
                if len(infos)>30:raise ValueError("The ZIP has too many files.")
                for info in infos:
                    if info.filename not in MSJ_MERCH_SPECS:continue
                    if info.file_size>5*1024*1024 or info.file_size<1000:
                        raise ValueError("A merchandise photo has an invalid size.")
                    asset=archive.read(info)
                    if len(asset)>5*1024*1024:
                        raise ValueError("A merchandise photo exceeds the 5 MB limit.")
                    image,mime=image_sanitize(SimpleNamespace(filename=info.filename,stream=io.BytesIO(asset)))
                    chosen.append((MSJ_MERCH_SPECS[info.filename],image,mime))
            if not chosen:raise ValueError("No recognized original MSJ merchandise images found in ZIP.")
            inserted,skipped=insert_merch_drafts(chosen)
            msg=f"Imported {inserted} original MSJ merchandise designs as drafts; {skipped} already existed. Review before publishing."
        except (BadZipFile,ValueError,TypeError,UnidentifiedImageError,OSError) as exc:
            msg="Import error: "+str(exc)[:160]
        return redirect(url_for("msj.admin_index",message=msg))

    @bp.route("/admin/msj/designs/import-sheets",methods=["POST"])
    @admin_required
    def admin_import_sheets():
        """Crop exactly the user's original 3-shirt and 2x2 mockup sheets.

        The source image is never redrawn. Admin reviews each result before
        clicking Publish, and duplicate design codes are safely ignored.
        """
        validate_admin_csrf()
        sheet_names={
            "three":("Classic","Script","Modern"),
            "four_a":("Circle","Handwritten","Label","Retro Flow"),
            "four_b":("Varsity","Stencil","Motion","Vertical"),
        }
        processed=[]
        try:
            for field,names in sheet_names.items():
                upload=request.files.get(field)
                if not upload or not upload.filename:continue
                raw=upload.stream.read(8*1024*1024+1)
                if len(raw)>8*1024*1024:raise ValueError("A design sheet must be 8 MB or smaller.")
                with Image.open(io.BytesIO(raw)) as im:
                    if im.format not in ("PNG","JPEG","WEBP"):
                        raise ValueError("Please use an original PNG, JPEG or WebP design sheet.")
                    if im.width*im.height>20_000_000:raise ValueError("Design sheet dimensions are too large.")
                    im=ImageOps.exif_transpose(im).convert("RGB")
                    w,h=im.size
                    if field=="three":
                        if w/h<1.3 or w/h>1.9:raise ValueError("The 3-shirt design sheet must be the wide 3-column image.")
                        crop_boxes=[(round(w*j/3),0,round(w*(j+1)/3),round(h*.85)) for j in range(3)]
                    else:
                        if w/h<.9 or w/h>1.3:raise ValueError("The 4-shirt sheet must be the 2x2 image.")
                        crop_boxes=[]
                        for row in range(2):
                            for col in range(2):
                                x0=round(w*col/2); x1=round(w*(col+1)/2)
                                y0=round(h*row/2); y1=round(h*(row+1)/2)
                                crop_boxes.append((x0,y0,x1,round(y0+(y1-y0)*.89)))
                    for label,box in zip(names,crop_boxes):
                        thumbnail=im.crop(box)
                        thumbnail.thumbnail((960,960),Image.Resampling.LANCZOS)
                        out=io.BytesIO()
                        thumbnail.save(out,format="JPEG",quality=88,optimize=True)
                        processed.append((label,out.getvalue()))
            if not processed:raise ValueError("Choose at least one original MSJ design sheet.")
            connect_setup()
            inserted=skipped=0
            with get_db() as conn:
                with conn.cursor() as cur:
                    for label,asset in processed:
                        code="MSJ-"+label.upper().replace(" ","-")
                        cur.execute("""INSERT INTO msj_merch_designs
                            (code,title,description,price_mwk,garments,sizes,colours,image_bytes,image_mime,published)
                            VALUES(%s,%s,%s,%s,'T-shirt','S,M,L,XL,XXL',%s,%s,'image/jpeg',FALSE)
                            ON CONFLICT (code) DO NOTHING RETURNING id""",
                            (code,"MSJ "+label,
                             "Mulungu Si Jemusi "+label+" T-shirt from approved original artwork sheet.",
                             MSJ_GARMENT_PRICES["T-shirt"],
                             "Black,White,Cream,Green,Grey,Navy,Burgundy",asset))
                        if cur.fetchone():inserted+=1
                        else:skipped+=1
                conn.commit()
            message=(f"Imported {inserted} original MSJ designs as unpublished drafts."
                     + (f" Skipped {skipped} designs already on record." if skipped else "")
                     + " Review every crop and publish designs you approve.")
        except (ValueError,UnidentifiedImageError,OSError) as exc:
            message="Import error: "+str(exc)[:160]
        return redirect(url_for("msj.admin_index",message=message))

    @bp.route("/admin/msj/designs/add",methods=["POST"])
    @admin_required
    def admin_add():
        validate_admin_csrf()
        try:
            title=str(request.form.get("title","")).strip()[:120]
            code=str(request.form.get("code","")).strip().upper()[:30]
            desc=str(request.form.get("description","")).strip()[:300]
            garments=",".join(csv_choices(request.form.get("garments","")))
            sizes=",".join(csv_choices(request.form.get("sizes","")))
            colours=",".join(csv_choices(request.form.get("colours","")))
            if not title or not re.fullmatch(r"[A-Z0-9_-]{3,30}",code):
                raise ValueError("Enter a design title and unique code.")
            price=msj_product_options(garments)
            allowed_sizes=set(MSJ_APPAREL_SIZES)|{MSJ_CAP_SIZE}
            if not sizes or any(x not in allowed_sizes for x in csv_choices(sizes)):
                raise ValueError("Set confirmed sizes (S, M, L, XL, XXL or One Size).")
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

    @bp.route("/admin/msj/designs/publish-all",methods=["POST"])
    @admin_required
    def admin_bulk_publish():
        """Publish eligible draft products with explicit admin confirmation and CSRF."""
        validate_admin_csrf()
        connect_setup()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM msj_merch_designs WHERE published=FALSE")
                total_drafts=int(cur.fetchone()[0] or 0)
                cur.execute("""UPDATE msj_merch_designs
                    SET published=TRUE WHERE published=FALSE
                      AND price_mwk>0 AND octet_length(image_bytes)>0
                      AND btrim(title)<>'' AND btrim(garments)<>''
                      AND btrim(sizes)<>''
                    RETURNING id""")
                count=len(cur.fetchall())
            conn.commit()
        if total_drafts==0:
            msg="All MSJ designs were already published. No changes made."
        elif count==total_drafts:
            msg=f"Published {count} MSJ designs. All drafts are now visible to visitors."
        else:
            msg=(f"Published {count} of {total_drafts} MSJ drafts. "
                 f"{total_drafts-count} still need complete artwork, pricing or garment details.")
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

    @bp.route("/admin/msj/designs/<int:design_id>/update",methods=["POST"])
    @admin_required
    def admin_update(design_id):
        validate_admin_csrf()
        p=product_by_id(design_id,public=False)
        if not p:abort(404)
        try:
            description=str(request.form.get("description","")).strip()[:300]
            garments=",".join(csv_choices(request.form.get("garments","")))
            sizes=",".join(csv_choices(request.form.get("sizes","")))
            colours=",".join(csv_choices(request.form.get("colours","")))
            price=msj_product_options(garments)
            allowed_sizes=set(MSJ_APPAREL_SIZES)|{MSJ_CAP_SIZE}
            if not sizes or any(x not in allowed_sizes for x in csv_choices(sizes)):
                raise ValueError("Set confirmed sizes (S, M, L, XL, XXL or One Size).")
            upload=request.files.get("image")
            new_artwork=image_sanitize(upload) if upload and upload.filename else None
            with get_db() as conn:
                with conn.cursor() as cur:
                    if new_artwork:
                        cur.execute("""UPDATE msj_merch_designs
                            SET price_mwk=%s,description=%s,garments=%s,sizes=%s,colours=%s,
                            image_bytes=%s,image_mime=%s,published=FALSE WHERE id=%s""",
                            (price,description,garments,sizes,colours,
                             new_artwork[0],new_artwork[1],design_id))
                    else:
                        cur.execute("""UPDATE msj_merch_designs
                            SET price_mwk=%s,description=%s,garments=%s,sizes=%s,colours=%s
                            WHERE id=%s""",
                            (price,description,garments,sizes,colours,design_id))
                conn.commit()
            msg="Design updated. Replaced artwork is unpublished until you reapprove it." if new_artwork else "Price and options updated."
        except (ValueError,TypeError) as exc:
            msg=str(exc)
        return redirect(url_for("msj.admin_index",message=msg))

    def send_customer_colour_unavailable(order_id):
        """On admin stock review, email buyer if available, otherwise require manual contact."""
        connect_setup()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT reference,email,buyer_name,colour,status,colour_alert_status
                    FROM msj_merch_orders WHERE id=%s""",(order_id,))
                row=cur.fetchone()
        if not row or row[4] != "COLOUR_UNAVAILABLE":
            return "Order is not awaiting a colour-availability notice."
        reference,email,buyer_name,colour,_,previous=row
        if previous in {"SENT","CONTACTED_MANUALLY","SENDING"}:
            return "A colour notice was already sent or is being processed."
        if not email:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""UPDATE msj_merch_orders
                        SET colour_alert_status='MANUAL_REQUIRED',
                        colour_alert_error='No buyer email. Phone or WhatsApp follow-up required.',
                        updated_at=NOW()
                        WHERE id=%s AND colour_alert_status NOT IN ('SENT','CONTACTED_MANUALLY')""",(order_id,))
                conn.commit()
            return "No email supplied: call or WhatsApp the buyer before continuing."
        # Claim this notification atomically so simultaneous admin actions cannot duplicate it.
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE msj_merch_orders SET colour_alert_status='SENDING',updated_at=NOW()
                    WHERE id=%s AND status='COLOUR_UNAVAILABLE'
                    AND colour_alert_status IN ('PENDING','FAILED','MANUAL_REQUIRED') RETURNING id""",(order_id,))
                claimed=cur.fetchone() is not None
            conn.commit()
        if not claimed:return "A colour notice was already sent or is being processed."
        key=os.getenv("BREVO_API_KEY","").strip()
        sender=os.getenv("BREVO_SENDER_EMAIL","").strip() or "info@ibrowsenterprise.com"
        sent=False
        error="Brevo not configured"
        if key:
            try:
                response=requests.post("https://api.brevo.com/v3/smtp/email",
                    headers={"api-key":key,"Content-Type":"application/json"},
                    json={"sender":{"email":sender,"name":"IBROWS Enterprise / MSJ"},
                          "to":[{"email":email}],
                          "subject":f"MSJ order {reference}: Preferred colour unavailable",
                          "textContent":(
                              f"Hello {buyer_name},\n\n"
                              f"We have checked your Mulungu Si Jemusi (MSJ) order {reference}.\n"
                              f"Unfortunately, your chosen colour ({colour}) is not currently available.\n"
                              "Please reply to discuss another colour or cancel the request. "
                              "No payment or production will be arranged until we agree on an alternative.\n\n"
                              "IBROWS Enterprise | info@ibrowsenterprise.com"
                          )},timeout=8)
                sent=200<=response.status_code<300
                error="" if sent else f"Brevo HTTP {response.status_code}"
            except Exception as exc:
                error=type(exc).__name__
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE msj_merch_orders SET colour_alert_status=%s,
                    colour_alert_error=%s,
                    colour_alert_sent_at=CASE WHEN %s THEN NOW() ELSE colour_alert_sent_at END,
                    updated_at=NOW() WHERE id=%s AND colour_alert_status='SENDING'""",
                    ("SENT" if sent else "FAILED",None if sent else error,sent,order_id))
            conn.commit()
        if sent:return "Colour-unavailable email accepted by Brevo (recipient delivery not independently confirmed)."
        return "Email notice failed. Please contact buyer directly or retry."

    @bp.route("/admin/msj/orders/<int:order_id>/notification-retry",methods=["POST"])
    @admin_required
    def admin_retry_order_notification(order_id):
        """Retry only a failed internal MSJ order alert, never the buyer's order."""
        validate_admin_csrf()
        connect_setup()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT o.reference,d.title,o.garment,o.size,o.colour,
                    o.quantity,o.buyer_name,o.phone,o.location
                    FROM msj_merch_orders o JOIN msj_merch_designs d ON d.id=o.design_id
                    WHERE o.id=%s""",(order_id,))
                row=cur.fetchone()
        if not row:abort(404)
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE msj_merch_orders
                    SET notification_status='SENDING',updated_at=NOW()
                    WHERE id=%s AND notification_status='FAILED'
                    RETURNING id""",(order_id,))
                claimed=cur.fetchone() is not None
            conn.commit()
        if not claimed:
            return redirect(url_for("msj.admin_index",message="Only failed internal order emails can be retried."))
        ref,title,garment,size,colour,quantity,buyer_name,phone,location=row
        try:
            send_notification(order_id,ref,{"title":title},garment,size,colour,quantity,buyer_name,phone,location)
        except Exception:
            # If Brevo accepted an email but recording the result failed, retrying
            # could deliver duplicates. Require manual checking instead.
            app.logger.exception("MSJ order %s: uncertain admin email retry delivery",ref)
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""UPDATE msj_merch_orders
                        SET notification_status='REVIEW_REQUIRED',
                            notification_error='Check Brevo/inbox before any manual resend',
                            updated_at=NOW()
                        WHERE id=%s AND notification_status='SENDING'""",(order_id,))
                conn.commit()
            return redirect(url_for("msj.admin_index",message="Email delivery uncertain. Check Brevo and inbox before any manual resend."))
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT notification_status FROM msj_merch_orders WHERE id=%s",(order_id,))
                final=cur.fetchone()
        message=("Internal order email accepted by provider; inbox delivery not independently confirmed."
                 if final and final[0]=="SENT" else
                 "Internal email attempt failed. Confirm Brevo settings and retry from this page.")
        return redirect(url_for("msj.admin_index",message=message))

    @bp.route("/admin/msj/orders/<int:order_id>/colour-contacted",methods=["POST"])
    @admin_required
    def admin_colour_contacted(order_id):
        validate_admin_csrf()
        connect_setup()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE msj_merch_orders SET colour_alert_status='CONTACTED_MANUALLY',
                    colour_alert_error=NULL, updated_at=NOW()
                    WHERE id=%s AND status='COLOUR_UNAVAILABLE'
                    AND colour_alert_status IN ('MANUAL_REQUIRED','FAILED') RETURNING id""",(order_id,))
                updated=cur.fetchone()
            conn.commit()
        if not updated:abort(400)
        return redirect(url_for("msj.admin_index",message="Manual customer colour notification recorded."))

    @bp.route("/admin/msj/orders/<int:order_id>/colour-email-retry",methods=["POST"])
    @admin_required
    def admin_retry_colour_notice(order_id):
        validate_admin_csrf()
        msg=send_customer_colour_unavailable(order_id)
        return redirect(url_for("msj.admin_index",message=msg))

    @bp.route("/admin/msj/orders/<int:order_id>/status",methods=["POST"])
    @admin_required
    def admin_status(order_id):
        validate_admin_csrf()
        allowed={"NEW","CONTACTED","COLOUR_UNAVAILABLE","QUOTED","CONFIRMED","IN_PRODUCTION","FULFILLED","CANCELLED"}
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
        message=("Order status saved. Verify payments separately."
                 if status!="COLOUR_UNAVAILABLE" else send_customer_colour_unavailable(order_id))
        return redirect(url_for("msj.admin_index",message=message))

    # Security header for every IBROWS route, including admin and error responses.
    # This is safe for first-party images, forms, PDFs and the WhatsApp webhook.
    @app.after_request
    def ibrows_nosniff_response_header(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    app.register_blueprint(bp)
