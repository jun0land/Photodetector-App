"""리치 입력 툴바 컴포넌트 (G4 / PLAN §8.4). 소유: WP6.

`<input>` 을 v2 컴포넌트로 감싸고, 툴바 버튼이 selectionStart/End 로 선택 영역을
마크업으로 감싼다 (DOM→마크업 직렬화기 없음 = 검증된 apply_markup 파서 무오염).
로직은 `toolbar.js` (export function wrapSelection + export default (component)) 에 있다.

v2 규약 (streamlit 1.59):
    renderer = st.components.v2.component(name, css=, js=)
    result = renderer(key=, data=, default=, on_value_change=, height=) -> ComponentResult
- `setStateValue("value", x)` 로 방출한 값을 파이썬에서 받으려면 default={"value":...} 와
  on_value_change 콜백이 **둘 다** 있어야 한다 (default 키는 콜백이 있는 state 만 유효).
- ComponentResult 는 AttributeDictionary → `result.get("value", ...)`.

v2 를 못 쓰는 환경(streamlit 다운그레이드 등)에서는 st.text_input 으로 우아하게 폴백한다.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

_DIR = Path(__file__).parent
_JS = (_DIR / "toolbar.js").read_text(encoding="utf-8")

# 툴바/입력칸/스와치 스타일. toolbar.js 는 클래스만 만들고 실제 스타일은 여기(component css)다.
_CSS = """
.pd-rt { display: flex; flex-direction: column; gap: 5px; font-family: inherit; }
.pd-rt-bar { display: flex; align-items: center; gap: 3px; }
.pd-rt-btn {
    min-width: 27px; height: 27px; padding: 0 6px;
    border: 1px solid #cfcfcf; border-radius: 7px; background: #fff;
    cursor: pointer; font-size: 13px; line-height: 1; color: #1c1c1e;
}
.pd-rt-btn:hover { border-color: #ed542b; color: #ed542b; }
.pd-rt-b { font-weight: 800; }
.pd-rt-i { font-style: italic; }
.pd-rt-a { font-weight: 700; }
.pd-rt-sep { display: inline-block; width: 1px; height: 18px; background: #ddd; margin: 0 4px; }
.pd-rt-swatch {
    width: 27px; height: 27px; padding: 0; border: 1px solid #cfcfcf;
    border-radius: 7px; background: none; cursor: pointer;
}
.pd-rt-input {
    width: 100%; box-sizing: border-box; padding: 7px 9px;
    border: 1px solid #cfcfcf; border-radius: 9px; font-size: 14px; color: #1c1c1e;
    background: rgba(255,255,255,0.85);
}
.pd-rt-input:focus { outline: none; border-color: #ed542b; }
"""

# component() 는 앱 실행마다 한 번만 등록하면 된다 (모듈 로드 시 캐시).
_renderer = None


def _get_renderer():
    global _renderer
    if _renderer is None:
        _renderer = st.components.v2.component("pd_rich_toolbar", css=_CSS, js=_JS)
    return _renderer


def _noop() -> None:
    """on_value_change 콜백. 값은 rerun 후 ComponentResult 로 읽으므로 여기선 할 일이 없다."""


def rich_toolbar(*, value: str, key: str, label: str = "",
                 placeholder: str = "", color: str = "#FF0000") -> str:
    """마크업 소스 입력칸 + 서식 툴바. 커밋된(Enter/포커스아웃/버튼) 마크업 문자열 반환.

    v2 컴포넌트를 못 쓰면 st.text_input 으로 폴백한다 (앱은 절대 깨지지 않는다).
    """
    safe = str(value) if value is not None else ""
    try:
        result = _get_renderer()(
            key=key,
            data={"value": safe, "label": label, "placeholder": placeholder, "color": color},
            default={"value": safe},
            on_value_change=_noop,
            height="content",
        )
        out = result.get("value", safe)
        return safe if out is None else str(out)
    except Exception:  # noqa: BLE001 — v2 불가 시 폴백. 앱은 계속 산다.
        return st.text_input(label or "텍스트", value=safe, key=f"{key}__fb",
                             placeholder=placeholder, label_visibility="collapsed")
