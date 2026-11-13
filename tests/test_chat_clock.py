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
