"""Actual localhost HTTP/SSE verifies the compatibility adapter, not a cloud-model claim."""
import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.ai.provider import OpenAICompatibleProvider
from backend.chat.service import partial_reply
from backend.core.config import Settings
from backend.main import create_app


@pytest.fixture
def wire_server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.server.requests.append((self.path,self.headers.get("Authorization"),body))
            behavior=self.server.behavior
            if behavior=="error":
                self.send_response(401);self.end_headers()
                self.wfile.write(b'private-provider-detail test-wire-secret')
                return
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.end_headers()
            result={"reply":"主人回来啦！\n一颗星星：⭐","emotion":"happy","action":"jump","memories":[]}
            if behavior=="invalid":
                result["emotion"]="alien"
            if behavior=="memory":
                result["memories"]=[{"category":"project","content":"主人正在造火箭","importance":.9}]
            raw=json.dumps(result,ensure_ascii=True)
            try:
                if behavior=="timeout":
                    time.sleep(.2)
                for i in range(0,len(raw),7):
                    if behavior=="slow":
                        time.sleep(.015)
                    event=json.dumps({"choices":[{"delta":{"content":raw[i:i+7]}}]})
                    self.wfile.write(('data: '+event+'\n\n').encode());self.wfile.flush()
                self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
                pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.behavior="ok";server.requests=[]
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    yield server
    server.shutdown();server.server_close();worker.join(timeout=2)


def settings(server,timeout=3):
    return Settings(llm_provider="openai",llm_mode="openai",llm_base_url=f"http://127.0.0.1:{server.server_port}/v1",llm_model="wire-model",llm_api_key="test-wire-secret",llm_timeout=timeout)


def test_real_http_adapter_auth_context_and_stream(tmp_path,wire_server):
    with TestClient(create_app(database_path=tmp_path/"wire.db",settings=settings(wire_server))) as client:
        first=client.post('/api/chat',json={"message":"你好，小星"})
        assert first.status_code==200,first.text
        cid=first.json()["conversation_id"]
        response=client.post('/api/chat/stream',json={"message":"我刚才说了什么？","conversation_id":cid})
        assert 'event: delta' in response.text and 'event: done' in response.text
        assert 'test-wire-secret' not in response.text
        path,auth,body=wire_server.requests[-1]
        assert path=='/v1/chat/completions' and auth=='Bearer test-wire-secret'
        assert body['stream'] is True and body['model']=='wire-model'
        assert any(m['content']=='你好，小星' for m in body['messages'])
        assert all('test-wire-secret' not in m['content'] for m in body['messages'])
        assert client.get(f'/api/conversations/{cid}/messages').json()[-1]['content']=='主人回来啦！\n一颗星星：⭐'


@pytest.mark.parametrize('behavior,code',[('timeout',504),('slow',504),('error',502),('invalid',502)])
def test_timeout_bad_payload_and_upstream_errors_are_safe(tmp_path,wire_server,behavior,code):
    wire_server.behavior=behavior
    timeout=.08 if behavior in ('timeout','slow') else 3
    with TestClient(create_app(database_path=tmp_path/'failure.db',settings=settings(wire_server,timeout))) as client:
        response=client.post('/api/chat',json={"message":"你好"})
        assert response.status_code==code,response.text
        assert 'test-wire-secret' not in response.text and 'private-provider-detail' not in response.text
        cid=response.json()['detail']['conversation_id']
        messages=client.get(f'/api/conversations/{cid}/messages').json()
        assert len(messages)==1 and messages[0]['status']=='failed'
        wire_server.behavior='ok'
        assert client.post('/api/chat',json={"message":"再试一次","conversation_id":cid}).status_code==200


def test_stream_error_event_and_grounding(tmp_path,wire_server):
    with TestClient(create_app(database_path=tmp_path/'bad.db',settings=settings(wire_server))) as client:
        wire_server.behavior='invalid'
        response=client.post('/api/chat/stream',json={'message':'你好'})
        assert 'event: error' in response.text and 'event: done' not in response.text
        wire_server.behavior='memory'
        assert client.post('/api/chat',json={'message':'我喜欢喝绿茶'}).status_code==200
        assert '火箭' not in client.get('/api/memories').text


def test_partial_json_unicode_and_escapes():
    raw=json.dumps({'reply':'他说："你好"\n星星⭐','emotion':'normal','action':'idle'},ensure_ascii=True)
    previous=''
    for i in range(1,len(raw)+1):
        decoded=partial_reply(raw[:i])
        assert decoded.startswith(previous)
        previous=decoded
    assert previous=='他说："你好"\n星星⭐'


def test_generic_provider_rejects_truncated_stream_and_bad_shape(tmp_path):
    for index,content in enumerate(['data: []\n\n','data: '+json.dumps({'choices':[{'delta':{'content':'{"reply":"截断","emotion":"happy","action":"jump"}'}}]})+'\n\n']):
        settings_value=Settings(llm_provider='openai',llm_base_url='http://unit/v1',llm_api_key='not-a-real-key',llm_model='unit')
        provider=OpenAICompatibleProvider(settings_value,transport=httpx.MockTransport(lambda request:httpx.Response(200,text=content,headers={'content-type':'text/event-stream'})))
        with TestClient(create_app(database_path=tmp_path/f'truncated-{index}.db',settings=settings_value,provider=provider)) as client:
            response=client.post('/api/chat',json={'message':'你好'})
            assert response.status_code==502
            cid=response.json()['detail']['conversation_id']
            assert len(client.get(f'/api/conversations/{cid}/messages').json())==1


def test_busy_and_cancellation_release(tmp_path):
    class GateProvider:
        mode='mock'
        async def stream(self,messages):
            self.started.set()
            await self.gate.wait()
            yield '{"reply":"好呀","emotion":"happy","action":"jump","memories":[]}'
        async def close(self):
            pass
    async def scenario():
        provider=GateProvider();provider.started=asyncio.Event();provider.gate=asyncio.Event()
        app=create_app(database_path=tmp_path/'busy.db',settings=Settings(llm_mode='mock'),provider=provider)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1') as client:
                cid=(await client.post('/api/conversations')).json()['id']
                pending=asyncio.create_task(client.post('/api/chat',json={'message':'你好','conversation_id':cid}))
                await provider.started.wait()
                assert (await client.post('/api/chat',json={'message':'同时发送','conversation_id':cid})).status_code==409
                assert (await client.delete(f'/api/conversations/{cid}')).status_code==409
                provider.gate.set()
                assert (await pending).status_code==200
                turn=app.state.chat.begin('中断测试',cid)
                generator=app.state.chat.events(turn)
                assert (await generator.__anext__())[0]=='meta'
                await generator.aclose()
                assert cid not in app.state.chat.active
                assert app.state.store.messages(cid)[-1]['status']=='failed'
    asyncio.run(scenario())
