"""Offline tests: only exact known QA records may be archived/deleted."""
import sys
import types
import unittest
from unittest.mock import patch
from explicit_qa_cleanup import run_exact_qa_cleanup,WEBSITE_TEST_REQUESTS,PROJECT_TEST_ID

class FakeCursor:
    def __init__(self,requests=(6,7),project=True,website_dependency=(),project_dependency=False,fail_delete=False):
        self.requests=set(requests)
        self.project=project
        self.website_dependency=set(website_dependency)
        self.project_dependency=project_dependency
        self.fail_delete=fail_delete
        self.events=[]
        self.response=None
        self.rowcount=0
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def execute(self,sql,args=None):
        args=args or ()
        compact=" ".join(sql.split())
        self.events.append((compact,args))
        self.rowcount=0
        if "pg_advisory_xact_lock" in sql or "CREATE TABLE IF NOT EXISTS" in sql:
            self.response=(True,)
        elif "SELECT id FROM website_service_requests" in sql:
            self.response=(args[0],) if args[0] in self.requests else None
        elif "SELECT id FROM project_assessments" in sql:
            self.response=(PROJECT_TEST_ID,) if self.project else None
        elif compact.startswith("SELECT EXISTS") and "website_service_request_files" in sql:
            self.response=(args[0] in self.website_dependency,)
        elif compact.startswith("SELECT EXISTS"):
            self.response=(self.project_dependency,)
        elif compact.startswith("INSERT INTO ibrows_qa_cleanup_archive"):
            self.rowcount=3 if "FROM project_activity" in sql else 1
        elif compact.startswith("DELETE FROM website_service_requests"):
            self.rowcount=0 if self.fail_delete else 1
        elif compact.startswith("DELETE FROM project_assessments"):
            self.rowcount=0 if self.fail_delete else 1
        else: raise AssertionError("Unexpected SQL in QA cleanup: "+compact[:130])
    def fetchone(self): return self.response

class FakeConn:
    def __init__(self,cursor):
        self.c=cursor
        self.commits=0
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def cursor(self): return self.c
    def commit(self): self.commits+=1

class CleanupTests(unittest.TestCase):
    def run_case(self,**kwargs):
        cursor=FakeCursor(**kwargs)
        conn=FakeConn(cursor)
        module=types.SimpleNamespace(get_db=lambda:conn)
        with patch.dict(sys.modules,{"app":module}):
            outcome=run_exact_qa_cleanup(None)
        return outcome,conn,cursor

    def test_only_three_exact_targets_archived_before_delete(self):
        outcome,conn,cursor=self.run_case()
        self.assertTrue(outcome)
        self.assertEqual(conn.commits,1)
        statements=cursor.events
        deleted=[(i,sql,args) for i,(sql,args) in enumerate(statements) if sql.startswith("DELETE FROM")]
        self.assertEqual(len(deleted),3)
        self.assertEqual(deleted[0][2],WEBSITE_TEST_REQUESTS[0])
        self.assertEqual(deleted[1][2],WEBSITE_TEST_REQUESTS[1])
        self.assertEqual(deleted[2][2],(1,"Test"))
        archived_indices=[i for i,(sql,_) in enumerate(statements) if sql.startswith("INSERT INTO ibrows_qa_cleanup_archive")]
        self.assertEqual(len(archived_indices),4)
        self.assertLess(archived_indices[0],deleted[0][0])
        self.assertLess(archived_indices[1],deleted[1][0])
        self.assertLess(archived_indices[-1],deleted[-1][0])
        self.assertFalse(any("DELETE FROM lead" in sql or "DELETE FROM conversations" in sql for sql,_ in statements))

    def test_idempotent_when_targets_absent(self):
        outcome,conn,cursor=self.run_case(requests=(),project=False)
        self.assertTrue(outcome)
        self.assertEqual(conn.commits,1)
        self.assertFalse(any(sql.startswith("DELETE FROM") for sql,_ in cursor.events))

    def test_dependencies_block_deletion(self):
        outcome,conn,cursor=self.run_case(website_dependency=(6,),project_dependency=True)
        self.assertTrue(outcome)
        deleted=[args for sql,args in cursor.events if sql.startswith("DELETE FROM")]
        self.assertEqual(deleted,[WEBSITE_TEST_REQUESTS[1]])

    def test_unexpected_delete_count_rolls_back(self):
        outcome,conn,cursor=self.run_case(fail_delete=True)
        self.assertFalse(outcome)
        self.assertEqual(conn.commits,0)

if __name__=="__main__": unittest.main()
