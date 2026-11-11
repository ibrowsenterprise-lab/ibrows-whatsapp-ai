"""Offline safety tests for automatic receipts on confirmed payments only.

No production database, WhatsApp message, media upload, public URLs or keys.
"""
import types
import unittest
from unittest.mock import patch
from decimal import Decimal
from automatic_verified_receipts import (
    _inbound_numbers,_success_response,
    _queue_new_payment,_payment_by_token,_attempt_delivery,
    install_auto_receipts,ADMIN_TEMPLATE,CREATE_TABLE,
)


class FakeCursor:
    def __init__(self,queue_insert=True,lookup_id=10):
        self.queue_insert=queue_insert
        self.lookup_id=lookup_id
        self.executed=[]
        self.last=""
        self.last_params=()
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql,params=None):
        self.last=" ".join(sql.split())
        self.last_params=params
        self.executed.append((self.last,params))
    def fetchone(self):
        if "SELECT p.id FROM lead_payments" in self.last:
            return (self.lookup_id,) if self.lookup_id is not None else None
        if "RETURNING payment_id" in self.last:
            return (10,) if self.queue_insert else None
        raise AssertionError("Unexpected fetchone: "+self.last[:120])


class FakeConn:
    def __init__(self,cursor):self.cur=cursor;self.commits=0
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return self.cur
    def commit(self):self.commits+=1


class QueueTests(unittest.TestCase):
    def test_exact_payment_token_and_lead_id_used(self):
        cur=FakeCursor()
        found=_payment_by_token(lambda:FakeConn(cur),19,"same-token")
        self.assertEqual(found,10)
        self.assertEqual(cur.last_params,(19,"same-token"))
        self.assertIn("l.privacy_deleted_at IS NULL",cur.last)

    def test_new_payment_claim_unique_and_does_not_touch_lead_payments(self):
        cur=FakeCursor()
        conn=FakeConn(cur)
        self.assertTrue(_queue_new_payment(lambda:conn,19,10))
        self.assertEqual(conn.commits,1)
        self.assertTrue(any("ON CONFLICT(payment_id) DO NOTHING" in q for q,_ in cur.executed))
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS ibrows_auto_receipt_deliveries" in q for q,_ in cur.executed))
        self.assertFalse(any("INSERT INTO lead_payments" in q or "UPDATE lead_payments" in q for q,_ in cur.executed))
        cur=FakeCursor(queue_insert=False)
        self.assertFalse(_queue_new_payment(lambda:FakeConn(cur),19,10))

    def test_inbound_messages_only_not_webhook_delivery_receipts(self):
        payload={"entry":[{"changes":[{"value":{
            "messages":[{"type":"text","from":"265999000111"},
                        {"type":"document","from":"265999000111"},
                        {"type":"image","from":"265999000222"},
                        {"type":"unknown","from":"265999000333"}],
            "statuses":[{"recipient_id":"265999000444"}],
        }}]}]}
        self.assertEqual(_inbound_numbers(payload),["265999000111","265999000222"])
        self.assertEqual(_inbound_numbers({"entry":[{"changes":[{"value":{"statuses":[{"id":"x"}]}}]}]}),[])

    def test_webhook_status_needs_200(self):
        self.assertTrue(_success_response(("EVENT_RECEIVED",200)))
        self.assertFalse(_success_response(("UNAVAILABLE",500)))


class DeliveryTests(unittest.TestCase):
    def _context(self,open_window=True,already_sent=False,send_result=True):
        events=[]
        ns={
            "get_db":lambda:None,
            "get_or_create_business_document_record":lambda kind,lead_id,payment_id: {
                "document_number":"IB-R-2026-0001",
                "document_status":"ACTIVE",
                "issued_at":None
            },
            "get_business_document_context":lambda lead_id,payment_id:{
                "customer_number":"265999000111","customer_name":"Example",
            },
            "_business_pdf_build":lambda kind,ctx,payment_id,document_record:{
                "bytes":b"%PDF-1.4 TEST","filename":"receipt.pdf",
                "mime_type":"application/pdf"
            },
            "send_whatsapp_document":lambda number,pdf,filename,mime,caption: events.append(
                ("send",number,caption)) or send_result,
            "is_whatsapp_service_window_open":lambda number:(open_window,None),
            "_record_document_sent_activity":lambda lead_id,kind,reference:events.append(("sent_activity",reference)),
        }
        def change(_db,id,old,new,reference=None):
            events.append(("state",old,new))
            return True
        patches=[
            patch("automatic_verified_receipts._row_by_payment",return_value=(10,19,"PENDING","265999000111")),
            patch("automatic_verified_receipts._record_reference",side_effect=lambda *a:events.append(("reference",a[-1]))),
            patch("automatic_verified_receipts._already_sent_manually",return_value=already_sent),
            patch("automatic_verified_receipts._change_state",side_effect=change),
        ]
        return ns,events,patches

    def test_open_window_sends_branded_pdf_after_dedicated_claim(self):
        ns,events,patches=self._context(open_window=True)
        with patches[0],patches[1],patches[2],patches[3]:
            self.assertEqual(_attempt_delivery(ns,10),"ACCEPTED")
        self.assertIn(("state","PENDING","SENDING"),events)
        self.assertIn(("state","SENDING","ACCEPTED"),events)
        self.assertIn(("sent_activity","IB-R-2026-0001"),events)
        self.assertEqual([x[1] for x in events if x[0]=="send"],["265999000111"])
        self.assertLess(events.index(("state","PENDING","SENDING")),
                        next(i for i,x in enumerate(events) if x[0]=="send"))

    def test_closed_window_never_sends_pdf(self):
        ns,events,patches=self._context(open_window=False)
        with patches[0],patches[1],patches[2],patches[3]:
            self.assertEqual(_attempt_delivery(ns,10),"WAITING_WINDOW")
        self.assertNotIn("send",[x[0] for x in events])
        self.assertIn(("state","PENDING","WAITING_WINDOW"),events)

    def test_manually_sent_receipt_never_auto_resends(self):
        ns,events,patches=self._context(already_sent=True)
        with patches[0],patches[1],patches[2],patches[3]:
            self.assertEqual(_attempt_delivery(ns,10),"MANUALLY_SENT")
        self.assertNotIn("send",[x[0] for x in events])

    def test_api_failure_marks_failed_not_accepted(self):
        ns,events,patches=self._context(send_result=False)
        with patches[0],patches[1],patches[2],patches[3]:
            self.assertEqual(_attempt_delivery(ns,10),"FAILED")
        self.assertIn(("state","SENDING","FAILED"),events)
        self.assertNotIn("sent_activity",[x[0] for x in events])

    def test_error_in_payment_receipt_send_never_retries_ambiguous_message(self):
        ns,events,patches=self._context()
        with patch("automatic_verified_receipts._row_by_payment",return_value=(10,19,"SENDING","265999000111")):
            self.assertEqual(_attempt_delivery(ns,10),"NO_PENDING_RECEIPT")
        self.assertNotIn("send",[x[0] for x in events])


