"""Windows launcher recognizes an existing instance before starting another app."""
import json
import os
from pathlib import Path
import subprocess
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

import pytest
from backend.release import VERSION

pytestmark=pytest.mark.skipif(os.name!='nt',reason='Windows PowerShell launcher')
ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('version,expected_code',[(VERSION,0),('1.0.0',4),(None,2)])
def test_occupied_port_is_handled_without_second_server(version,expected_code):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            data=({'version':version,'mode':'mock','streaming':True,'persistent_history':True} if self.path=='/api/status' else {'info':{'title':'PixelPet · 小星'}}) if version else {'detail':'another service'}
            encoded=json.dumps(data).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        result=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/start.ps1'),'-Port',str(server.server_port)],cwd=ROOT/'tmp',capture_output=True,text=True,errors='replace',timeout=15)
        assert result.returncode==expected_code,result.stdout+result.stderr
        assert 'Started server process' not in result.stdout+result.stderr
        if version:assert 'already running' in result.stdout
        else:assert 'another service' in result.stdout
    finally:
        server.shutdown();server.server_close();worker.join(timeout=2)
