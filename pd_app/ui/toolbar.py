"""PLAN §8.4 리치 입력 툴바 (G4). 소유: WP6.

`rich_input(label, value, key)` 는 마크업 필드 공용 입력 위젯이다: 서식 툴바가 달린
입력칸(`components.rich_toolbar`) + 그 아래 렌더 미리보기 칩. 각 패널(축 제목·인셋
텍스트·샘플명 등)이 `st.text_input` 대신 이걸 호출한다.

선택 영역을 마크업으로 감싼다(DOM→마크업 직렬화기 없음 = 검증된 apply_markup 무오염):
    선택 → B ⇒ **선택** · I ⇒ *선택* · x² ⇒ ^{선택} · x₂ ⇒ _{선택} · A ⇒ {#RRGGBB|선택}
편차(PLAN §8.4): 입력칸은 렌더된 텍스트가 아니라 마크업 소스를 보여준다. 그래서 옆에
apply_markup 미리보기 칩을 붙여 결과를 즉시 보인다.

`render(ctx)` 는 편집 패널 상단의 조용한 마크업 힌트 스트립(발견성)이다.
"""

from __future__ import annotations

import streamlit as st

from components.rich_toolbar import rich_toolbar
from pd_app import constants
from pd_app.markup import apply_markup


def rich_input(label: str, value: str, key: str, placeholder: str = "") -> str:
    """마크업 필드 공용 위젯: 서식 툴바 입력 + 렌더 미리보기 칩."""
    raw = rich_toolbar(value=value or "", key=key, label=label, placeholder=placeholder)
    preview = apply_markup(raw) or "&nbsp;"
    st.html(
        "<div style='margin-top:2px;padding:3px 9px;border-radius:7px;"
        "background:rgba(0,0,0,0.035);font-size:13px;color:#333;"
        f"min-height:20px;line-height:1.5'>{preview}</div>"
    )
    return raw

def render(ctx) -> None:
    """편집 패널 최상단에 고정 표시되는 마크업 문법 요약 안내 가이드."""
    st.info(
        "💡 **마크업 퀵 서식**: 위첨자 `^{x}` · 아래첨자 `_{x}` · "
        "굵게 `**x**` · 기울임 `*x*` · 색상 `{#Hex코드|x}`",
        icon="ℹ️"
    )