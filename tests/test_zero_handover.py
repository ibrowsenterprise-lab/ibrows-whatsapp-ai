"""Offline regression tests for the IBROWS global 0 human-handover command."""
import ast
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"app.py"

def isolated_menu_handler(stubs):
    tree=ast.parse(SOURCE.read_text(encoding="utf-8"))
    f=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="handle_numbered_service_menu")
    exec(compile(ast.Module(body=[f],type_ignores=[]),str(SOURCE),"exec"),stubs)
    return stubs[f.name]

class ZeroHandover(unittest.TestCase):
    def make_handler(self,state=None):
        calls=[]
        stubs={
            "_normalise_menu_text":lambda value:" ".join(str(value or "").strip().lower().split()),
            "clear_customer_menu_state":lambda number:calls.append(("clear",number)),
            "get_customer_menu_state":lambda number: calls.append(("get",number)) or state,
            "is_main_service_menu_request":lambda msg:False,
            "_career_menu_selection":lambda text:None,
            "_main_menu_selection":lambda text:None,
        }
        return isolated_menu_handler(stubs),calls

    def test_bare_zero_without_menu_state_requests_jones(self):
        handler,calls=self.make_handler()
        self.assertEqual(handler("265999000111","Tester","0"),{"action":"JONES"})
        self.assertEqual(calls,[("clear","265999000111")])

    def test_zero_with_live_menu_state_requests_jones(self):
        handler,calls=self.make_handler("MAIN")
        self.assertEqual(handler("265999000111","Tester"," 0 "),{"action":"JONES"})
        self.assertEqual(calls,[("clear","265999000111")])

    def test_zero_with_career_menu_state_requests_jones(self):
        handler,calls=self.make_handler("CAREER")
        self.assertEqual(handler("265999000111","Tester","0"),{"action":"JONES"})
        self.assertEqual(calls,[("clear","265999000111")])

    def test_zero_inside_quantity_is_not_handover(self):
        handler,calls=self.make_handler()
        self.assertIsNone(handler("265999000111","Tester","0 kg of maize"))
        self.assertNotIn(("clear","265999000111"),calls)

    def test_other_number_outside_menu_is_not_handover(self):
        handler,calls=self.make_handler()
        self.assertIsNone(handler("265999000111","Tester","14"))
        self.assertNotIn(("clear","265999000111"),calls)

    def test_jones_dispatch_in_webhook_still_calls_real_handover(self):
        tree=ast.parse(SOURCE.read_text(encoding="utf-8"))
        func=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="receive_webhook")
        snippet=ast.get_source_segment(SOURCE.read_text(encoding="utf-8"),func)
        self.assertIn('menu_result.get("action") == "JONES"',snippet)
        self.assertIn('handle_local_human_handover(',snippet)
        handover=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="handle_local_human_handover")
        inner=ast.get_source_segment(SOURCE.read_text(encoding="utf-8"),handover)
        self.assertIn("set_ai_paused(customer_number, True)",inner)
        self.assertIn("record_human_handover_on_current_lead(",inner)
        self.assertIn("send_human_handover_alert_email(",inner)

if __name__=="__main__":
    unittest.main()
