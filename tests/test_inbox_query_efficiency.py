"""Bounded secure inbox tests: fake data only; no customer data, writes or network."""
import unittest
from datetime import datetime,timezone
from inbox_query_efficiency import (
    LIMIT,INBOX_QUERY,load_inbox_customers,install_inbox_query_efficiency,
)

class FakeCursor:
    def __init__(self,items,fail=False):
        self.items=items
        self.fail=fail
        self.sql=None
        self.params=None
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False
    def execute(self,sql,params):
        if self.fail:
            raise RuntimeError("offline simulated database outage")
        self.sql=sql
        self.params=params
        assert sql.lstrip().startswith("WITH latest AS")
        assert params[-1]==LIMIT
    def fetchall(self):
        return self.items

class FakeConn:
    def __init__(self,cursor):
        self.c=cursor
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False
    def cursor(self):
        return self.c

class TestInboxReadOnlyEfficiency(unittest.TestCase):
    def test_search_is_parameterized_and_fetched_rows_are_bounded(self):
        self.assertEqual(LIMIT,250)
        self.assertIn("POSITION(%s IN LOWER",INBOX_QUERY)
        self.assertIn("LIMIT %s",INBOX_QUERY)
        self.assertIn("DISTINCT ON (c.customer_number)",INBOX_QUERY)
        self.assertIn("COALESCE(a.ai_paused,FALSE) DESC",INBOX_QUERY)
        self.assertIn("c.created_at DESC",INBOX_QUERY)
        self.assertNotIn("DELETE FROM",INBOX_QUERY)
        self.assertNotIn("UPDATE ",INBOX_QUERY)
        self.assertNotIn("INSERT INTO",INBOX_QUERY)
        now=datetime(2026,11,11,10,0,tzinfo=timezone.utc)
        c=FakeCursor([
            ("265000000001","user","Need Jones please","Client",now,True,"Customer A"),
            ("265000000002","assistant","Hello and welcome to IBROWS","AI",now,False,"Customer B"),
        ])
        result=load_inbox_customers(lambda:FakeConn(c),"  Customer A  ",timezone.utc)
        self.assertEqual(c.params,("customer a","customer a","customer a","customer a",250))
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]["customer_name"],"Customer A")
        self.assertTrue(result[0]["ai_paused"])
        self.assertEqual(result[1]["sender_label"],"AI")
        self.assertEqual(result[0]["preview"],"Need Jones please")
        self.assertEqual(result[0]["local_time"],"11 Nov 2026 at 10:00")

    def test_failed_optimized_read_uses_original_function(self):
        bad=FakeCursor([],fail=True)
        saved=[]
        def original(query=""):
            saved.append(query)
            return [{"customer_number":"safe-existing"}]
        ns={
            "get_db":lambda:FakeConn(bad),
            "get_admin_inbox_customers":original,
            "ADMIN_TIMEZONE":timezone.utc,
            "INBOX_TEMPLATE":'<div class="tools"><form class="search">',
        }
        exec("def admin_inbox(): return 'ok'\n",ns)
        class DummyApp:
            def __init__(self,view):
                self.view_functions={"admin_inbox":view}
        app=DummyApp(ns["admin_inbox"])
        self.assertTrue(install_inbox_query_efficiency(app))
        self.assertTrue(install_inbox_query_efficiency(app))
        result=ns["get_admin_inbox_customers"]("test")
        self.assertEqual(result,[{"customer_number":"safe-existing"}])
        self.assertEqual(saved,["test"])
        self.assertIn("most recent matching conversations",ns["INBOX_TEMPLATE"])
        self.assertIn("Search by customer name",ns["INBOX_TEMPLATE"])
        self.assertNotIn("DELETE",ns["INBOX_TEMPLATE"])

if __name__=="__main__":
    unittest.main()
