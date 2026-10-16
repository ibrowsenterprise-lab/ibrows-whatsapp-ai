"""Add MSJ merchandise entry to Branding without rewriting existing templates."""
import ast
from pathlib import Path
root=Path(__file__).resolve().parent.parent
app_path=root/"app.py"
s=app_path.read_text(encoding="utf-8")
reg="from msj_store import register_msj_store\nregister_msj_store(app, get_db, get_public_service_csrf, get_csrf_token, validate_csrf, admin_required)\n\n"
shop_segment="""{% if service_key=='DESIGN_BRANDING' %}
<section class="msj-merch" aria-labelledby="msj-title" style="background:#f8f3e9;padding:55px 0;border-top:1px solid #eadfd0;border-bottom:1px solid #eadfd0">
<div class="wrap" style="display:grid;grid-template-columns:1fr;gap:15px">
<span class="eyebrow">IBROWS Enterprise · Clothing label</span>
<h2 id="msj-title" style="font-family:Georgia,serif;font-size:clamp(30px,5vw,48px);line-height:1.1;color:#193b2c">Mulungu Si Jemusi <span style="color:#6c2436">(MSJ)</span></h2>
<p style="max-width:720px;color:#4a5c53;font-size:1.05rem">Wear the message. Explore our genuine MSJ clothing-artwork collection, choose a design and request the garment, colour, size and quantity you want.</p>
<p style="margin:0;display:flex;gap:12px;flex-wrap:wrap"><a class="btn primary" href="/msj">Explore MSJ Collection &amp; Order</a>
{% if session.get('admin_authenticated') %}<a class="btn" href="/admin/msj">Manage MSJ Merch</a>{% endif %}</p>
<p style="margin:0;font-size:.84rem;color:#6b6d67">Orders are reviewed before stock, pricing, delivery or payment is confirmed. No automatic online charges.</p>
</div></section>
{% endif %}
"""
if 'register_msj_store(app, get_db' in s:
    print("MSJ integration already applied")
    raise SystemExit(0)
marker="{% if service_key=='LANDSCAPING' %}"
assert s.count(marker)==1,("Branding template insertion marker count",s.count(marker))
s=s.replace(marker,shop_segment+marker,1)
tree=ast.parse(s)
defs={n.name for n in tree.body if isinstance(n,ast.FunctionDef)}
for name in ('get_db','get_public_service_csrf','get_csrf_token','validate_csrf','admin_required'):
    assert name in defs,name
main_nodes=[n for n in tree.body if isinstance(n,ast.If) and isinstance(n.test,ast.Compare)
            and isinstance(n.test.left,ast.Name) and n.test.left.id=='__name__']
lines=s.splitlines(keepends=True)
if main_nodes:
    n=main_nodes[-1]
    lines.insert(n.lineno-1,reg)
else:
    lines.append('\n'+reg)
out=''.join(lines)
assert out.count('register_msj_store(app, get_db')==1
assert out.count('href="/msj"')>=1
compile(out,str(app_path),"exec")
app_path.write_text(out,encoding="utf-8")
print("PASS MSJ added to Branding tab; blueprint registered and source compiles")
