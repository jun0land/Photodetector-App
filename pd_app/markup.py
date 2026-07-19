"""인라인 마크업 파서 (원본 app.py 510-574 축자 이동, 로직 변경 금지).

문법: **굵게** / *기울임* / ^{위첨자} / _{아래첨자} / {#RRGGBB|색} / \\ 이스케이프
"""

import re

_COLOR_OPEN = re.compile(r"\{(#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3}))\|")


def _esc_html(text):
    """마크업 확장 전에 원문의 &, <, > 를 이스케이프 (Plotly HTML 깨짐 방지)."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _wrap(open_tag, close_tag, inner):
    return f"{open_tag}{inner}{close_tag}" if inner else ""


def _parse_seq(s, i, stop=None):
    """stop 문자열을 만나거나 끝날 때까지 토큰을 이어붙인다."""
    out = []
    while i < len(s):
        if stop and s.startswith(stop, i):
            break
        frag, i = _parse_token(s, i)
        out.append(frag)
    return "".join(out), i


def _parse_token(s, i):
    c = s[i]
    if c == "\\" and i + 1 < len(s):  # 이스케이프: 다음 글자를 그대로
        return s[i + 1], i + 2
    if s.startswith("**", i):
        inner, j = _parse_seq(s, i + 2, "**")
        if s.startswith("**", j):
            return _wrap("<b>", "</b>", inner), j + 2
        return "**", i + 2  # 짝 없음 -> 리터럴
    if c == "*":
        inner, j = _parse_seq(s, i + 1, "*")
        if j < len(s) and s[j] == "*":
            return _wrap("<i>", "</i>", inner), j + 1
        return "*", i + 1
    if c in "^_":
        # 반드시 중괄호가 뒤따라야 위/아래첨자. 그 외에는 리터럴 문자.
        if i + 1 < len(s) and s[i + 1] == "{":
            inner, j = _parse_seq(s, i + 2, "}")
            if j < len(s) and s[j] == "}":
                tag = "sup" if c == "^" else "sub"
                return _wrap(f"<{tag}>", f"</{tag}>", inner), j + 1
        return c, i + 1
    if c == "{":
        m = _COLOR_OPEN.match(s, i)
        if m:  # {#RRGGBB|...} 형태만 색 span, 나머지 중괄호는 리터럴
            inner, j = _parse_seq(s, m.end(), "}")
            if j < len(s) and s[j] == "}":
                return _wrap(f'<span style="color:{m.group(1)}">', "</span>", inner), j + 1
        return "{", i + 1
    return c, i + 1


def apply_markup(text):
    """사용자 인라인 마크업 -> Plotly 가 인식하는 HTML."""
    if not text:
        return ""
    html, _ = _parse_seq(_esc_html(text), 0)
    return html
