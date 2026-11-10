"""Upgrade a literal phase-one schema without discarding its conversations or memories."""
import sqlite3

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from backend.core.config import Settings
from backend.main import create_app


def test_legacy_upgrade_preserves_data_and_is_idempotent(tmp_path):
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as connection:
        connection.executescript('''
        CREATE TABLE user_profile (id VARCHAR(64) PRIMARY KEY,display_name VARCHAR(100) NOT NULL,profile_json TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE conversations (id VARCHAR(64) PRIMARY KEY,user_id VARCHAR(64) NOT NULL,created_at DATETIME NOT NULL);
        CREATE TABLE messages (id INTEGER PRIMARY KEY,conversation_id VARCHAR(64) NOT NULL,role VARCHAR(20) NOT NULL,content TEXT NOT NULL,created_at DATETIME NOT NULL);
        CREATE TABLE memories (id INTEGER PRIMARY KEY,user_id VARCHAR(64) NOT NULL,category VARCHAR(40) NOT NULL,memory_key VARCHAR(200) NOT NULL,content TEXT NOT NULL,updated_at DATETIME NOT NULL,UNIQUE(user_id,category,memory_key));
        CREATE TABLE pet_settings (id INTEGER PRIMARY KEY,user_id VARCHAR(64) NOT NULL,key VARCHAR(100) NOT NULL,value TEXT NOT NULL,UNIQUE(user_id,key));
        INSERT INTO user_profile VALUES ('owner','主人','{}');
        INSERT INTO conversations VALUES ('legacy','owner','2026-11-04 12:00:00');
        INSERT INTO messages VALUES (1,'legacy','user','旧消息','2026-11-04 12:00:00');
        INSERT INTO memories VALUES (1,'owner','project','legacy-project','ESP32 桌宠','2026-11-04 12:00:00');
        ''')
    for _ in range(2):
        app=create_app(database_path=path,settings=Settings(llm_mode='mock'))
        with TestClient(app) as client:
            assert len(inspect(app.state.engine).get_table_names())==5
            assert client.get('/api/conversations/legacy/messages').json()[0]['content']=='旧消息'
            assert client.get('/api/memories').json()[0]['content']=='ESP32 桌宠'
            assert client.get('/api/memories').json()[0]['source']=='legacy'
            assert client.post('/api/chat',json={'message':'你好','conversation_id':'legacy'}).status_code==200