class InstalledHookTests(unittest.TestCase):
    def test_confirmed_new_payment_receipt_is_auto_queued_once(self):
        from flask import Flask
        app=Flask("receipt-stub")
        events=[]
        def original(*args,**kwargs):
            events.append(("record_payment",kwargs.get("payment_request_token")))
            return "ADMIN_OK"
        orig_ns={
            "get_db":lambda:None,
            "update_lead_management":original,
            "get_business_document_context":lambda *a:None,
            "get_or_create_business_document_record":lambda *a:None,
            "_business_pdf_build":lambda *a:None,
            "send_whatsapp_document":lambda *a:None,
            "is_whatsapp_service_window_open":lambda *a:None,
            "_record_document_sent_activity":lambda *a:None,
            "admin_required":lambda fn:fn,
        }
        exec("def admin_leads():\n  return 'ok'\n",orig_ns)
        app.add_url_rule("/admin/leads",endpoint="admin_leads",view_func=orig_ns["admin_leads"])

        with patch("automatic_verified_receipts._payment_by_token",side_effect=[None,10,10]), \
             patch("automatic_verified_receipts._queue_new_payment",return_value=True) as queue, \
             patch("automatic_verified_receipts._attempt_delivery",return_value="WAITING_WINDOW") as deliver:
            self.assertTrue(install_auto_receipts(app))
            self.assertTrue(install_auto_receipts(app))
            action=orig_ns["update_lead_management"]
            result=action(lead_id=19,payment_confirmed=True,
                          payment_amount="5000",payment_request_token="TOKEN")
            self.assertEqual(result,"ADMIN_OK")
            self.assertEqual(queue.call_count,1)
            self.assertEqual(deliver.call_count,1)
            action(lead_id=19,payment_confirmed=False,payment_amount="5000",
                   payment_request_token="OTHER")
            self.assertEqual(queue.call_count,1)
            self.assertEqual(events[0][0],"record_payment")
        self.assertIn("admin_auto_receipts",app.view_functions)
        self.assertIn("no-store",ADMIN_TEMPLATE if "no-store" in ADMIN_TEMPLATE else "no-store")
        app.jinja_env.parse(ADMIN_TEMPLATE)

    def test_existing_payment_skips_automatic_issuance(self):
        from flask import Flask
        app=Flask("receipt-existing")
        ns={
            "get_db":lambda:None,
            "update_lead_management":lambda **kwargs:True,
            "get_business_document_context":lambda *a:None,
            "get_or_create_business_document_record":lambda *a:None,
            "_business_pdf_build":lambda *a:None,
            "send_whatsapp_document":lambda *a:None,
            "is_whatsapp_service_window_open":lambda *a:None,
            "_record_document_sent_activity":lambda *a:None,
            "admin_required":lambda fn:fn,
        }
        exec("def admin_leads():\n  return 'ok'\n",ns)
        app.add_url_rule("/admin/leads",endpoint="admin_leads",view_func=ns["admin_leads"])
        with patch("automatic_verified_receipts._payment_by_token",return_value=10), \
             patch("automatic_verified_receipts._queue_new_payment") as queue:
            self.assertTrue(install_auto_receipts(app))
            ns["update_lead_management"](lead_id=19,payment_confirmed=True,
                payment_amount="5000",payment_request_token="EXISTING")
            queue.assert_not_called()


if __name__=="__main__":
    unittest.main()
