"""Safe multilingual WhatsApp service-menu routing for the IBROWS AI assistant.

Installed through the existing Gunicorn post_worker_init hook. The original
handoff/CRM logic stays responsible for requests for a human.
"""

ENGLISH_MENU = """Welcome to IBROWS Enterprise 👋
What can we help you with? Reply with a number.

1. Career & Jobs
2. Scholarships & Opportunities
3. Business Registration & Support
4. Website, AI & Automation
5. Graphic Design & Branding
6. Social Media, Digital Marketing & Content Creation (videos and jingles)
7. Photo Restoration
8. Cleaning Services
9. Car Wash
10. Fumigation
11. Landscaping
12. Construction & Property Improvement
13. Agro Dealing

0. Talk to Jones (human assistance)

Type MENU to see this list again."""

CHICHEWA_MENU = """Takulandirani ku IBROWS Enterprise 👋
Tumizani nambala ya ntchito yomwe mukufuna.

1. Ntchito ndi thandizo la ma CV
2. Ma scholarship ndi mwayi wamaphunziro
3. Kulembetsa bizinesi ndi upangiri
4. Mawebsite, AI ndi automation
5. Graphic design ndi branding
6. Social media, digital marketing ndi kupanga content (makanema ndi jingles)
7. Kukonza zithunzi zakale
8. Kuyeretsa nyumba ndi maofesi
9. Kutsuka magalimoto
10. Fumigation
11. Kukonza minda ndi malo (landscaping)
12. Zomangamanga ndi kukonza nyumba
13. Kugula ndi kugulitsa zokolola

0. Lankhulani ndi Jones (munthu)

Tumizani MENU kuti muonenso mndandandawu."""

TUMBUKA_MENU = """Takupokelerani ku IBROWS Enterprise 👋
Sankhani nambala ya ntchito iyo mukukhumba.

1. Kupenja ntchito na ma CV
2. Scholarships na mipata ya masambiro
3. Kulembeska bizinesi na wovwiri
4. Mawebsite, AI na automation
5. Graphic design na branding
6. Social media, digital marketing na kupanga content (mavidiyo na jingles)
7. Kunozga vithuzi vyakale
8. Cleaning services
9. Car wash
10. Fumigation
11. Landscaping
12. Construction na property improvement
13. Agro dealing — kugura na kuguliska vyakurya

0. Yowoyani na Jones (munthu)

Tumizgani MENU kuti muwonenso mndandanda."""

NUMBER_ROUTE = {
    "0": "JONES", "1": "CAREER", "2": "SCHOLARSHIP",
    "3": "BUSINESS", "4": "DIGITAL", "5": "MEDIA",
    "6": "MEDIA", "7": "PHOTO", "8": "CLEANING",
    "9": "CAR_WASH", "10": "FUMIGATION", "11": "LANDSCAPING",
    "12": "CONSTRUCTION", "13": "AGRO", "14": "MEDIA",
}


def _menu_language(message):
    text = " ".join(str(message or "").casefold().split())
    if any(word in text for word in (
        "chitumbuka", "tumbuka", "ndioneko", "mipata ya", "yowoyani",
    )):
        return TUMBUKA_MENU
    if any(word in text for word in (
        "chichewa", "chinyanja", "nyanja", "ndiwonetseni",
        "ndionetseni", "ndipatseni",
    )):
        return CHICHEWA_MENU
    return ENGLISH_MENU


def _local_menu_request(message):
    text = " ".join(str(message or "").casefold().split())
    return (
        any(phrase in text for phrase in (
            "ndioneko ma service anu", "ndioneko ma services anu",
            "ndioneko service zanu", "ndioneko ntchito zanu",
            "ndiwonetseni ntchito zanu", "ndionetseni ntchito zanu",
            "ndipatseni menu", "ndiwonetseni menu",
            "mundionetseko ntchito zanu",
        ))
        or (
            "menu" in text and
            any(lang in text for lang in (
                "chichewa", "chinyanja", "nyanja", "chitumbuka", "tumbuka",
            ))
        )
    )


def install_whatsapp_menu_fix(flask_app):
    """Patch only menu discovery and numbering; preserve customer handovers."""
    import sys

    core = sys.modules.get("app")
    if core is None:
        import app as core

    if getattr(core, "_ibrows_multilingual_menu_fixed", False):
        return

    original_menu_intent = core.is_main_service_menu_request
    original_number_route = core._main_menu_selection
    original_menu_handler = core.handle_numbered_service_menu

    core.MAIN_SERVICE_MENU = ENGLISH_MENU

    def menu_intent(message):
        return _local_menu_request(message) or original_menu_intent(message)

    def menu_selection(text):
        normalized = " ".join(str(text or "").casefold().split())
        if normalized in NUMBER_ROUTE:
            return NUMBER_ROUTE[normalized]
        return original_number_route(text)

    def menu_handler(customer_number, customer_name, customer_message):
        if _local_menu_request(customer_message):
            core.set_customer_menu_state(customer_number, "MAIN")
            return {"action": "REPLY", "reply": _menu_language(customer_message)}

        result = original_menu_handler(
            customer_number, customer_name, customer_message
        )
        if isinstance(result, dict) and result.get("action") == "REPLY":
            result = dict(result)
            result["reply"] = str(result.get("reply") or "").replace(
                "Please choose a number from 0 to 12",
                "Please choose a number from 0 to 13",
            )
        return result

    core.is_main_service_menu_request = menu_intent
    core._main_menu_selection = menu_selection
    core.handle_numbered_service_menu = menu_handler
    core._ibrows_multilingual_menu_fixed = True
    print("IBROWS WHATSAPP MULTILINGUAL MENU FIX READY: 1-13 and 0", flush=True)
