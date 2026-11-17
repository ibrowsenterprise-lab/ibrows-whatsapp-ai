"""Munda Watch pilot pages and field intake validation."""
from datetime import date

from agro_marketplace_ui import START, END

PATH = "/agriculture/munda-watch"
ACTIONS = {
    "check": "Check my area",
    "register": "Register a field",
    "report": "Report a field problem",
}
CROPS = (
    "Maize", "Groundnuts", "Soya", "Rice",
    "Banana", "Cassava", "Chillies", "Coffee", "Common beans", "Cotton",
    "Cowpeas", "Irish potato", "Macadamia", "Millet", "Paprika", "Pigeon peas",
    "Sesame", "Sorghum", "Sugarcane", "Sunflower", "Sweet potato", "Tea",
    "Tobacco",
)
WATER_SOURCES = ("Rain-fed", "Irrigated", "Rain-fed and irrigated", "Other")
DISTRICTS = (
    "Balaka", "Blantyre", "Chikwawa", "Chiradzulu", "Chitipa", "Dedza", "Dowa",
    "Karonga", "Kasungu", "Likoma", "Lilongwe", "Machinga", "Mangochi", "Mchinji",
    "Mulanje", "Mwanza", "Mzimba", "Neno", "Nkhata Bay", "Nkhotakota", "Nsanje",
    "Ntcheu", "Ntchisi", "Phalombe", "Rumphi", "Salima", "Thyolo", "Zomba",
)


DCCMS_DISTRICT_OUTLOOKS = "https://www.metmalawi.gov.mw/products/downscaled-seasonal-climate-outlook/"
OUTLOOK_ISSUED_ON = date(2026, 9, 15)
OUTLOOK_END_OF_SEASON = date(2027, 4, 30)
OUTLOOK_END_OF_FEBRUARY = date(2027, 2, 28)
NEAR_OR_ABOVE = "Seasonal rainfall is expected to be near or above normal."
NEAR_OR_BELOW = "Seasonal rainfall is expected to be near or below normal."

DISTRICT_RAINFALL_SUMMARIES = {
    "Balaka": "Seasonal rainfall is expected to be near or below normal, with a higher chance of near- or above-normal rainfall in March 2027.",
    "Blantyre": NEAR_OR_BELOW,
    "Chikwawa": NEAR_OR_BELOW,
    "Chiradzulu": NEAR_OR_BELOW,
    "Chitipa": NEAR_OR_ABOVE,
    "Dedza": NEAR_OR_ABOVE,
    "Dowa": NEAR_OR_BELOW,
    "Karonga": NEAR_OR_ABOVE,
    "Kasungu": NEAR_OR_BELOW,
    "Likoma": NEAR_OR_ABOVE,
    "Lilongwe": "Rainfall is expected to be near normal from October to December 2026, with a chance of near- or below-normal rainfall in January and February 2027.",
    "Machinga": NEAR_OR_BELOW,
    "Mangochi": NEAR_OR_BELOW,
    "Mchinji": NEAR_OR_BELOW,
    "Mulanje": NEAR_OR_BELOW,
    "Mwanza": NEAR_OR_BELOW,
    "Mzimba": NEAR_OR_ABOVE,
    "Neno": NEAR_OR_BELOW,
    "Nkhata Bay": "Many areas are expected to receive near- or above-normal rainfall this season.",
    "Nkhotakota": NEAR_OR_ABOVE,
    "Nsanje": NEAR_OR_BELOW,
    "Ntcheu": NEAR_OR_BELOW,
    "Ntchisi": "Rainfall is expected to be near or above normal from October to December 2026, with a chance of near- or below-normal rainfall in January and February 2027.",
    "Phalombe": NEAR_OR_BELOW,
    "Rumphi": NEAR_OR_ABOVE,
    "Salima": "Rainfall is expected to be near or above normal from October to December 2026, with a higher chance of near- or below-normal rainfall in January and February 2027.",
    "Thyolo": NEAR_OR_BELOW,
    "Zomba": NEAR_OR_BELOW,
}
FEBRUARY_OUTLOOK_DISTRICTS = {"Lilongwe", "Ntchisi", "Salima"}


