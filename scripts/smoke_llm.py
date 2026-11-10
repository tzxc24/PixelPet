"""Explicit real-model acceptance run; uses an isolated D-drive SQLite database."""
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from fastapi.testclient import TestClient
from backend.core.config import Settings
from backend.main import create_app


def run():
    settings=Settings()
    folder=ROOT/'tmp'/('live-smoke-'+uuid4().hex)
    folder.mkdir(parents=True)
    database=folder/'smoke.sqlite3'
    records=[]
    def send(client,message,cid=None):
        payload={'message':message}
        if cid:payload['conversation_id']=cid
        response=client.post('/api/chat',json=payload)
        if response.status_code!=200:
            raise RuntimeError('真实模型测试失败：'+str(response.json().get('detail','服务异常')))
        result=response.json()
        records.append({'user':message,'reply':result['reply'],'emotion':result['emotion'],'action':result['action'],'mode':result['mode'],'fallback':result['fallback']})
        return result
    with TestClient(create_app(database_path=database,settings=settings)) as client:
        mode=client.get('/api/status').json()['mode']
        if mode=='mock':
            raise RuntimeError('当前是 Mock 模式；此脚本必须在本机配置真实模型密钥后手动执行。')
        first=send(client,'你好小星，你叫什么名字？')
        assert '小星' in first['reply'],'模型没有返回角色名称'
        cid=first['conversation_id']
        send(client,'请记住：我正在开发 ESP32 AI 桌宠 PixelPet。',cid)
        follow=send(client,'我刚才说我在开发什么？',cid)
        assert 'ESP32' in follow['reply'] or 'PixelPet' in follow['reply'],'缺少多轮上下文'
        assert len(client.get(f'/api/conversations/{cid}/messages').json())==6
    with TestClient(create_app(database_path=database,settings=settings)) as client:
        assert len(client.get(f'/api/conversations/{cid}/messages').json())==6
        response=client.post('/api/chat/stream',json={'message':'你还记得我最近正在开发什么吗？'})
        events=[]
        for block in response.text.split('\n\n'):
            lines=block.splitlines()
            if len(lines)==2:events.append((lines[0][7:],json.loads(lines[1][6:])))
        if not events or events[-1][0]!='done':
            error=next((data.get('message') for name,data in events if name=='error'),'未收到完整回复')
            raise RuntimeError('流式实测失败：'+error)
        done=events[-1][1]
        assert 'ESP32' in done['reply'] or 'PixelPet' in done['reply'],'未命中跨会话记忆'
        assert any(name=='delta' for name,_ in events),'未收到流式文本'
        records.append({'user':'重启后跨会话回忆（流式）','reply':done['reply'],'emotion':done['emotion'],'action':done['action'],'mode':done['mode'],'fallback':done['fallback']})
    report={'mode':mode,'model':settings.llm_model,'thinking':settings.llm_thinking,'checks':['真实认证与中文非流式','角色名称','多轮上下文','SQLite消息持久化','应用重启恢复','跨会话长期记忆','真实流式delta/done','结构化情绪动作'],'passed':True,'records':records}
    path=ROOT/'output'/'live-llm-verification.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    try:
        run()
    except (RuntimeError,AssertionError) as exc:
        print(str(exc))
        sys.exit(1)
