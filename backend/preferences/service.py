import json
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from backend.database.models import PetSetting
from backend.database.store import OWNER


class PetPreferences(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)
    name: str = Field(default='小星', min_length=1, max_length=40)
    volume: float = Field(default=1, ge=0, le=1)
    rate: float = Field(default=1, ge=0.5, le=2)
    voice: str = Field(default='zh-CN-XiaoyiNeural', max_length=200)
    pitch_hz: int = Field(default=0,ge=-12,le=12)
    microphone_id: str = Field(default='', max_length=500)
    brightness: float = Field(default=1, ge=0.1, le=1)
    animation_fps: int = Field(default=12, ge=1, le=30)
    haptics: bool = True
    haptic_strength: float = Field(default=0.6, ge=0, le=1)
    quiet_start: str = '22:00'
    quiet_end: str = '08:00'
    time_zone: str = 'Asia/Shanghai'
    time_format: Literal['12', '24'] = '24'
    proactive_enabled: bool = False
    daily_limit: int = Field(default=3, ge=0, le=100)
    asr_provider: Literal['local_whisper', 'baidu_asr', 'disabled'] = 'local_whisper'
    tts_provider: Literal['edge','sapi','browser','mock'] = 'edge'
    llm_model: str = Field(default='deepseek-flash', min_length=1, max_length=100)
    personality: str = Field(default='cute', min_length=1, max_length=100)

    @field_validator('quiet_start', 'quiet_end')
    @classmethod
    def validate_time(cls, value):
        parsed = datetime.strptime(value, '%H:%M')
        if parsed.strftime('%H:%M') != value:
            raise ValueError('Use HH:MM in 24-hour time.')
        return value

    @field_validator('time_zone')
    @classmethod
    def validate_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Unknown IANA time zone.') from None
        return value


class PreferencesService:
    def __init__(self, engine):
        self.engine = engine

    def read_json(self, key, default):
        with self.engine.connect() as connection:
            value = connection.execute(select(PetSetting.value).where(PetSetting.user_id == OWNER, PetSetting.key == key)).scalar_one_or_none()
        return json.loads(value) if value is not None else default

    def mutate_json(self, key, default, operation):
        """Serialize read/modify/write across connections and processes with SQLite."""
        with self.engine.connect() as connection:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            try:
                connection.exec_driver_sql('INSERT INTO user_profile (id, display_name, profile_json) VALUES (?, ?, ?) ON CONFLICT(id) DO NOTHING', (OWNER, '主人', '{}'))
                value = connection.execute(select(PetSetting.value).where(PetSetting.user_id == OWNER, PetSetting.key == key)).scalar_one_or_none()
                state = json.loads(value) if value is not None else default
                result = operation(state)
                connection.exec_driver_sql('INSERT INTO pet_settings (user_id, key, value) VALUES (?, ?, ?) ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value', (OWNER, key, json.dumps(state, ensure_ascii=False)))
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def get(self):
        return PetPreferences.model_validate(self.read_json('preferences.v1', {}))

    def is_quiet(self, now=None):
        value = self.get()
        local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(value.time_zone))
        clock = local.strftime('%H:%M')
        start, end = value.quiet_start, value.quiet_end
        return start <= clock < end if start < end else (clock >= start or clock < end) if start > end else False

    def update(self, changes):
        def apply(state):
            validated = PetPreferences.model_validate(state | changes)
            state.clear()
            state.update(validated.model_dump())
            return validated
        return self.mutate_json('preferences.v1', {}, apply)
