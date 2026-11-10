"""Offline WhatsApp resume regression tests; no real messages, OpenAI or database."""
import ast, unittest
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]/"app.py"
CODE=SOURCE.read_text(encoding="utf-8")

def build_receiver(stubs):
    tree=ast.parse(CODE)
    func=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="receive_webhook")
    func.decorator_list=[]
    namespace=stubs.copy()
    exec(compile(ast.Module(body=[func],type_ignores=[]),str(SOURCE),"exec"),namespace)
    return namespace["receive_webhook"]

class Request:
    def __init__(self,text):
        self.text=text
    def get_json(self, silent=True):
        return {"entry":[{"changes":[{"value":{
            "messages":[{"from":"265999111222","id":"test-msg-001","type":"text",
                         "text":{"body":self.text}}],
            "contacts":[{"profile":{"name":"Test Client"}}],
        }}]}]}

class TestResume(unittest.TestCase):
    def run_chat(self,text,paused):
        events=[]
        ctx={
            "request":Request(text),
            "cleanup_expired_data":lambda:None,
            "claim_whatsapp_message":lambda mid,number:("NEW",None),
            "is_ai_paused":lambda number:events.append(("check_paused",number)) or paused,
            "set_ai_paused":lambda number,value:events.append(("set_paused",value)),
            "clear_customer_menu_state":lambda number:events.append(("clear_menu",number)),
            "save_message":lambda number,role,msg:events.append(("save",role,msg)),
            "store_pending_reply":lambda mid,reply:events.append(("pending",reply)),
            "send_whatsapp_message":lambda number,reply:events.append(("send",reply)) or True,
            "finish_whatsapp_message":lambda mid,sent:events.append(("finished",sent)),
        }
        result=build_receiver(ctx)()
        return result,events

    def test_resume_paused_customer_clears_pause_and_sends_ack(self):
        result,events=self.run_chat("Resume ai",True)
        self.assertEqual(result,("EVENT_RECEIVED",200))
        self.assertIn(("set_paused",False),events)
        self.assertEqual(len([e for e in events if e[0]=="send"]),1)
        reply=[e[1] for e in events if e[0]=="send"][0]
        self.assertIn("is active again",reply)
        self.assertIn("Show me your menu",reply)
        self.assertIn("reply 0",reply)
        self.assertEqual(events[-1],("finished",True))
        self.assertLess([e[0] for e in events].index("set_paused"),
                        [e[0] for e in events].index("send"))

    def test_case_whitespace_and_alternative_command(self):
        for text in ("  RESUME   AI  ","restart ai","Start AI","resume bot"):
            with self.subTest(text=text):
                _,events=self.run_chat(text,True)
                self.assertIn(("set_paused",False),events)

    def test_idempotent_when_already_active(self):
        result,events=self.run_chat("resume ai",False)
        self.assertEqual(result,("EVENT_RECEIVED",200))
        self.assertIn(("set_paused",False),events)

    def test_ordinary_messages_stay_paused(self):
        for text in ("hello","Show me your menu","0",
                     "I might resume AI later","Please resume my business registration"):
            with self.subTest(text=text):
                result,events=self.run_chat(text,True)
                self.assertEqual(result,("EVENT_RECEIVED",200))
                self.assertNotIn(("set_paused",False),events)
                self.assertFalse(any(e[0]=="send" for e in events))
                self.assertIn(("check_paused","265999111222"),events)

    def test_handover_explains_how_to_resume(self):
        tree=ast.parse(CODE)
        fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef)
                and x.name=="handle_local_human_handover")
        snippet=ast.get_source_segment(CODE,fn)
        self.assertIn("To return to AI support later, send: Resume AI",snippet)
        self.assertIn("set_ai_paused(customer_number, True)",snippet)

if __name__=="__main__": unittest.main()
