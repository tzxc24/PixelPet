"""Conservative plain-text preparation and bounded provider prosody hints."""
import re
import unicodedata


def prepare_text(text: str, max_chars: int = 2000) -> str:
    """Remove visual markup; retain complete clauses within the speech budget."""
    if not isinstance(text, str) or isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 2:
        raise ValueError('Invalid speech text or character limit')
    text = re.sub(r'(?ms)^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1[^\n]*(?:\n|$)', '代码内容请查看屏幕。\n', text)
    text = re.sub(r'!\[[^\]]*\]\([^\n]*?\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\n]*?\)', r'\1', text)
    text = re.sub(r'https?://[^\s<>，。！？；：、]+', '', text)
    text = re.sub(r'(?m)^(\s{0,3}#{1,6}\s+.*?)\s+#+\s*$', r'\1', text)
    text = re.sub(r'(?m)^\s{0,3}(?:#{1,6}\s+|>\s*|[-+*]\s+|\d+[.)]\s+)', '', text)
    text = re.sub(r'(?m)^\s*(?:[-*_]\s*){3,}$', '', text)
    text = re.sub(r'(\*\*|__|~~|`)', '', text)
    text = re.sub(r'(?<!\w)[*_](?=\S)|(?<=\S)[*_](?!\w)', '', text)
    # Emoji blocks and presentation selectors; retain units, maths, and minus signs.
    text = ''.join(c for c in text if not (0x1F000 <= ord(c) <= 0x1FAFF or 0x2600 <= ord(c) <= 0x27BF or ord(c) in {0x200D, 0xFE0F}) and unicodedata.category(c) not in {'Cc', 'Cf'} or c in '\n\t')
    lines = []
    for line in text.splitlines():
        line = re.sub(r'\s+', ' ', line).strip()
        if not line:
            continue
        if line[-1] not in '。！？!?；;：:，,.…':
            line += '。'
        lines.append(line)
    text = ''.join(lines).strip()
    if not any(c.isalnum() for c in text):
        raise ValueError('No speakable text')
    if len(text) > max_chars:
        prefix = text[:max_chars]
        boundaries = list(re.finditer(r'[。！？!?；;](?:[”’\"\']|$)?|(?<!\d)\.(?!\d)', prefix))
        if boundaries:
            text = prefix[:boundaries[-1].end()]
        else:
            clauses = list(re.finditer(r'[，,:：]|\s+', prefix[:-1]))
            if not clauses:
                raise ValueError('Speech text exceeds limit without a safe boundary')
            text = prefix[:clauses[-1].start()].rstrip() + '。'
    if not any(c.isalnum() for c in text):
        raise ValueError('No speakable text within limit')
    return text


def emotion_parameters(emotion: str, rate_percent: int = 0, pitch_hz: int = 0, volume_percent: int = 0) -> dict:
    """Mild prosody only, without claiming provider emotion/SSML support."""
    shifts = {'normal': 0, 'happy': 4, 'shy': -3, 'sad': -5, 'curious': 1, 'sleepy': -7, 'surprised': 5, 'angry': 0, 'thinking': 0}
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (rate_percent, pitch_hz, volume_percent)):
        raise ValueError('Prosody values must be integers')
    return {'rate_percent': max(-20, min(20, rate_percent + shifts.get(emotion, 0))), 'pitch_hz': max(-12, min(12, pitch_hz)), 'volume_percent': max(-100, min(0, volume_percent))}
