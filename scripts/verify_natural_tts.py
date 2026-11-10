"""Opt-in live Edge verification using one public comparison sentence."""
import io
import json
import argparse
from pathlib import Path
import sys
import time
import wave

import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.speech.providers import PREVIEW_TEXT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-chat',action='store_true',help='Also call the configured real LLM in an isolated test database.')
    args=parser.parse_args()
    output=ROOT/'output'/'natural-voice'
    output.mkdir(parents=True,exist_ok=True)
    report={'text':PREVIEW_TEXT,'physical_speaker_audibility_verified':False,'hardware':'HW_PENDING','voices':[]}
    with httpx.Client(base_url='http://127.0.0.1:8765',timeout=60) as client:
        for voice in ('zh-CN-XiaoyiNeural','zh-CN-XiaoxiaoNeural','zh-CN-YunxiNeural'):
            started=time.monotonic()
            response=client.post('/api/audio/synthesize',json={'text':PREVIEW_TEXT,'provider':'edge','voice':voice,'rate_percent':0,'pitch_hz':0,'volume_percent':0,'allow_fallback':False})
            response.raise_for_status()
            assert response.headers['x-audio-provider']=='edge'
            assert response.headers['x-audio-voice']==voice
            assert response.headers['x-audio-fallback']=='none'
            with wave.open(io.BytesIO(response.content),'rb') as audio:
                assert audio.getframerate()==24000 and audio.getnchannels()==1 and audio.getsampwidth()==2
                duration=audio.getnframes()/audio.getframerate()
                assert duration>1
            path=output/f'{voice}.wav'
            path.write_bytes(response.content)
            item={'voice':voice,'bytes':len(response.content),'duration':round(duration,4),'elapsed_ms':round((time.monotonic()-started)*1000),'headers':{k:v for k,v in response.headers.items() if k.startswith('x-audio-')},'file':str(path)}
            report['voices'].append(item)
            print(voice,item['bytes'],item['duration'],item['elapsed_ms'],flush=True)
        unavailable=client.post('/api/audio/synthesize',json={'text':PREVIEW_TEXT,'provider':'edge','voice':'zh-CN-XiaomengNeural','allow_fallback':False})
        assert unavailable.status_code==422
        report['xiaomeng']={'available':False,'status':422,'reason':'Not present in verified Edge catalogue; no substitute is represented as Xiaomeng.'}
    if args.with_chat:
        from uuid import uuid4
        from fastapi.testclient import TestClient
        from backend.core.config import Settings
        from backend.main import create_app
        database=ROOT/'tmp'/f'natural-voice-chat-{uuid4().hex}.sqlite3'
        with TestClient(create_app(database_path=database,settings=Settings())) as client:
            status=client.get('/api/status').json()
            assert status['mode']!='mock','Real LLM verification requires configured credentials.'
            reply=client.post('/api/chat',json={'message':'你好小星，请用一句简短的话向我打招呼。'})
            reply.raise_for_status()
            data=reply.json()
            speech=client.post('/api/audio/synthesize',json={'text':data['reply'],'provider':'edge','voice':'zh-CN-XiaoyiNeural','emotion':data['emotion'],'allow_fallback':False})
            speech.raise_for_status()
            assert speech.headers['x-audio-provider']=='edge'
            (output/'deepseek-reply.wav').write_bytes(speech.content)
            report['chat_to_speech']={'mode':status['mode'],'model':status['model'],'reply':data['reply'],'emotion':data['emotion'],'provider':speech.headers['x-audio-provider'],'audio_bytes':len(speech.content),'isolated_database':str(database)}
            print('Real chat -> Edge speech passed',flush=True)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
