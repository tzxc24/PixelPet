"""Strict device control phrases, independent of the language model."""
import unicodedata
import re


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', str(text))
                   if not c.isspace() and not unicodedata.category(c).startswith('P'))


def is_rest_command(text):
    phrase = normalize(text)
    phrases = {
        prefix + command for prefix in ('', '小星', '小心', '小新', '小辛', '小型')
        for command in ('休息吧', '你休息吧', '先休息吧', '你先休息吧', '进入待机', '停止聊天')
    }
    # An addressed imperative at the start remains a command when ASR merges
    # the following sentence into the same recording. Quoted discussions do not.
    first=normalize(re.split(r'[，,。！!？?；;\n]',str(text),maxsplit=1)[0])
    return phrase in phrases or first in phrases


def is_wake_command(text):
    return normalize(text) in {'你好小星', '你好小心', '你好小新', '你好小辛', '小星小星'}


def assistant_rest_commitment(text):
    if re.search(r'[?？]|(?:可以|要不要|行不行|能不能).{0,3}[吗么呢]',str(text)):
        return False
    phrase=normalize(text)
    return bool(re.match(r'^(?:好(?:的|呀|啊|啦)?|嗯)?(?:那|现在)?我(?:先|乖乖|这就|去|就|要|准备)?(?:休息|睡一)',phrase))
