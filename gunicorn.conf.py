"""Safe, narrowly scoped public-response hooks for IBROWS Enterprise.

The existing Flask application, all web routes, Meta webhook, and customer
database remain unmodified. Gunicorn applies these HTML-only adjustments
after the application has generated a successful public response.
"""
from launch_contact_config import rewrite_public_whatsapp_html
from public_ai_shortcut import register_public_ai_shortcut
from crm_quality import install_crm_improvements
from crm_paid_truth import install_paid_crm_truth
from scholarship_eligibility_backend import install_eligibility_work_queue
from whatsapp_menu_patch import install_whatsapp_menu_fix
from automatic_verified_receipts import install_auto_receipts
from backend_operations_health import install_backend_operations
from payment_query_efficiency import install_payment_query_batch

MITGO_META_TAG = '<meta name="mitgo-verification" content="0f143843-cefa-4d05-91a9-ab05bdbc998c" />'


def post_worker_init(worker):
    """Preserve MetaTag verification and connect public WhatsApp to the AI."""
    flask_app = worker.wsgi
    register_public_ai_shortcut(flask_app)
    install_crm_improvements(flask_app)
    install_eligibility_work_queue(flask_app)
    install_paid_crm_truth(flask_app)
    install_whatsapp_menu_fix(flask_app)
    install_auto_receipts(flask_app)
    install_backend_operations(flask_app)
    install_payment_query_batch(flask_app)

    @flask_app.after_request
    def _ibrows_public_launch_contact(response):
        from flask import request

        # No mutation of webhooks, API responses, POST submissions, admin,
        # customer records, or error responses.
        if request.method != "GET":
            return response
        if response.status_code != 200 or response.mimetype != "text/html":
            return response
        if request.path.startswith(("/admin", "/api/", "/webhook", "/internal/")):
            return response

        html = response.get_data(as_text=True)
        if request.path == "/" and MITGO_META_TAG not in html and "<head>" in html:
            html = html.replace("<head>", "<head>\n  " + MITGO_META_TAG, 1)

        html = rewrite_public_whatsapp_html(html)
        if html != response.get_data(as_text=True):
            response.set_data(html)
        return response
