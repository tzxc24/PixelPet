"""Short SQLite transactions; never hold a write transaction while awaiting an LLM."""
import json
from datetime import timezone
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.database.models import Conversation, Memory, Message, UserProfile, now
from backend.memory.logic import fact_key, rank, safe_memory, similar

OWNER = "owner"


class Missing(Exception):
    pass


def timestamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()


def memory_dict(row):
    return {name:getattr(row,name) for name in ("id","category","memory_key","content","importance","source","confirmed","confidence")} | {"updated_at":timestamp(row.updated_at),"created_at":timestamp(row.created_at or row.updated_at)}


def message_dict(row):
    return {name:getattr(row,name) for name in ("id","role","content","emotion","action","status","mode")} | {"created_at":timestamp(row.created_at)}


class Store:
    def __init__(self, engine, memory_decay_days=90):
        self.engine = engine
        self.memory_decay_days=memory_decay_days

    @staticmethod
    def ensure_owner(session):
        profile=session.get(UserProfile,OWNER)
        if profile is None:
            profile=UserProfile(id=OWNER)
            session.add(profile)
            session.flush()
        return profile

    @staticmethod
    def require_conversation(session, cid):
        row=session.get(Conversation,cid)
        if row is None or row.user_id != OWNER:
            raise Missing("会话不存在。")
        return row

    def create_conversation(self, title="新对话"):
        with Session(self.engine) as session, session.begin():
            self.ensure_owner(session)
            row=Conversation(id=uuid4().hex,user_id=OWNER,title=title[:100])
            session.add(row)
            session.flush()
            return {"id":row.id,"title":row.title,"created_at":row.created_at.isoformat()}

    def conversations(self):
        with Session(self.engine) as session:
            return [{"id":r.id,"title":r.title,"created_at":r.created_at.isoformat()} for r in session.scalars(select(Conversation).where(Conversation.user_id==OWNER).order_by(Conversation.created_at.desc()))]

    def messages(self,cid):
        with Session(self.engine) as session:
            self.require_conversation(session,cid)
            return [message_dict(r) for r in session.scalars(select(Message).where(Message.conversation_id==cid).order_by(Message.id))]

    def context(self,cid):
        with Session(self.engine) as session:
            rows=list(session.scalars(select(Message).where(Message.conversation_id==cid,Message.status=="complete").order_by(Message.id.desc()).limit(20)))
            result=[]
            remaining=12000
            for row in rows:
                if remaining<=200:
                    break
                content=row.content[-min(remaining-180,2000):]
                if row.role=="assistant":
                    # Preserve the structured-output examples across turns; sending
                    # plain assistant history can bias JSON-mode models toward blanks.
                    content=json.dumps({"reply":content,"emotion":row.emotion,"action":row.action,"memories":[]},ensure_ascii=False)
                remaining-=len(content)
                result.append({"role":row.role,"content":content})
            return list(reversed(result))

    def full_context(self, before_message_id):
        """All stored owner conversations in message order, with no text clipping."""
        with Session(self.engine) as session:
            rows=session.scalars(select(Message).join(Conversation)
                .where(Conversation.user_id==OWNER, Message.id<before_message_id)
                .order_by(Message.id))
            result=[]
            for row in rows:
                if row.role not in ('user','assistant'):
                    continue
                content=row.content
                if row.role=='assistant':
                    content=json.dumps({'reply':content,'emotion':row.emotion,'action':row.action,'memories':[]},ensure_ascii=False)
                result.append({'role':row.role,'content':content})
            return result

    def begin_message(self,cid,content):
        with Session(self.engine) as session, session.begin():
            conversation=self.require_conversation(session,cid)
            if conversation.title=="新对话":
                conversation.title=content[:32]
            row=Message(conversation_id=cid,role="user",content=content,status="pending")
            session.add(row)
            session.flush()
            return row.id

    def finish_message(self,cid,mid,reply,mode):
        with Session(self.engine) as session, session.begin():
            user=session.get(Message,mid)
            if user is None:
                raise Missing("消息不存在。")
            user.status="complete"
            row=Message(conversation_id=cid,role="assistant",content=reply.reply,emotion=reply.emotion,action=reply.action,status="complete",mode=mode)
            session.add(row)
            session.flush()
            return row.id

    def fail_message(self,mid):
        with Session(self.engine) as session, session.begin():
            row=session.get(Message,mid)
            if row is not None and row.status=="pending":
                row.status="failed"

    def delete_conversation(self,cid,clear_only=False):
        with Session(self.engine) as session, session.begin():
            conversation=self.require_conversation(session,cid)
            session.execute(delete(Message).where(Message.conversation_id==cid))
            if not clear_only:
                session.delete(conversation)
            else:
                conversation.title="新对话"

    def memories(self,query=None):
        with Session(self.engine) as session:
            rows=[memory_dict(r) for r in session.scalars(select(Memory).where(Memory.user_id==OWNER).order_by(Memory.updated_at.desc()))]
        return rank(rows,query,8,self.memory_decay_days) if query is not None else rows

    @staticmethod
    def sync_profile(session):
        profile=session.get(UserProfile,OWNER)
        rows=list(session.scalars(select(Memory).where(Memory.user_id==OWNER)))
        names=[r for r in rows if r.memory_key=="name"]
        profile.display_name=names[-1].content.removeprefix("主人叫") if names else "主人"
        profile.profile_json=json.dumps({"basic":[r.content for r in rows if r.category=="basic"],"preferences":[r.content for r in rows if r.category in ("preference","interest")]},ensure_ascii=False)

    def upsert_memory(self,category,content,importance=.8,source="manual",memory_id=None,confirmed=None):
        if not safe_memory(content):
            raise ValueError("敏感内容不能保存为长期记忆。")
        key=fact_key(category,content)
        with Session(self.engine) as session, session.begin():
            self.ensure_owner(session)
            rows=list(session.scalars(select(Memory).where(Memory.user_id==OWNER)))
            if memory_id is not None:
                row=next((r for r in rows if r.id==memory_id),None)
                if row is None:
                    raise Missing("记忆不存在。")
            else:
                row=next((r for r in rows if r.category==category and (r.memory_key==key or similar(r.content,content))),None)
            duplicate=next((r for r in rows if r.id!=(row.id if row else None) and r.category==category and r.memory_key==key),None)
            if duplicate is not None:
                # Editing onto an existing fact merges both rows rather than violating uniqueness.
                session.delete(duplicate)
                session.flush()
            if row is None:
                row=Memory(user_id=OWNER,category=category,memory_key=key,content=content,importance=importance,source=source)
                session.add(row)
            else:
                row.category,row.memory_key,row.content=category,key,content
                row.importance=importance if memory_id is not None else max(row.importance,importance)
                row.source=source
                row.updated_at=now()
            session.flush()
            row.confirmed=confirmed if confirmed is not None else (bool(row.confirmed) or source=='manual' or (source.startswith('user:') and importance>=.98))
            row.confidence=max(row.confidence or 0,1.0 if source=='manual' else .95 if source.startswith('user:') else .8)
            self.sync_profile(session)
            return memory_dict(row)

    def delete_memory(self,mid):
        with Session(self.engine) as session, session.begin():
            row=session.get(Memory,mid)
            if row is None or row.user_id!=OWNER:
                raise Missing("记忆不存在。")
            session.delete(row)
            session.flush()
            self.sync_profile(session)

    def profile(self):
        with Session(self.engine) as session, session.begin():
            row=self.ensure_owner(session)
            return {"id":row.id,"display_name":row.display_name,"profile":json.loads(row.profile_json)}
