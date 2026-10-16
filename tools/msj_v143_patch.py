"""Apply the second half of the V143 mobile ordering layout patch safely."""
from pathlib import Path

path=Path("msj_store.py")
src=path.read_text(encoding="utf-8")
if "V143_SUBTOTAL_READY" in src:
    print("Already applied V143")
    raise SystemExit(0)

def one(old,new):
    global src
    count=src.count(old)
    assert count==1,(old[:80],count)
    src=src.replace(old,new,1)

one(
    '<small class="note">Type any colour you prefer. Listed colours are suggestions, not guaranteed stock. If we cannot supply your colour, we will notify you.</small>',
    '<p class="order-help">Any colour is welcome. We will contact you if it is unavailable.</p>'
)
one(
    '<p class="note">T-shirt MK25,000 · Hoodie MK50,000 · Cap MK20,000. The order estimate uses the selected garment and quantity. Delivery cost and availability are confirmed separately before accepting payment.</p>',
    '''<div class="order-total" aria-live="polite">
<div><strong>Estimated subtotal</strong><p class="order-help">Excludes delivery · No payment now</p></div>
<strong id="order-subtotal">MK {{ '{:,.0f}'.format(garment_prices[garments[0]]) }}</strong>
</div>'''
)
one(
    '<label><input type="checkbox" name="consent" value="1" required> I agree that IBROWS may use my details to respond to this merchandise request.</label>',
    '''<label class="order-consent"><input type="checkbox" name="consent" value="1" required
{% if old.get('consent')=='1' %}checked{% endif %}>
<span>I agree that IBROWS may use my contact details to respond to this order request.</span></label>'''
)
one(
    '<p class="note">No payment is collected at this stage. IBROWS will verify your colour request and contact you before confirming an order. If the colour is unavailable, you will be notified by email when provided; otherwise, our team will contact you by telephone or WhatsApp.</p>',
    '<p class="order-help">IBROWS checks size and colour before confirming production, delivery or payment.</p>'
)
one(
    '<label for="notes">Notes or custom instructions (optional)</label><textarea id="notes" name="notes" maxlength="1200" placeholder="Preferred fit, delivery details or questions"></textarea>',
    '''<details class="order-extras" {% if old.get('notes') %}open{% endif %}>
<summary>Special instructions (optional)</summary>
<label for="notes">Order notes</label>
<textarea id="notes" name="notes" maxlength="1200" placeholder="Preferred fit, delivery questions or other details">{{ old.get('notes','') }}</textarea>
</details>'''
)
one(
    'sizes=size_choices,colours=colour_choices,csrf_token=public_csrf("MSJ_ORDER"),error="")',
    'sizes=size_choices,colours=colour_choices,csrf_token=public_csrf("MSJ_ORDER"),error="",garment_prices=MSJ_GARMENT_PRICES,old={})'
)
one(
    'sizes=size_choices,colours=colour_choices,csrf_token=public_csrf("MSJ_ORDER"),\n                 error=',
    'sizes=size_choices,colours=colour_choices,csrf_token=public_csrf("MSJ_ORDER"),\n                 garment_prices=MSJ_GARMENT_PRICES,old=request.form,error='
)
for field in ("buyer_name","phone","email","location"):
    token='name="'+field+'"'
    assert src.count(token)>=1,field
    # Insert value attribute on the customer-facing order form only.
    import re
    before=src.index("ORDER_TEMPLATE=")
    after=src.index("COMPLETE_TEMPLATE=")
    order=src[before:after]
    pat=r'(<input [^>]*name="'+field+r'"[^>]*)(>)'
    order,count=re.subn(pat,lambda m:m.group(1)+' value="{{ old.get(\''+field+'\',\'\') }}"'+m.group(2),order,count=1)
    assert count==1,field
    src=src[:before]+order+src[after:]
one(
    'name="colour" type="text" list="msj-colour-ideas" maxlength="50" placeholder=',
    'name="colour" type="text" list="msj-colour-ideas" maxlength="50" value="{{ old.get(\'colour\',\'\') }}" placeholder='
)
one(
    'id="quantity" name="quantity" type="number" value="1" min="1" max="30" required',
    'id="quantity" name="quantity" type="number" value="{{ old.get(\'quantity\',\'1\') }}" min="1" max="30" required'
)
one(
    '{% for v in sizes %}<option value="{{ v }}">{{ v }}</option>{% endfor %}</select></div></div>',
    '{% for v in sizes %}<option value="{{ v }}" {% if old.get(\'size\')==v %}selected{% endif %}>{{ v }}</option>{% endfor %}</select></div></div>'
)
ending='</div></div></div></main>""" + BASE_END\n\nCOMPLETE_TEMPLATE='
assert src.count(ending)==1
javascript='''</div></div></div></main>
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

COMPLETE_TEMPLATE='''
src=src.replace(ending,javascript)
compile(src,"msj_store.py","exec")
path.write_text(src,encoding="utf-8")
print("PASS: V143 mobile form, dynamic subtotal, validated price data and form retention")
