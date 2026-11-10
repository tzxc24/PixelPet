import json

from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app
from backend.ai.schemas import ModelReply


def test_all_sessions_and_old_messages_are_sent_once(tmp_path):
    app = create_app(database_path=tmp_path/'all.sqlite3', settings=Settings(llm_mode='mock'))
    prompts = []
    async def reply(messages):
        prompts.append(messages)
        return json.dumps({'reply':'好的','emotion':'normal','action':'idle','memories':[]})
    with TestClient(app) as http:
        app.state.provider.complete = reply
        store=app.state.store
        old=store.create_conversation()['id']
        for i in range(25):
            text=('最早那条不能丢失' if i==0 else str(i)) + 'a'*2100
            mid=store.begin_message(old,text)
            store.finish_message(old,mid,ModelReply(reply='reply '+str(i),emotion='normal',action='idle'),'mock')
        r=http.post('/api/chat',json={'message':'新会话的问题'})
        assert r.status_code==200
        messages=prompts[-1]
        assert len(messages)==52
        assert messages[1]['content']=='最早那条不能丢失'+'a'*2100
        assert sum(m['content']=='新会话的问题' for m in messages)==1
        assert all(any(m['content']==str(i)+'a'*2100 for m in messages) for i in range(1,25))
        assert len(store.messages(r.json()['conversation_id']))==2


def test_context_limit_reports_error_without_losing_user_message(tmp_path):
    app=create_app(database_path=tmp_path/'limit.sqlite3',settings=Settings(llm_mode='mock',llm_history_max_chars=1000))
    with TestClient(app) as http:
        cid=app.state.store.create_conversation()['id']
        mid=app.state.store.begin_message(cid,'a'*2000)
        app.state.store.finish_message(cid,mid,ModelReply(reply='好',emotion='normal',action='idle'),'mock')
        r=http.post('/api/chat',json={'message':'这条也要保存'})
        assert r.status_code==413
        assert r.json()['detail']['code']=='history_too_large'
        rows=http.get('/api/conversations').json()
        latest=http.get('/api/conversations/'+rows[0]['id']+'/messages').json()
        assert latest[-1]['content']=='这条也要保存'
        assert latest[-1]['status']=='failed'
