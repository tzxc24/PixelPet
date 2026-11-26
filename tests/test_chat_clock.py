from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from unittest.mock import patch
from backend.chat.service import ChatService

def test_clock_uses_current_time_and_preferred_zone():
    chat = ChatService.__new__(ChatService)
    chat.preferences = SimpleNamespace(get=lambda: SimpleNamespace(time_zone='Asia/Shanghai', time_format='12'))
    with patch('backend.chat.service.datetime') as clock:
        clock.now.return_value = datetime(2026, 11, 13, 21, 4)
        assert chat.clock_reply('小星，现在几点了？').reply == '现在是下午9点04分。'
        clock.now.assert_called_once_with(ZoneInfo('Asia/Shanghai'))
    assert chat.clock_reply('明天几点开会？') is None


def test_voice_clock_variants():
    chat = ChatService.__new__(ChatService)
    for phrase in ('现在几点了呀', '能告诉我现在几点了吗', '帮我看一下现在几点', '现在几点了？我得去干活了。'):
        assert chat.clock_reply(phrase).reply.startswith('现在是')
    assert chat.clock_reply('现在几点出发合适') is None

def test_health_followup_crosses_conversations_and_is_delivered_once(tmp_path):
    from backend.ai.schemas import ModelReply
    from backend.database.engine import initialize_database
    from backend.preferences.service import PreferencesService

    engine = initialize_database(tmp_path / 'followup.sqlite')
    try:
        chat = ChatService.__new__(ChatService)
        chat.preferences = PreferencesService(engine)
        reply = ModelReply(reply='知道了。', emotion='normal', action='speak',
                           followup_topic='sleep', followup_summary='最近睡不好')
        assert chat.apply_followup(reply).reply == reply.reply
        assert chat.preferences.read_json(chat.FOLLOWUP_KEY, {})['tasks']['sleep']
        chat.apply_followup(reply)
        chat.apply_followup(reply)
        state = chat.preferences.read_json(chat.FOLLOWUP_KEY, {})
        assert len(state['tasks']) == 1
        with patch('backend.chat.service.datetime') as clock:
            from datetime import timedelta, timezone
            clock.now.return_value = datetime.now(timezone.utc) + timedelta(days=4)
            assert '最近睡不好。现在怎么样了' in chat.apply_followup(reply).reply
            normal = reply.model_copy(update={'followup_topic': None})
            assert chat.apply_followup(normal).reply == normal.reply
        assert chat.followup_control('关闭健康回访')
        assert not chat.preferences.read_json(chat.FOLLOWUP_KEY, {})['enabled']
    finally:
        engine.dispose()
