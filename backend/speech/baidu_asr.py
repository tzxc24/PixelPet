"""Baidu short-speech REST adapter. Credentials and tokens remain in the backend."""
import base64
import threading
import time

import httpx
import numpy as np

from backend.speech.service import SpeechError

TOKEN_URL = 'https://aip.baidubce.com/oauth/2.0/token'
ASR_URL = 'https://vop.baidu.com/server_api'


class BaiduASR:
    name = 'baidu_asr'

    def __init__(self, settings, transport=None):
        key = getattr(settings, 'baidu_asr_api_key', '')
        secret = getattr(settings, 'baidu_asr_secret_key', '')
        self._key = key.get_secret_value() if hasattr(key, 'get_secret_value') else str(key)
        self._secret = secret.get_secret_value() if hasattr(secret, 'get_secret_value') else str(secret)
        self.timeout = getattr(settings, 'baidu_asr_timeout', 20)
        self.dev_pid = getattr(settings, 'baidu_asr_dev_pid', 1537)
        self.transport = transport
        self._token = None
        self._expires_at = 0
        self._lock = threading.Lock()
        self.last_success = None

    def status(self):
        configured = bool(self._key.strip() and self._secret.strip())
        return {'provider': self.name, 'ready': configured, 'configured': configured,
                'network_required': True, 'network_verified': self.last_success is not None,
                'model': 'baidu-' + str(self.dev_pid),
                'message': '百度在线语音识别' if configured else '请在本机配置 BAIDU_ASR_API_KEY 和 BAIDU_ASR_SECRET_KEY'}

    def _access_token(self, client):
        if self._token and time.monotonic() < self._expires_at:
            return self._token
        response = client.post(TOKEN_URL, data={
            'grant_type': 'client_credentials', 'client_id': self._key, 'client_secret': self._secret})
        response.raise_for_status()
        result = response.json()
        token = result.get('access_token')
        expires = result.get('expires_in', 0)
        if not isinstance(token, str) or not token or not isinstance(expires, (int, float)) or expires <= 0:
            raise SpeechError(503, 'baidu_auth_failed', '百度语音授权失败，请检查本机密钥和应用权限。')
        self._token = token
        self._expires_at = time.monotonic() + max(0, expires - 60)
        return token

    def transcribe(self, samples):
        if not self.status()['configured']:
            raise SpeechError(503, 'baidu_not_configured', '百度语音尚未配置密钥，请填写本机配置或选择本地 Whisper。')
        samples = np.asarray(samples)
        if samples.ndim != 1 or not 0 < samples.size <= 60 * 16000 or not np.isfinite(samples).all():
            raise SpeechError(422, 'invalid_audio', '百度识别需要 60 秒以内的有效单声道音频。')
        pcm = np.clip(np.rint(samples * 32768), -32768, 32767).astype('<i2').tobytes()
        try:
            with self._lock, httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                for attempt in range(2):
                    payload = {'format': 'pcm', 'rate': 16000, 'channel': 1,
                               'cuid': 'pixelpet-pc', 'token': self._access_token(client),
                               'dev_pid': self.dev_pid, 'len': len(pcm),
                               'speech': base64.b64encode(pcm).decode('ascii')}
                    response = client.post(ASR_URL, json=payload)
                    response.raise_for_status()
                    result = response.json()
                    code = result.get('err_no')
                    if code == 3302 and attempt == 0:
                        self._token = None
                        continue
                    if code == 3301:
                        raise SpeechError(422, 'no_speech', '百度没有识别出清晰语音，请靠近麦克风重试。')
                    if code != 0:
                        raise SpeechError(503, 'baidu_asr_error', '百度语音识别未完成，请检查控制台的权限、用量及音频要求。')
                    words = result.get('result')
                    if not isinstance(words, list) or not words or not all(isinstance(word, str) for word in words):
                        raise SpeechError(502, 'baidu_invalid_response', '百度语音返回了无法解析的结果。')
                    text = ''.join(words).strip()
                    if not text:
                        raise SpeechError(422, 'no_speech', '这段录音未识别到文字。')
                    self.last_success = time.time()
                    return {'text': text, 'language': 'zh'}
        except SpeechError:
            raise
        except httpx.TimeoutException:
            raise SpeechError(504, 'baidu_timeout', '百度语音识别超时，请稍后重试。') from None
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                raise SpeechError(503, 'baidu_auth_failed', '百度语音授权失败，请检查本机密钥和应用权限。') from None
            raise SpeechError(503, 'baidu_unavailable', '百度语音服务暂时不可用，请稍后重试。') from None
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            raise SpeechError(503, 'baidu_unavailable', '百度语音服务暂时不可用，请稍后重试。') from None
