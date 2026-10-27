"""Exercise webhook helpers without importing the live application's database."""
import ast
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / "app.py"


def load_function(name, index, namespace):
    tree = ast.parse(SOURCE.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    exec(compile(ast.Module(body=[nodes[index]], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace[name]


def test_graph_failure_logs_only_numeric_codes(capsys):
    class Requests:
        RequestException = Exception
        @staticmethod
        def post(*args, **kwargs):
            return SimpleNamespace(status_code=401, json=lambda: {"error": {
                "code": 190, "error_subcode": 463, "message": "PRIVATE TOKEN AND PHONE"}})
    send = load_function("send_whatsapp_message", 0, {
        "WHATSAPP_TOKEN": "secret", "PHONE_NUMBER_ID": "123", "requests": Requests})
    assert send("recipient", "hello") is False
    log = capsys.readouterr().out
    assert "code=190" in log and "error_subcode=463" in log
    assert "PRIVATE" not in log and "secret" not in log and "recipient" not in log


def test_reclaimed_stale_message_retries_saved_reply():
    class Cursor:
        def __init__(self): self.calls = 0
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, *args): self.calls += 1
        def fetchone(self):
            return {1: None, 2: ("sender", "PROCESSING", "saved reply", None),
                    3: (0, 0), 4: ("message-id",)}[self.calls]
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Cursor()
        def commit(self): pass
    claim = load_function("claim_whatsapp_message", -1, {"get_db": Connection})
    assert claim("message-id", "sender") == ("RETRY_REPLY", "saved reply")


def test_batched_webhook_retains_failure_status_for_meta_retry():
    from flask import Flask, request
    app = Flask(__name__)
    namespace = {"app": app, "request": request}
    namespace["_v125_contact_slice"] = load_function("_v125_contact_slice", 0, namespace)
    namespace["_v125_message_payloads"] = load_function("_v125_message_payloads", 0, namespace)
    seen = []
    def old_handler():
        msg = request.get_json()["entry"][0]["changes"][0]["value"]["messages"][0]
        seen.append(msg["id"])
        return ("FAILED", 500) if msg["id"] == "two" else ("OK", 200)
    namespace["_V124_RECEIVE_WEBHOOK"] = old_handler
    handler = load_function("_receive_webhook_v125", 0, namespace)
    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"id": "one", "from": "a"}, {"id": "two", "from": "b"}]}}]}]}
    with app.test_request_context('/webhook', method='POST', json=payload):
        assert handler()[1] == 500
    assert seen == ['one', 'two']
