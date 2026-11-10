"""Bounded, transparent lexical rules; no embedding service or sensitive-value retention."""
import hashlib
import re
from datetime import datetime,timezone
from difflib import SequenceMatcher

SENSITIVE = re.compile(r"密[码碼]|口令|密[钥鑰]|[验驗][证證][码碼]|[银銀]行卡|信用卡|支付|身份[证證]|私[钥鑰]|password|passwd|secret|api[ _-]?key|token|cvv|\bsk-[a-z0-9_-]+|\b\d{13,19}\b", re.I)
DENIAL = re.compile(r"(?:不要|[别別]).{0,6}[记記]|不想.{0,8}[记記]|不需要.{0,8}[记記]|忘掉|忘[记記]|[删刪]除.{0,8}(?:记忆|記憶)")
HYPOTHETICAL = re.compile(r"假如|如果|比如|例如|假[设設]")
RECALL = re.compile(r"[记記]得|[记記]住了什[么麼]|记忆|記憶|做什[么麼]|名字|喜[欢歡]什[么麼]")
REMEMBER = r"[请請]?[记記]住|[记記]下[来來]|[记記]一下"
QUESTION = re.compile(r"[吗嗎]|什[么麼]|怎[么麼]|是不是")
PREFERENCE = r"不?喜[欢歡]|偏[爱愛]|[习習][惯慣]|[爱愛]好"


def safe_memory(content):
    return not bool(SENSITIVE.search(content))


def normalized(text):
    return re.sub(r"[\W_]+", "", text.lower())


def tokens(text):
    text = text.lower()
    result = set(re.findall(r"[a-z0-9]{2,}", text))
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        result.update(run[i:i+2] for i in range(len(run)-1))
    return result


def fact_key(category, content):
    if category == "basic" and re.search(r"(?:我叫|主人叫|名字是)", content):
        return "name"
    if category in ("preference","interest"):
        preference=re.search(rf"(?:我|主人)(?:更)?(?:{PREFERENCE}|不[爱愛]|[讨討][厌厭])(?:喝|吃|玩|用|[听聽]|看)?(.+)",content)
        if preference:
            return "preference:"+hashlib.sha256(normalized(preference.group(1)).encode()).hexdigest()[:24]
    return hashlib.sha256(normalized(content).encode()).hexdigest()[:40]


def similar(left, right):
    # Negation changes meaning: never fuzzy-merge across it.
    if bool(re.search(r"不|讨厌|别", left)) != bool(re.search(r"不|讨厌|别", right)):
        return False
    return SequenceMatcher(None, normalized(left), normalized(right)).ratio() >= .82


def extract(text):
    if not safe_memory(text) or DENIAL.search(text) or HYPOTHETICAL.search(text):
        return []
    explicit = bool(re.search(REMEMBER, text))
    facts = []
    for clause in re.split(r"[。；;\n]", text):
        clause = re.sub(rf"^(?:{REMEMBER})[，,:：\s]*", "", clause.strip()).strip(" ，！!？?")
        if not clause or len(clause) < 3:
            continue
        # Questions and hypothetical statements are not autobiographical facts.
        if QUESTION.search(clause):
            continue
        name = re.search(r"(?:我叫|我的名字是)\s*([^\s，,！!？?。]{1,20})", clause)
        if name:
            facts.append({"category":"basic", "content":"主人叫"+name.group(1), "importance":.98 if explicit else .9})
        elif re.search(r"我.*(?:做|[开開][发發]|研究).*(?:[项項]目|桌[宠寵]|ESP32|系[统統]|[应應]用)|我的[项項]目", clause, re.I):
            facts.append({"category":"project", "content":clause, "importance":.98 if explicit else .9})
        elif re.search(rf"我.*(?:{PREFERENCE})", clause):
            facts.append({"category":"preference", "content":clause, "importance":.98 if explicit else .8})
        elif re.search(r"我.*(?:工作|任[职職]|上班|[读讀]研|[读讀]博|就[读讀]|[学學][习習]|[专專][业業]是)", clause):
            facts.append({"category":"work", "content":clause, "importance":.98 if explicit else .8})
        elif re.search(r"我的.*(?:生日|[纪紀]念日)|我.*(?:[毕畢][业業][于於]|出生[于於])",clause):
            facts.append({"category":"event", "content":clause, "importance":.98 if explicit else .85})
        elif explicit:
            facts.append({"category":"explicit", "content":clause, "importance":.98})
    return facts[:8]


def grounded(content, user_text):
    """Reject model memory suggestions unsupported by the current user's statement."""
    if not safe_memory(content) or not safe_memory(user_text):
        return False
    if DENIAL.search(user_text) or HYPOTHETICAL.search(user_text):
        return False
    if not re.search(rf"我|{REMEMBER}", user_text):
        return False
    if QUESTION.search(user_text) and not re.search(r"[记記]住", user_text):
        return False
    left=tokens(content)
    negative=bool(re.search(r"不|没|讨厌|别",content))
    for clause in re.split(r"[，,。；;\n]|但是|不过|但",user_text):
        if negative != bool(re.search(r"不|没|讨厌|别",clause)):
            continue
        right=tokens(clause)
        if left and len(left & right)/len(left)>=.65:
            return True
    return False


def rank(memories, query, limit=8, decay_days=90):
    def importance(memory):
        value=memory['importance']
        if decay_days:
            try:
                date=datetime.fromisoformat(memory['updated_at'].replace('Z','+00:00'))
                if date.tzinfo is None:date=date.replace(tzinfo=timezone.utc)
                age=max(0,(datetime.now(timezone.utc)-date).total_seconds()/86400)
                value/=1+age/decay_days
            except ValueError:pass
        return value
    if not query.strip():
        return sorted(memories, key=lambda m:(importance(m),m["updated_at"]), reverse=True)[:limit]
    query_tokens = tokens(query)
    recall = bool(RECALL.search(query))
    project = bool(re.search(r"项目|項目|做什[么麼]|开发|開發|在做", query))
    preference = bool(re.search(r"喜[欢歡]什[么麼]", query))
    scored=[]
    for memory in memories:
        overlap = len(query_tokens & tokens(memory["content"]))
        bonus = 4 if project and memory["category"]=="project" else 0
        if preference and memory['category'] in ('preference', 'interest'):
            bonus += 4
        if "名字" in query and memory["memory_key"]=="name":
            bonus += 6
        if overlap or recall or bonus:
            scored.append((overlap+bonus+importance(memory),memory["updated_at"],memory))
    return [item[2] for item in sorted(scored,key=lambda item:(item[0],item[1]),reverse=True)[:limit]]