def district_outlook(district, today):
    valid_through = (
        OUTLOOK_END_OF_FEBRUARY if district in FEBRUARY_OUTLOOK_DISTRICTS
        else OUTLOOK_END_OF_SEASON
    )
    if OUTLOOK_ISSUED_ON <= today <= valid_through:
        slug = district.lower().replace(" ", "-")
        return {
            "summary": DISTRICT_RAINFALL_SUMMARIES[district],
            "issued_on": OUTLOOK_ISSUED_ON,
            "source_url": f"{DCCMS_DISTRICT_OUTLOOKS}{slug}-district-downscaled-seasonal-forecast-2026-2027/",
        }


def whatsapp_reply(base_url):
    return (
        "Munda Watch | El Niño farm preparedness\n\n"
        "Preparing for El Niño in Malawi? Check what the seasonal rainfall outlook "
        "means for your district and use the field forms if you need follow-up.\n\n"
        f"Start here: Check your district and crop\n{base_url}{PATH}/check\n\n"
        f"Register your field for IBROWS follow-up\n{base_url}{PATH}/register\n\n"
        f"Report a field problem, such as dry conditions or poor emergence\n"
        f"{base_url}{PATH}/report\n\n"
        "Automatic weather alerts are currently unavailable. Use Check my area "
        "for links to official Malawi DCCMS bulletins.\n\n"
        "Pa Chichewa, lembani CHICHEWA."
    )


def chichewa_whatsapp_reply(base_url):
    return (
        "Munda Watch | Kukonzekera El Niño ku Malawi\n\n"
        "Sankhani boma lanu ndi mbewu yanu kuti muone mmene mvula "
        "ikuyembekezeka kugwa m'nyengo ino.\n\n"
        f"Onani mmene mvula ikuyembekezeka m'boma lanu\n{base_url}{PATH}/check\n\n"
        f"Lembetsani munda wanu kuti IBROWS ikutsatireni\n{base_url}{PATH}/register\n\n"
        f"Fotokozani vuto la m'munda, monga kuuma kwa nthaka kapena kusamera bwino kwa mbewu\n"
        f"{base_url}{PATH}/report\n\n"
        "Mauthenga a chenjezo la nyengo sanayambe kutumizidwa pa WhatsApp. "
        "Pa tsamba la Munda Watch pali maulosi a nyengo ochokera ku DCCMS."
    )


def whatsapp_alert_status(base_url):
    return (
        "Munda Watch weather alerts are currently unavailable on WhatsApp. "
        "Check your district for official DCCMS bulletins:\n"
        f"{base_url}{PATH}/check"
    )


def field_payload(action, form):
    district = form.get("district")
    crop = form.get("crop")
    if district not in DISTRICTS or crop not in CROPS:
        raise ValueError("Choose a district and a crop from the list.")
    payload = {"request_type": ACTIONS[action], "district": district, "crop": crop}
    if action == "check":
        payload["outlook"] = district_outlook(district, date.today())
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
  <h2>El Niño farm preparedness in Malawi</h2>
  <p class="intro">Start by choosing your district and crop to see the official seasonal rainfall outlook. Register a field for IBROWS follow-up or report a problem you are seeing on the ground.</p>
</div>
<nav class="form-actions" aria-label="Munda Watch">
  {% for key, label in actions.items() %}
    <a class="button secondary" href="{{ url_for('munda_watch_page', action=key) }}">{{ label }}</a>
  {% endfor %}
</nav>
<p>Automatic weather alerts are currently unavailable. Check your area for official DCCMS bulletins.</p>
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
    {% if area.outlook %}
      <p><strong>Seasonal rainfall outlook</strong> · Issued {{ area.outlook.issued_on.strftime('%d %B %Y') }}</p>
      <p>{{ area.outlook.summary }}</p>
      <p>This outlook describes district rainfall for the 2026–2027 season. For {{ area.crop|lower }} planting decisions, check the latest short-term bulletin and speak with your local agricultural extension officer.</p>
      <p><a href="{{ area.outlook.source_url }}">Read the DCCMS {{ area.district }} district outlook</a></p>
    {% else %}
      <p>No current seasonal rainfall outlook is available here.</p>
    {% endif %}
    <p><a href="https://www.metmalawi.gov.mw/products/10-day-weather-and-agrometeorological-bulletin/">Read the DCCMS 10-day weather and agricultural bulletins</a></p>
    <div class="form-actions">
      <a class="button secondary" href="{{ url_for('munda_watch_page', action='register', district=area.district, crop=area.crop) }}">Register this field</a>
      <a class="button secondary" href="{{ url_for('munda_watch_page', action='report', district=area.district, crop=area.crop) }}">Report a problem for this crop</a>
    </div>
  {% endif %}
</section>
{% endif %}
""" + END
