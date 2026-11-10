"""Run a business-protocol mock, never native xiaozhi/Opus traffic.
Default: isolated in-process FastAPI websocket. --url: optional websockets package.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

MESSAGES=['hello','heartbeat','audio.record_start','audio.record_stop','response']


def connection_options(url, environment=None):
    parsed = urlsplit(url)
    if parsed.scheme not in ('ws', 'wss') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use a ws:// or wss:// URL without credentials.')
    query = parse_qs(parsed.query)
    if any(name.lower() in ('token', 'access_token', 'api_key', 'key') for name in query):
        raise ValueError('Keep access tokens out of URLs; use PIXELPET_ACCESS_TOKEN.')
    token = (os.environ if environment is None else environment).get('PIXELPET_ACCESS_TOKEN', '')
    return {'additional_headers': {'Authorization': 'Bearer ' + token} if token else {}}

def run(ws):
    def receive():
        if hasattr(ws,'receive_json'): return ws.receive_json()
        return json.loads(ws.recv())
    def send(value):
        if hasattr(ws,'send_json'): return ws.send_json(value)
        return ws.send(json.dumps(value))
    assert receive()['type']=='device.connected'
    for kind in MESSAGES:
        send({'version':1,'type':kind,'payload':{}})
        reply=receive()
        assert reply['type']=='ack',reply
        print(kind,reply['type'])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',help='e.g. ws://127.0.0.1:8000/api/devices/ws?device_id=mock-client')
    args=parser.parse_args()
    if args.url:
        try:
            options = connection_options(args.url)
        except ValueError as exc:
            parser.error(str(exc))
        try:
            from websockets.sync.client import connect
        except ImportError:
            parser.error('Live socket requires optional package: python -m pip install websockets')
        for _ in range(2):
            with connect(args.url,max_size=16384,**options) as ws: run(ws)
    else:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.events import EventBus
        from backend.pet import PetEngine
        from backend.devices import DeviceService
        from backend.api.devices import router
        app=FastAPI()
        app.state.event_bus=EventBus()
        app.state.pet_engine=PetEngine(app.state.event_bus)
        app.state.devices=DeviceService(app.state.event_bus,app.state.pet_engine)
        app.include_router(router)
        with TestClient(app) as client:
            for _ in range(2):
                with client.websocket_connect('/api/devices/ws?device_id=mock-client') as ws: run(ws)
            assert not client.get('/api/devices').json()['devices'][0]['connected']
    print('PASS: connect/hello/audio-control/response/disconnect/reconnect (business JSON; no audio codec test)')

if __name__=='__main__': main()
