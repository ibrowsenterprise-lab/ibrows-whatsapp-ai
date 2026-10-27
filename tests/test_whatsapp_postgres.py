"""WhatsApp retry tests, using only the disposable CI database."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest


@pytest.fixture(scope="module")
def app_module():
    assert os.environ.get("DATABASE_URL", "").endswith("/ibrows_marketplace_test")
    import app
    return app


@pytest.fixture
def message_id(app_module):
    mid = "ci-whatsapp-" + uuid.uuid4().hex
    yield mid
    with app_module.get_db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM whatsapp_delivery_outbox WHERE message_id=%s", (mid,))
        cur.execute("DELETE FROM processed_whatsapp_messages WHERE message_id=%s", (mid,))


def test_concurrent_duplicate_claims_only_one_processes(app_module, message_id):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: app_module.claim_whatsapp_message(message_id, "test-sender"), range(2)))
    assert sorted(action for action, _ in results) == ["IGNORE", "PROCESS"]
    app_module.finish_whatsapp_message(message_id, True)
    assert app_module.claim_whatsapp_message(message_id, "test-sender")[0] == "IGNORE"


def test_failed_delivery_retries_saved_reply(app_module, message_id):
    assert app_module.claim_whatsapp_message(message_id, "test-sender")[0] == "PROCESS"
    app_module.store_pending_reply(message_id, "saved reply")
    with pytest.raises(RuntimeError, match="WHATSAPP_DELIVERY_FAILED"):
        app_module.finish_whatsapp_message(message_id, False)
    assert app_module.claim_whatsapp_message(message_id, "test-sender") == ("RETRY_REPLY", "saved reply")
    assert app_module.claim_whatsapp_message(message_id, "different-sender")[0] == "IGNORE"


def test_stale_worker_reuses_saved_reply(app_module, message_id):
    assert app_module.claim_whatsapp_message(message_id, "test-sender")[0] == "PROCESS"
    app_module.store_pending_reply(message_id, "saved reply")
    with app_module.get_db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE processed_whatsapp_messages SET updated_at=NOW()-INTERVAL '2 minutes' WHERE message_id=%s", (message_id,))
    assert app_module.claim_whatsapp_message(message_id, "test-sender") == ("RETRY_REPLY", "saved reply")
