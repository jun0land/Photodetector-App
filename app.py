"""Photodetector I-V Studio — 진입점.

⚠️ 얇게 유지할 것. 여기엔 로직이 없다. 부팅과 위임만 한다.
원본 app.py(1184줄)는 `pd_app/_legacy_reference.py.txt` 에 보존되어 있고,
그 내용은 각 WP 가 `pd_app/` 모듈로 옮겼다 (PLAN §1).

WP9 가 최종 배선했다: `state.boot()` 후 `layout.render_app()` 에 위임한다.
"""

from __future__ import annotations

import streamlit as st

# set_page_config 는 반드시 다른 st 호출보다 먼저 (streamlit 규약).
st.set_page_config(page_title="Photodetector I-V Studio", layout="wide")

from pd_app import state  # noqa: E402  — set_page_config 이후여야 함
from pd_app.ui import layout  # noqa: E402


def main() -> None:
    """세션 부팅 후 레이아웃에 위임."""
    state.boot()
    layout.render_app()


if __name__ == "__main__":
    main()
