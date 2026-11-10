"""SDK request contracts, safe fallbacks and no-key offline mode."""
import json

import httpx
from fastapi.testclient import TestClient

from backend.ai.deepseek import DeepSeekProvider
from backend.ai.provider import make_provider
from backend.core.config import Settings
from backend.main import create_app


def sdk_settings(**values):
    return Settings(llm_provider='deepseek',deepseek_api_key='sdk-test-key',llm_base_url='https://api.deepseek.com',llm_model='deepseek-flash',llm_thinking='disabled',llm_timeout=2,**values)


def test_sdk_nonstream_and_stream_request_contract(tmp_path):
    requests=[]
    def handler(request):
        body=json.loads(request.content);requests.append(body)
        assert request.headers['authorization']=='Bearer sdk-test-key'
        assert body['model']=='deepseek-flash'
        assert body['thinking']=={'type':'disabled'}
        assert body['response_format']=={'type':'json_object'}
        raw=json.dumps({'reply':'你好呀！我是小星。','emotion':'happy','action':'jump'},ensure_ascii=False)
        if body.get('stream'):
            data=''.join('data: '+json.dumps({'id':'x','object':'chat.completion.chunk','created':1,'model':'deepseek-flash','choices':[{'index':0,'delta':{'content':part},'finish_reason':'stop' if part==raw[25:] else None}]},ensure_ascii=False)+'\n\n' for part in [raw[:25],raw[25:]])+'data: [DONE]\n\n'
            return httpx.Response(200,headers={'content-type':'text/event-stream'},text=data)
        return httpx.Response(200,json={'id':'x','object':'chat.completion','created':1,'model':'deepseek-flash','choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':raw}}]})
    provider=DeepSeekProvider(sdk_settings(),transport=httpx.MockTransport(handler))
    with TestClient(create_app(database_path=tmp_path/'sdk.db',settings=sdk_settings(),provider=provider)) as client:
        result=client.post('/api/chat',json={'message':'你叫什么名字？'})
        assert result.status_code==200,result.text
        assert result.json()['mode']=='deepseek' and '小星' in result.json()['reply']
        streamed=client.post('/api/chat/stream',json={'message':'你好'})
        assert 'event: done' in streamed.text
    assert requests[0].get('stream') is False
    assert requests[1]['stream'] is True


def test_plain_text_fallback_and_empty_reply(tmp_path):
    replies=iter(['你好呀！我是小星。','{"reply":"你好","emotion":"invalid","action":"jump"}','   '])
    def handler(request):
        return httpx.Response(200,json={'id':'x','object':'chat.completion','created':1,'model':'deepseek-flash','choices':[{'index':0,'message':{'role':'assistant','content':next(replies)},'finish_reason':'stop'}]})
    provider=DeepSeekProvider(sdk_settings(),transport=httpx.MockTransport(handler))
    with TestClient(create_app(database_path=tmp_path/'fallback.db',settings=sdk_settings(),provider=provider)) as client:
        first=client.post('/api/chat',json={'message':'你好'})
        assert first.status_code==200 and first.json()['fallback'] is True
        second=client.post('/api/chat',json={'message':'再你好'})
        assert second.status_code==200 and second.json()['reply']=='你好'
        assert second.json()['emotion']=='normal'
        assert client.post('/api/chat',json={'message':'空回复测试'}).status_code==502


def test_deepseek_missing_key_falls_back_to_mock(monkeypatch):
    settings=Settings(llm_provider='deepseek',deepseek_api_key='',llm_mode='auto')
    assert make_provider(settings).mode=='mock'


def test_deepseek_sdk_timeout_safe(tmp_path):
    def handler(request):
        raise httpx.ReadTimeout('sdk-test-key private upstream error')
    provider=DeepSeekProvider(sdk_settings(),transport=httpx.MockTransport(handler))
    with TestClient(create_app(database_path=tmp_path/'timeout.db',settings=sdk_settings(),provider=provider)) as client:
        result=client.post('/api/chat',json={'message':'你好'})
        assert result.status_code==504
        assert 'sdk-test-key' not in result.text and 'private upstream' not in result.text
