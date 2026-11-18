"""Munda Watch pilot pages and field intake validation."""
from datetime import date
from urllib.parse import urlencode

from agro_marketplace_ui import START, END
from launch_contact_config import ACTIVE_PUBLIC_WHATSAPP
from munda_weather import DCCMS_DAILY_URL, DCCMS_WARNINGS_URL, FORECAST_PREVIEWS, daily_forecast

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
        "For the short-range forecast, type WEATHER followed by your district, "
        "for example WEATHER LILONGWE.\n\n"
        "For all six language commands, type MUNDA LANGUAGES.\n\n"
        "To use the numbered farm services menu, type MUNDA WATCH.\n\n"
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
        "Kuti muone ulosi wa masiku akubwerawa, lembani NYENGO ndi dzina la boma lanu, "
        "monga NYENGO LILONGWE.\n\n"
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
        payload["weather"] = daily_forecast(district)
        payload["dccms_daily"] = DCCMS_DAILY_URL
        payload["dccms_warnings"] = DCCMS_WARNINGS_URL
        languages = [("weather", "English", "en"), ("nyengo", "Mu Chichewa", "ny")]
        languages.extend((command, name, lang) for command, (name, lang, _, _) in FORECAST_PREVIEWS.items())
        payload["weather_links"] = [
            (name, lang, f"https://wa.me/{ACTIVE_PUBLIC_WHATSAPP}?" + urlencode({"text": f"{command.upper()} {district.upper()}"}))
            for command, name, lang in languages
        ]
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


PAGE_STYLES = """
<style>
  .munda-heading h1 { margin-bottom:8px; }
  .munda-heading .back-link { margin-bottom:16px; }
  .munda-heading h2 { font-size:clamp(18px, 3vw, 23px); line-height:1.3; margin:0 0 8px; }
  .munda-home-actions { margin-top:0; }
  .munda-language-switch { display:flex; flex-wrap:wrap; gap:8px; margin:12px 0 16px; }
  .munda-language-switch a { min-height:44px; display:inline-flex; align-items:center; padding:0 14px; border:1px solid var(--line); border-radius:8px; text-decoration:none; }
  .munda-language-switch a[aria-current="page"] { background:var(--green); border-color:var(--green); color:white; font-weight:700; }
  .munda-home-languages { margin:16px 0; }
  #area-check-form { scroll-margin-top:16px; }
  .munda-result { margin-top:28px; border-top:1px solid var(--line); padding-top:20px; }
  #area-outlook { scroll-margin-top:16px; margin:0; font-size:clamp(23px, 4vw, 29px); line-height:1.2; }
  #area-outlook:focus, #area-check-form:focus { outline:none; }
  .munda-change-area { display:inline-flex; align-items:center; min-height:44px; font-size:14px; }
  .munda-result h4 { font-size:16px; margin:0 0 6px; }
  .munda-result p { margin:8px 0; }
  .munda-result .small-note { margin-top:10px; }
  .munda-weather { background:var(--soft); border:1px solid var(--line); border-radius:12px; padding:16px; }
  .munda-weather p, .munda-links { font-size:14px; }
  .munda-weather table { width:100%; border-collapse:collapse; font-size:14px; line-height:1.35; font-variant-numeric:tabular-nums; }
  .munda-weather th, .munda-weather td { padding:8px 5px; border-bottom:1px solid #cbdacf; text-align:right; }
  .munda-weather th:first-child { text-align:left; }
  .munda-weather thead th { color:var(--muted); font-size:12px; }
  .munda-weather tbody td { white-space:nowrap; }
  .munda-weather tbody tr:first-child { background:#fff8; }
  .munda-weather .munda-window { display:block; font-size:11px; font-weight:400; color:var(--muted); white-space:nowrap; }
  .munda-season { border-top:1px solid var(--line); padding-top:16px; margin-top:20px; }
  .munda-links { display:flex; flex-wrap:wrap; gap:10px 16px; margin:12px 0; }
  @media(max-width:620px) {
    .munda-heading { padding-block:20px 16px; }
    .munda-home-actions { gap:8px; }
    .munda-weather { padding:12px 8px; }
    .munda-weather table { font-size:13px; }
    .munda-weather th, .munda-weather td { padding:7px 4px; }
    .munda-weather thead th { font-size:11px; }
    .munda-result .munda-links a { min-height:24px; }
  }
</style>
"""

