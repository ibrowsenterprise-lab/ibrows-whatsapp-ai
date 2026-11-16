"""Munda Watch pilot pages and field intake validation."""
from datetime import date

from agro_marketplace_ui import START, END

PATH = "/agriculture/munda-watch"
ACTIONS = {
    "check": "Check my area",
    "register": "Register a field",
    "report": "Report a field problem",
}
CROPS = ("Maize", "Groundnuts", "Soya", "Rice")
WATER_SOURCES = ("Rain-fed", "Irrigated", "Rain-fed and irrigated", "Other")
DISTRICTS = (
    "Balaka", "Blantyre", "Chikwawa", "Chiradzulu", "Chitipa", "Dedza", "Dowa",
    "Karonga", "Kasungu", "Likoma", "Lilongwe", "Machinga", "Mangochi", "Mchinji",
    "Mulanje", "Mwanza", "Mzimba", "Neno", "Nkhata Bay", "Nkhotakota", "Nsanje",
    "Ntcheu", "Ntchisi", "Phalombe", "Rumphi", "Salima", "Thyolo", "Zomba",
)


def whatsapp_reply(base_url):
    return "Munda Watch | IBROWS Agriculture\n\n" + "\n".join(
        f"{label}\n{base_url}{PATH}/{action}" for action, label in ACTIONS.items()
    )


def field_payload(action, form):
    district = form.get("district")
    crop = form.get("crop")
    if district not in DISTRICTS or crop not in CROPS:
        raise ValueError("Choose a district and one of the four pilot crops.")
    payload = {"request_type": ACTIONS[action], "district": district, "crop": crop}
    if action == "check":
        return payload
    locality = form.get("locality", "").strip()
    if not locality or len(locality) > 160:
        raise ValueError("Enter a village or field location of up to 160 characters.")
    payload["locality"] = locality
    if action == "register":
        try:
            planting_date = date.fromisoformat(form.get("planting_date", ""))
        except ValueError:
            raise ValueError("Enter a valid planting date.") from None
        water_source = form.get("water_source")
        if water_source not in WATER_SOURCES:
            raise ValueError("Choose a water source.")
        payload.update(planting_date=planting_date.isoformat(), water_source=water_source)
    else:
        problem = form.get("problem", "").strip()
        if not problem or len(problem) > 2000:
            raise ValueError("Describe the problem in up to 2,000 characters.")
        payload["problem"] = problem
    return payload


PAGE = START + """
<div class="page-heading">
  <a class="back-link" href="/agriculture">← Agriculture</a>
  <h1>Munda Watch</h1>
  <p class="intro">Weather information and field reports for maize, groundnuts, soya and rice.</p>
</div>
<nav class="form-actions" aria-label="Munda Watch">
  {% for key, label in actions.items() %}
    <a class="button secondary" href="{{ url_for('munda_watch_page', action=key) }}">{{ label }}</a>
  {% endfor %}
</nav>
{% if action %}
<section class="panel" style="margin-top:24px;max-width:760px">
  <h2>{{ actions[action] }}</h2>
  {% if error %}<p class="error" role="alert">{{ error }}</p>{% endif %}
  {% if reference %}
    <p role="status">Received by IBROWS. Your reference is <strong>{{ reference }}</strong>.</p>
  {% else %}
    <form method="{{ 'get' if action == 'check' else 'post' }}">
      {% if action != 'check' %}
        <input type="hidden" name="csrf_token" value="{{ csrf }}">
        <input class="honeypot" name="fax_number" tabindex="-1" autocomplete="off" aria-hidden="true">
      {% endif %}
      <div class="form-grid">
        {% for name, label, choices in [('district', 'District', districts), ('crop', 'Crop', crops)] %}
          <label class="field">{{ label }}<select name="{{ name }}" required>
            <option value="">Choose {{ label|lower }}</option>
            {% for choice in choices %}<option{% if values.get(name) == choice %} selected{% endif %}>{{ choice }}</option>{% endfor %}
          </select></label>
        {% endfor %}
        {% if action != 'check' %}
          <label class="field full">Village or field location<input name="locality" maxlength="160" required value="{{ values.get('locality', '') }}"></label>
          {% if action == 'register' %}
            <label class="field">Planting date<input name="planting_date" type="date" required value="{{ values.get('planting_date', '') }}"></label>
            <label class="field">Water source<select name="water_source" required>
              <option value="">Choose a source</option>
              {% for source in water_sources %}<option{% if values.get('water_source') == source %} selected{% endif %}>{{ source }}</option>{% endfor %}
            </select></label>
          {% else %}
            <label class="field full">What is happening in the field?<textarea name="problem" maxlength="2000" required>{{ values.get('problem', '') }}</textarea></label>
          {% endif %}
          <label class="field">Full name<input name="full_name" autocomplete="name" maxlength="160" required value="{{ values.get('full_name', '') }}"></label>
          <label class="field">Phone or WhatsApp number<input name="phone" type="tel" autocomplete="tel" maxlength="60" required value="{{ values.get('phone', '') }}"></label>
          <label class="check full"><input name="consent" type="checkbox" value="1" required{% if values.get('consent') == '1' %} checked{% endif %}>I agree that IBROWS may use these details to review my submission and contact me about it.</label>
        {% endif %}
      </div>
      <div class="form-actions"><button>{{ 'Check area' if action == 'check' else 'Submit to IBROWS' }}</button></div>
    </form>
  {% endif %}
  {% if area %}
    <h3>{{ area.district }} · {{ area.crop }}</h3>
    <p>No district and crop advisory has been published here yet.</p>
    <p><a href="https://www.metmalawi.gov.mw/products/">Browse official forecasts and agricultural bulletins from Malawi DCCMS</a>.</p>
  {% endif %}
</section>
{% endif %}
""" + END
