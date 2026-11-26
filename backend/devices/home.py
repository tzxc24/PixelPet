"""Persistent, device-scoped lamp targets and one-shot music alarms."""
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import av
import numpy as np
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from typing import Literal

from backend.preferences.scheduler import parse_voice_reminder
from backend.speech.service import AudioResult

TRACKS = {
    "morning": ("晨间铃声", "01_morning_chime.wav"),
    "wakeup": ("起床旋律", "02_wakeup_loop.wav"),
    "sunbeam": ("阳光跳跃", "06_sunbeam_bounce.wav"),
}


class LampInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    mode: Literal["steady", "fade", "breath"] = "steady"
    level: int = Field(default=100, ge=0, le=100)
    seconds: int = Field(default=3, ge=1, le=600)


class AlarmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    due_at: AwareDatetime
    track: Literal["morning", "wakeup", "sunbeam"] = "morning"
    wake_light: bool = False


def number(text):
    parsed = parse_voice_reminder(text + "分钟后提醒我")
    return parsed[0] if parsed else None


class HomeControl:
    KEY = "home-control.v1"

    def __init__(self, preferences, music_root):
        self.preferences = preferences
        self.music_root = Path(music_root)

    def mutate(self, fn):
        return self.preferences.mutate_json(self.KEY, {"devices": {}, "alarms": []}, fn)

    def snapshot(self):
        return self.preferences.read_json(self.KEY, {"devices": {}, "alarms": []})

    def lamp(self, device, value):
        value = LampInput.model_validate(value).model_dump()
        def update(state):
            target = state["devices"].setdefault(device, {})
            revision = target.get("lamp", {}).get("revision", 0) + 1
            target["lamp"] = dict(value, revision=revision)
            return target["lamp"].copy()
        return self.mutate(update)

    def create(self, value):
        value = AlarmInput.model_validate(value)
        now = datetime.now(timezone.utc)
        if value.due_at <= now:
            raise ValueError("请选择将来的时间。")
        item = dict(value.model_dump(mode="json"), id=uuid4().hex, status="pending")
        def add(state):
            if len(state["alarms"]) >= 200:
                raise ValueError("定时列表已满，请删除旧定时。")
            state["alarms"].append(item)
            return item.copy()
        return self.mutate(add)

    def delete(self, identity):
        def remove(state):
            before = len(state["alarms"])
            state["alarms"] = [a for a in state["alarms"] if a["id"] != identity]
            return len(state["alarms"]) < before
        return self.mutate(remove)

    def queue(self, device, track):
        def update(state):
            state["devices"].setdefault(device, {})["music"] = dict(
                id=uuid4().hex, track=track, status="pending")
        self.mutate(update)

    def reconnect(self, device):
        def update(state):
            target = state["devices"].get(device, {})
            if (target.get("music") or {}).get("status") == "playing":
                identity = target["music"]["id"]
                target["music"] = None
                for item in state["alarms"]:
                    if item["id"] == identity:
                        item["status"] = "interrupted"
        self.mutate(update)

    def stop(self, device):
        def update(state):
            target = state["devices"].setdefault(device, {})
            target["music"] = None
            for item in state["alarms"]:
                if item["device_id"] == device and item["status"] == "playing":
                    item["status"] = "cancelled"
        self.mutate(update)

    def poll(self, device, now=None):
        now = now or datetime.now(timezone.utc)
        def update(state):
            target = state["devices"].setdefault(device, {})
            for item in sorted(state["alarms"], key=lambda a: a["due_at"]):
                due = datetime.fromisoformat(item["due_at"].replace("Z","+00:00"))
                if item["device_id"] != device or item["status"] != "pending" or due > now:
                    continue
                if now - due > timedelta(minutes=10):
                    item["status"] = "expired"
                    continue
                if target.get("music"):
                    break
                item["status"] = "playing"
                target["music"] = dict(id=item["id"], track=item["track"], status="pending")
                if item["wake_light"]:
                    revision = target.get("lamp", {}).get("revision", 0) + 1
                    target["lamp"] = dict(mode="fade", level=100, seconds=30, revision=revision)
                break
            return target.copy()
        return self.mutate(update)

    def claim(self, device, identity):
        def update(state):
            music = state["devices"].get(device, {}).get("music")
            if not music or music["id"] != identity or music["status"] != "pending":
                return None
            music["status"] = "playing"
            return music["track"]
        return self.mutate(update)

    def playing(self, device, identity):
        music = self.snapshot()["devices"].get(device, {}).get("music")
        return bool(music and music["id"] == identity and music["status"] == "playing")

    def finish(self, device, identity):
        def update(state):
            target = state["devices"].get(device, {})
            if (target.get("music") or {}).get("id") != identity:
                return
            target["music"] = None
            for item in state["alarms"]:
                if item["id"] == identity:
                    item["status"] = "delivered"
        self.mutate(update)

    def audio(self, track, alarm_id=None):
        with av.open(str(self.music_root / TRACKS[track][1])) as container:
            resampler = av.AudioResampler(format="s16", layout="mono", rate=24000)
            chunks = []
            for frame in container.decode(audio=0):
                chunks.extend(f.to_ndarray().tobytes() for f in resampler.resample(frame))
            chunks.extend(f.to_ndarray().tobytes() for f in resampler.resample(None))
        data = b"".join(chunks)
        if not 0 < len(data) <= 120 * 48000:
            raise ValueError("音乐长度不支持。")
        if alarm_id and any(item["id"] == alarm_id for item in self.snapshot()["alarms"]):
            target_bytes = 10 * 24000 * 2
            data = (data * ((target_bytes + len(data) - 1) // len(data)))[:target_bytes]
        gain = self.preferences.get().volume
        samples = np.frombuffer(data, dtype="<i2").astype(np.float32) * gain
        data = np.clip(samples, -32768, 32767).astype("<i2").tobytes()
        result = AudioResult(data, 24000, 1, len(data) / 48000, provider="music", peak=1)
        # Keep volume responsive; source files are short enough to decode per request.
        return result

    def voice(self, device, text):
        q = unicodedata.normalize("NFKC", text).strip().strip("。！! ")
        q = re.sub(r"^(?:小星[，, ]*)?(?:请|帮我)?", "", q)
        modes = {"开灯": ("steady", 100), "关灯": ("steady", 0),
                 "渐亮": ("fade", 100), "慢慢开灯": ("fade", 100),
                 "渐灭": ("fade", 0), "慢慢关灯": ("fade", 0),
                 "呼吸灯": ("breath", 100), "打开呼吸灯": ("breath", 100)}
        if q in modes:
            mode, level = modes[q]
            self.lamp(device, dict(mode=mode, level=level))
            return "灯光指令已发送。"
        match = re.fullmatch(r"(?:把)?(?:灯光|灯的)?亮度(?:调到|调成|设为)(?:百分之)?([0-9零一二两三四五六七八九十百]+)%?", q)
        if match:
            level = number(match[1])
            if level is None or not 0 <= level <= 100:
                return "亮度请设为百分之零到百分之一百。"
            self.lamp(device, dict(level=level))
            return f"灯光亮度已设为百分之{level}。"
        if q in ("停止音乐", "关闭音乐", "停止播放"):
            self.stop(device)
            return "音乐已停止。"
        match = re.fullmatch(r"(?:播放|放)(?:一段|一首)?(音乐|晨间铃声|起床旋律|阳光跳跃)", q)
        if match:
            self.queue(device, self.track(match[1]))
            return "好，接下来播放音乐。"
        # An explicit clock time followed by “叫我” sets a music alarm.
        alarm = re.fullmatch(
            r"((?:今天|明天)?(?:凌晨|早上|上午|中午|下午|晚上)?[0-9零一二两三四五六七八九十]+[点时]"
            r"(?:半|[0-9零一二两三四五六七八九十]+分?)?)(?:叫|喊|叫醒)我", q)
        if alarm:
            q = alarm[1] + "播放起床旋律"
        relative_alarm = re.fullmatch(
            r"([0-9零〇一二两三四五六七八九十百千]+)\s*分钟\s*(?:之|以)?后[，, ]*(?:叫醒|叫|喊)我(?:一下)?", q)
        if relative_alarm:
            q = relative_alarm[1] + "分钟后播放起床旋律"
        match = re.fullmatch(
            r"(?:(每天|明天|今天)?(?:凌晨|早上|上午|中午|晚上|下午)?([0-9零一二两三四五六七八九十]+)[点时](半|[0-9零一二两三四五六七八九十]+分?)?|"
            r"([0-9零一二两三四五六七八九十百]+)分钟后)(?:给我|帮我)?(?:放|播放)(音乐|晨间铃声|起床旋律|阳光跳跃)(并开灯)?", q)
        if not match:
            return None
        day, hour, minute, delay, name, light = match.groups()
        if day == "每天":
            return "目前支持单次定时，请说今天或明天几点播放。"
        now = datetime.now(ZoneInfo(self.preferences.get().time_zone))
        if delay:
            value = number(delay)
            if not value or value > 1440:
                return "请设置一到一千四百四十分钟后的时间。"
            due = now + timedelta(minutes=value)
        else:
            h, m = number(hour), (30 if minute == "半" else number((minute or "0").rstrip("分")))
            if h is None or m is None or h > 23 or m > 59:
                return "这个时间不正确，请重新说。"
            if ("下午" in q or "晚上" in q) and h < 12:
                h += 12
            due = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if day == "明天" or (not day and due <= now):
                due += timedelta(days=1)
        try:
            self.create(dict(device_id=device, due_at=due, track=self.track(name), wake_light=bool(light)))
        except ValueError as exc:
            return str(exc)
        return f"已设置{due.month}月{due.day}日{due.hour}点{due.minute}分播放{name}。"

    @staticmethod
    def track(name):
        return next((key for key, (label, _) in TRACKS.items() if label == name), "morning")
