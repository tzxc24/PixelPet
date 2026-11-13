from datetime import datetime, timedelta, timezone
from uuid import uuid4
import re
import unicodedata
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


def parse_voice_reminder(text):
    query = unicodedata.normalize('NFKC', text).strip()
    match = re.fullmatch(
        r'(?:小[星心][，, ]*)?(?:请|帮我)?([0-9]{1,4}|[零〇一二两三四五六七八九十百千]{1,7})\s*分钟\s*(?:之|以)?后[，, ]*(?:提醒|叫)我(?:一下)?[，, ]*([^。！？?!]*?)[。！!]?',
        query)
    if not match:
        return None
    value, content = match.groups()
    if content.endswith(('吗', '么')):
        return None
    if value.isascii():
        minutes = int(value)
    else:
        digits = {char: n for n, char in enumerate('零一二三四五六七八九')} | {'两': 2, '〇': 0}
        minutes = digit = 0
        for char in value:
            if char in digits:
                digit = digits[char]
            else:
                minutes += (digit or 1) * {'十': 10, '百': 100, '千': 1000}[char]
                digit = 0
        minutes += digit
    return minutes, content.strip()


class ReminderInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=500)
    due_at: AwareDatetime


class ReminderScheduler:
    """Polling delivers reminders and optional local greetings; no cloud calls.

    Claiming before returning provides at-most-once delivery, including restarts.
    A crash after claiming can lose display, but cannot duplicate a reminder.
    """
    KEY = 'reminders.v1'

    def __init__(self, preferences):
        self.preferences = preferences

    def _mutate(self, operation):
        return self.preferences.mutate_json(self.KEY, {'items': [], 'counts': {}}, operation)

    def create(self, text, due_at, *, device_id=None):
        value = ReminderInput(text=text, due_at=due_at)
        item = {'id': uuid4().hex, 'text': value.text, 'due_at': value.due_at.astimezone(timezone.utc).isoformat(), 'delivered': False, 'status': 'pending'}
        if device_id is not None:
            item['device_id'] = device_id
        def add(state):
            if len(state['items']) >= 1000:
                raise ValueError('最多保存 1000 条提醒，请先删除旧提醒。')
            state['items'].append(item)
            return item.copy()
        return self._mutate(add)

    def list(self):
        return sorted(self.preferences.read_json(self.KEY, {'items': []})['items'], key=lambda item: item['due_at'])

    def delete(self, reminder_id):
        def remove(state):
            before = len(state['items'])
            state['items'] = [item for item in state['items'] if item['id'] != reminder_id]
            return len(state['items']) != before
        return self._mutate(remove)

    def next_device_reminder(self, device_id, now=None):
        now = now or datetime.now(timezone.utc)
        return next((item for item in self.list() if item.get('device_id') == device_id
                     and item['status'] == 'pending'
                     and timedelta(0) <= now - datetime.fromisoformat(item['due_at']) <= timedelta(hours=24)), None)

    def ack_device_reminder(self, device_id, reminder_id, now=None):
        now = now or datetime.now(timezone.utc)

        def ack(state):
            for item in state['items']:
                if item['id'] == reminder_id and item.get('device_id') == device_id and item['status'] == 'pending':
                    item.update(delivered=True, status='delivered', delivered_at=now.isoformat())
                    return True
            return False
        return self._mutate(ack)

    def poll(self, now=None):
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError('Polling time must contain a time zone.')
        now = now.astimezone(timezone.utc)
        preferences = self.preferences.get()
        local = now.astimezone(ZoneInfo(preferences.time_zone))
        clock = local.strftime('%H:%M')
        start, end = preferences.quiet_start, preferences.quiet_end
        quiet = start <= clock < end if start < end else (clock >= start or clock < end) if start > end else False
        day = local.date().isoformat()
        def claim(state):
            ready = []
            counts = state['counts']
            counts.setdefault(day, 0)
            # A bounded recent counter history survives restarts and zone changes.
            for old in sorted(counts)[:-40]:
                del counts[old]
            for item in sorted(state['items'], key=lambda value: value['due_at']):
                if item['status'] != 'pending':
                    continue
                due = datetime.fromisoformat(item['due_at'])
                if now - due > timedelta(hours=24):
                    item['status'] = 'expired'
                elif not item.get('device_id') and due <= now and not quiet and counts[day] < preferences.daily_limit:
                    item.update(delivered=True, status='delivered', delivered_at=now.isoformat())
                    counts[day] += 1
                    ready.append(item.copy() | {'type': 'reminder'})
            # Send at most one current-period greeting, never replay old periods.
            # Explicit reminders claim the shared daily quota first.
            if preferences.proactive_enabled and not quiet and counts[day] < preferences.daily_limit:
                periods = [(9, '早上好，记得喝点水，慢慢开启今天吧。'), (14, '下午好，忙了一会儿的话，可以伸个懒腰。'), (19, '晚上好，今天辛苦啦，留一点时间给自己。')]
                eligible = [(hour, text) for hour, text in periods if local.hour >= hour]
                if eligible:
                    hour, text = eligible[-1]
                    slot = f'{day}:{hour}'
                    sent = state.setdefault('proactive_slots', [])
                    if slot not in sent:
                        sent.append(slot)
                        state['proactive_slots'] = sent[-120:]
                        counts[day] += 1
                        ready.append({'id': f'proactive-{slot}', 'type': 'proactive', 'text': text, 'delivered': True, 'status': 'delivered', 'delivered_at': now.isoformat()})
            return ready
        return self._mutate(claim)