PAGE = START.replace("</head>", PAGE_STYLES + "</head>") + """
{% set home_chichewa = not action and request.args.get('lang') == 'ny' %}
<div class="page-heading munda-heading">
  {% if action %}
    <a class="back-link" href="{{ url_for('munda_watch_page') }}">← Munda Watch</a>
  {% else %}
    <a class="back-link" href="/agriculture">← Agriculture</a>
  {% endif %}
  <h1>Munda Watch</h1>
  {% if not action %}
    <nav class="munda-language-switch" aria-label="Page language">
      <a lang="en" href="{{ url_for('munda_watch_page') }}"{% if not home_chichewa %} aria-current="page"{% endif %}>English</a>
      <a lang="ny" href="{{ url_for('munda_watch_page', lang='ny') }}"{% if home_chichewa %} aria-current="page"{% endif %}>Mu Chichewa</a>
    </nav>
    {% if home_chichewa %}
      <h2 lang="ny">Kukonzekera El Niño ku Malawi</h2>
      <p class="intro" lang="ny">Onani ulosi wa nyengo wa tsiku lililonse ndi mmene mvula ikuyembekezeka kugwa m'boma lanu m'nyengo ino. Lembetsani munda wanu kapena auzeni IBROWS za vuto la m'munda.</p>
    {% else %}
      <h2>El Niño farm preparedness in Malawi</h2>
      <p class="intro">Check daily weather and the seasonal rainfall outlook for your district. Register your field or report a problem to IBROWS.</p>
    {% endif %}
  {% endif %}
</div>
{% if action %}
<section class="panel" style="max-width:760px">
  <h2{% if action == 'check' %} id="area-check-form" tabindex="-1"{% endif %}>{{ actions[action] }}</h2>
  {% if error %}<p class="error" role="alert">{{ error }}</p>{% endif %}
  {% if reference %}
    <p role="status">Received by IBROWS. Your reference is <strong>{{ reference }}</strong>.</p>
    <p>Keep this reference to check your request and see your district forecast.</p>
    <div class="form-actions">
      <a class="button" href="https://wa.me/""" + ACTIVE_PUBLIC_WHATSAPP + """?text=MY%20FIELD%20{{ reference|urlencode }}">Check status on WhatsApp</a>
    </div>
    <p class="small-note">Use the same WhatsApp number you entered on this form.</p>
  {% else %}
    <form method="{{ 'get' if action == 'check' else 'post' }}"{% if action == 'check' %} action="{{ url_for('munda_watch_page', action=action, _anchor='area-outlook') }}"{% endif %}>
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
  <div class="munda-result">
    <h3 id="area-outlook" tabindex="-1">{{ area.district }} · {{ area.crop }}</h3>
    <a class="munda-change-area" href="#area-check-form">Change district or crop</a>
    <section class="munda-weather" aria-labelledby="short-range-weather">
      <h4 id="short-range-weather">Today and next 5 days</h4>
      {% if area.weather %}
        <p>Forecast near {{ area.district }}. Conditions vary across the district.</p>
        <table aria-labelledby="short-range-weather">
          <thead><tr>
            <th scope="col">Day</th><th scope="col">Rain (mm)</th>
            <th scope="col">Temp (°C)</th><th scope="col">Wind max<br>(km/h)</th>
          </tr></thead>
          <tbody>
          {% for day in area.weather.rows %}
            <tr>
              <th scope="row">{{ day.date.strftime('%a %d %b') }}
                {% if day.from_time != '02:00' %}<span class="munda-window">From {{ day.from_time }}</span>{% endif %}
              </th>
              <td>{{ '%g'|format(day.rain_mm) }}</td>
              <td>{{ day.temp_low }}–{{ day.temp_high }}</td>
              <td>{{ day.wind_kmh }}</td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
        <p class="small-note">Full periods run from 02:00 to 02:00 the next morning, Malawi time.</p>
        <p class="small-note">Updated {{ area.weather.updated }}. Based on <a href="{{ area.weather.source }}">MET Norway data</a> (<a href="{{ area.weather.licence }}">CC BY 4.0</a>), aggregated by IBROWS. Reference coordinates from <a href="https://www.geonames.org/">GeoNames</a>.</p>
      {% else %}
        <p>The short-range forecast is temporarily unavailable.</p>
      {% endif %}
    </section>
    <div class="munda-links">
      <a href="{{ area.dccms_daily }}">DCCMS daily forecast</a>
      <a href="{{ area.dccms_warnings }}">DCCMS weather warnings</a>
    </div>
    <section aria-labelledby="munda-whatsapp">
      <h4 id="munda-whatsapp">Get this forecast on WhatsApp</h4>
      <div class="munda-links">
        {% for name, lang, link in area.weather_links %}
          <a lang="{{ lang }}" href="{{ link }}">{{ name }}</a>
        {% endfor %}
      </div>
      <p class="small-note">Chitumbuka, Chisena, Chiyao and Chilomwe are bilingual previews.</p>
    </section>
    <section class="munda-season" aria-labelledby="munda-seasonal">
      <h4 id="munda-seasonal">Seasonal rainfall outlook</h4>
      {% if area.outlook %}
        <p class="small-note">Issued {{ area.outlook.issued_on.strftime('%d %B %Y') }}</p>
        <p>{{ area.outlook.summary }}</p>
        <p>This outlook describes district rainfall for the 2026–2027 season. For {{ area.crop|lower }} planting decisions, check the latest short-term bulletin and speak with your local agricultural extension officer.</p>
        <p><a href="{{ area.outlook.source_url }}">Read the DCCMS {{ area.district }} district outlook</a></p>
      {% else %}
        <p>No current seasonal rainfall outlook is available here.</p>
      {% endif %}
      <p><a href="https://www.metmalawi.gov.mw/products/10-day-weather-and-agrometeorological-bulletin/">Read the DCCMS 10-day weather and agricultural bulletins</a></p>
    </section>
    <div class="form-actions">
      <a class="button secondary" href="{{ url_for('munda_watch_page', action='register', district=area.district, crop=area.crop) }}">Register this field</a>
      <a class="button secondary" href="{{ url_for('munda_watch_page', action='report', district=area.district, crop=area.crop) }}">Report a problem for this crop</a>
    </div>
  </div>
  {% endif %}
</section>
{% endif %}
{% if not area %}
{% set chichewa_actions = {'check': 'Onani nyengo m’boma lanu', 'register': 'Lembetsani munda', 'report': 'Fotokozani vuto la m’munda'} %}
<nav class="form-actions{% if not action %} munda-home-actions{% endif %}" aria-label="Munda Watch">
  {% for key, label in actions.items() if key != action %}
    <a{% if home_chichewa %} lang="ny"{% endif %} class="button{{ '' if key == 'check' else ' secondary' }}" href="{{ url_for('munda_watch_page', action=key) }}">{{ chichewa_actions[key] if home_chichewa else label }}</a>
  {% endfor %}
</nav>
{% endif %}
{% if not action %}
  <p class="munda-home-languages"><a{% if home_chichewa %} lang="ny"{% endif %} href="https://wa.me/""" + ACTIVE_PUBLIC_WHATSAPP + """?text=MUNDA%20LANGUAGES">{{ 'Zinenero za ulosi wa nyengo pa WhatsApp' if home_chichewa else 'Forecast languages on WhatsApp' }}</a></p>
{% endif %}
{% if home_chichewa %}
  <p lang="ny">Mauthenga a chenjezo la nyengo sanayambe kutumizidwa. Onani maulosi ovomerezeka a DCCMS pa tsamba la nyengo la boma lanu.</p>
{% else %}
  <p>Automatic weather alerts are currently unavailable.{% if not area %} Check your area for official DCCMS bulletins.{% endif %}</p>
{% endif %}
""" + END
