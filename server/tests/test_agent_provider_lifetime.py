import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from server.agent_provider import complete
from server.agent_runtime import AgentError

class Lifetime(unittest.TestCase):
    def test_slow_body_and_cancel_release(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200); self.end_headers()
                try:
                    for _ in range(80):
                        self.wfile.write(b' '); self.wfile.flush(); time.sleep(.05)
                except (BrokenPipeError, ConnectionResetError): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever); thread.start()
        config = dict(PROVIDER_URL='http://127.0.0.1:'+str(server.server_port), PROVIDER_MODEL='synthetic', PROVIDER_KEY='synthetic', PRODUCTION=False)
        try:
            for cancel in (False, True):
                started = time.monotonic()
                def progress():
                    if cancel and time.monotonic()-started > .2:
                        raise AgentError('cancelled', '任务已停止')
                with self.assertRaises(AgentError) as error:
                    complete(config, {'messages': [{'role':'user','content':'test'}]}, timeout=.4, check_progress=progress)
                self.assertEqual(error.exception.code, 'cancelled' if cancel else 'budget_exceeded')
                self.assertLess(time.monotonic()-started, 1.5)
                self.assertFalse(any(t.name in ('provider-input', 'provider-output') for t in threading.enumerate()))
        finally:
            server.shutdown(); server.server_close(); thread.join()
