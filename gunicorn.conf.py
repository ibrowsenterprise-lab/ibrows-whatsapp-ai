"""Inject Admitad/Mitgo ownership verification on the public home page only.

Gunicorn loads this file from the repository root. It leaves the existing large
Flask application, other routes, and all customer data untouched.
"""

MITGO_META_TAG = '<meta name="mitgo-verification" content="0f143843-cefa-4d05-91a9-ab05bdbc998c" />'


def post_worker_init(worker):
    """Register a narrowly scoped public-homepage response hook."""
    flask_app = worker.wsgi

    @flask_app.after_request
    def _add_mitgo_verification(response):
        from flask import request

        if request.path != "/" or response.status_code != 200 or response.mimetype != "text/html":
            return response

        html = response.get_data(as_text=True)
        if MITGO_META_TAG in html:
            return response

        if "<head>" in html:
            response.set_data(html.replace("<head>", "<head>\n  " + MITGO_META_TAG, 1))
        return response
