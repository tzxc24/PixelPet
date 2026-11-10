"""Explicit offline test provider, with deterministic history/memory-aware replies."""
import asyncio
import json

from backend.memory.logic import RECALL


class MockProvider:
    mode = "mock"

    async def stream(self, messages):
        user = messages[-1]["content"]
        memories = []
        for message in messages:
            if "\nMEMORY_DATA:" in message["content"]:
                memories = json.loads(message["content"].rsplit("\nMEMORY_DATA:",1)[1])
        facts = "；".join(m["content"] for m in memories)
        history = [m["content"] for m in messages[:-1] if m["role"] == "user"]
        emotion, action = "happy", "jump"
        if RECALL.search(user):
            reply = f"我记得呀：{facts}。一起慢慢把事情做好～" if facts else "我还没有找到相关记忆，可以再告诉我一次吗？"
            emotion, action = "curious", "listen"
        elif "刚才" in user or "上一句" in user:
            reply = f"你刚才说的是：{history[-1]}。我有认真听哦！" if history else "这段对话里我还没听到前一句呢。"
        elif "摸" in user:
            reply = "嘿嘿，被你摸摸就充满星星能量啦！"
            emotion, action = "shy", "idle"
        elif any(word in user for word in ["累", "难过", "伤心"]):
            reply, emotion, action = "辛苦啦，我陪你歇一会儿。要不要说说今天发生了什么？", "sad", "idle"
        elif any(word in user for word in ["困", "晚安"]):
            reply, emotion, action = "那就一起给今天画个小星星，晚安，好梦～", "sleepy", "sleep"
        elif "记住" in user or "我叫" in user:
            reply = "收到啦！可保存的重要信息会进入记忆本，你也可以随时查看和删除。"
        else:
            reply = "收到你的小纸条啦！我在这里陪着你。今天有什么想分享的新鲜事？"
        raw = json.dumps({"reply": reply, "emotion": emotion, "action": action, "memories": []}, ensure_ascii=False)
        for start in range(0, len(raw), 6):
            await asyncio.sleep(.005)
            yield raw[start:start+6]

    async def close(self):
        pass

    async def complete(self, messages):
        return "".join([part async for part in self.stream(messages)])
