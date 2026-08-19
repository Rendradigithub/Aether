from src.aether.remote_perception import RemotePerceptionEncoder
from src.aether.orchestrator import AetherCognitiveCore
import threading, json, time
from http.server import BaseHTTPRequestHandler, HTTPServer
import shutil, os

if os.path.exists('test_workspace'):
    shutil.rmtree('test_workspace')

class MockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'embedding': [0.1]*384}).encode())
    def log_message(self, *args): pass

server = HTTPServer(('127.0.0.1', 8000), MockHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
time.sleep(1)

encoder = RemotePerceptionEncoder(endpoint='http://127.0.0.1:8000/encode', timeout=5.0)
core = AetherCognitiveCore(stimulus_source='assets/images/circle.png', perception_encoder=encoder, quiet=False, workspace='test_workspace')
for i in range(5):
    core.step()
print('SUCCESS: 5 cycles completed without dimension errors.')
server.shutdown()
