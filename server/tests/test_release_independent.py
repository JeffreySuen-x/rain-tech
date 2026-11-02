"""Independent synthetic transport acceptance; no external provider."""
import json, threading, time, unittest, subprocess
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from server.agent_provider import complete, ProviderFailure
from server.agent_runtime import AgentError

class IndependentTransport(unittest.TestCase):
    def test_transport_matrix(self):
        class Handler(BaseHTTPRequestHandler):
            mode = 'normal'
            def log_message(self, *args): pass
            def do_POST(self):
                mode = Handler.mode
                if mode == 'noresponse':
                    time.sleep(1); return
                self.rfile.read(int(self.headers['Content-Length']))
                if mode == 'headers':
                    time.sleep(1); return
                self.send_response(200); self.end_headers()
                if mode == 'slowbody':
                    time.sleep(1); return
                value = b'x' * 300000 if mode == 'outputlimit' else json.dumps({'choices':[{'message':{'content':'synthetic ok','tool_calls':[]}}]}).encode()
                try: self.wfile.write(value)
                except (BrokenPipeError, ConnectionResetError): pass
        server = ThreadingHTTPServer(('127.0.0.1',0), Handler); server.daemon_threads=True
        thread=threading.Thread(target=server.serve_forever); thread.start()
        config=dict(PROVIDER_URL=f'http://127.0.0.1:{server.server_port}', PROVIDER_MODEL='synthetic',PROVIDER_KEY='synthetic-secret',PRODUCTION=False)
        try:
            for mode in ('headers','noresponse','slowbody','largeinput','outputlimit','normal'):
                with self.subTest(mode=mode):
                    Handler.mode=mode
                    request={'messages':[{'role':'user','content':'x' * (20*1024*1024 if mode=='largeinput' else 1)}]}
                    started=time.monotonic()
                    children=[]
                    original_popen=subprocess.Popen
                    def capture(*args, **kwargs):
                        child=original_popen(*args, **kwargs); children.append(child); return child
                    patcher=patch('subprocess.Popen',capture); patcher.start()
                    if mode in ('headers','noresponse','slowbody'):
                        with self.assertRaises(AgentError) as caught: complete(config,request,timeout=.2)
                        self.assertEqual(caught.exception.code,'budget_exceeded')
                    elif mode=='outputlimit':
                        with self.assertRaises(ProviderFailure): complete(config,request,timeout=3)
                    else:
                        self.assertEqual(complete(config,request,timeout=5)['body'],'synthetic ok')
                    patcher.stop()
                    self.assertLess(time.monotonic()-started,1.7 if mode in ('headers','noresponse','slowbody') else 6)
                    self.assertTrue(children)
                    self.assertTrue(all(child.returncode is not None and child.poll() is not None for child in children))
                    self.assertFalse(any(t.name in ('provider-input','provider-output') for t in threading.enumerate()))
        finally:
            server.shutdown();server.server_close();thread.join()
