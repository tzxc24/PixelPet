import json
import numpy as np
import httpx
import pytest
from backend.core.config import Settings
from backend.speech.service import SpeechError
from backend.speech.baidu_asr import BaiduASR

def settings(**kwargs):
    return Settings(baidu_asr_api_key='test-baidu-key',baidu_asr_secret_key='test-baidu-secret',**kwargs)

def test_baidu_pcm_request_and_token_cache():
    requests=[]
    def handle(request):
        requests.append(request)
        if request.url.path.endswith('/token'):
            assert request.method=='POST' and not request.url.query
            return httpx.Response(200,json={'access_token':'cached-access','expires_in':3600})
        body=json.loads(request.content)
        assert body['format']=='pcm' and body['rate']==16000 and body['channel']==1
        assert body['len']==3200 and body['dev_pid']==1537 and body['token']=='cached-access'
        return httpx.Response(200,json={'err_no':0,'result':['小星你好。']})
    provider=BaiduASR(settings(),transport=httpx.MockTransport(handle))
    assert provider.transcribe(np.zeros(1600,dtype=np.float32))['text']=='小星你好。'
    provider.transcribe(np.zeros(1600,dtype=np.float32))
    assert len(requests)==3
    status=json.dumps(provider.status())
    assert 'test-baidu' not in status and 'cached-access' not in status

def test_missing_baidu_keys_never_calls_network():
    def reject(request):
        raise AssertionError('No request is allowed without credentials')
    provider=BaiduASR(Settings(baidu_asr_api_key="", baidu_asr_secret_key=""),transport=httpx.MockTransport(reject))
    assert not provider.status()['ready']
    with pytest.raises(SpeechError) as error:
        provider.transcribe(np.zeros(1600,dtype=np.float32))
    assert error.value.code=='baidu_not_configured'

def test_baidu_auth_error_does_not_expose_credentials():
    def denied(request):
        return httpx.Response(200,json={'error':'invalid_client','error_description':'test-baidu-secret'})
    provider=BaiduASR(settings(),transport=httpx.MockTransport(denied))
    with pytest.raises(SpeechError) as error:
        provider.transcribe(np.zeros(1600,dtype=np.float32))
    assert 'test-baidu' not in str(error.value)

def test_baidu_timeout_is_friendly():
    def timeout(request):
        raise httpx.ReadTimeout('transport failure with secret',request=request)
    provider=BaiduASR(settings(),transport=httpx.MockTransport(timeout))
    with pytest.raises(SpeechError) as error:
        provider.transcribe(np.zeros(1600,dtype=np.float32))
    assert error.value.code=='baidu_timeout' and error.value.status==504

def test_baidu_no_speech_is_not_a_chat_message():
    def silence(request):
        if request.url.path.endswith('/token'):
            return httpx.Response(200,json={'access_token':'cached-access','expires_in':3600})
        return httpx.Response(200,json={'err_no':3301,'err_msg':'speech quality error'})
    provider=BaiduASR(settings(),transport=httpx.MockTransport(silence))
    with pytest.raises(SpeechError) as error:
        provider.transcribe(np.zeros(1600,dtype=np.float32))
    assert error.value.code=='no_speech'
