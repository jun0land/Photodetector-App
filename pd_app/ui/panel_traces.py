"""[트레이스] 탭: 트레이스 on/off (D5), 색, dash, 레전드 텍스트. 소유: WP3.

ctx = SimpleNamespace(fid, settings, traces, parsed, fig_px, domains)
"""

from __future__ import annotations

import re

import streamlit as st

from pd_app import constants, state
from pd_app.ui.toolbar import rich_input

_SAFE = re.compile(r"\W+")

_CUSTOM = "Custom"
_COLOR_NAMES = list(constants.ORIGIN_COLORS.keys())
_COLOR_OPTIONS = _COLOR_NAMES + [_CUSTOM]
_DASH_LABELS = list(constants.DASH_OPTIONS.keys())
_DASH_BY_VALUE = {v: k for k, v in constants.DASH_OPTIONS.items()}


def _color_name_of(hex_color):
    h = str(hex_color).upper()
    return next((k for k, v in constants.ORIGIN_COLORS.items() if v.upper() == h), _CUSTOM)


@st.dialog("🎨 색상 및 투명도 설정")
def _color_dialog(ctx, tk, safe):
    """팝업 꺼짐 버그를 해결한 모달 다이얼로그. 6x4 정방형 스와치 복구 및 안전한 헥스 입력."""
    fid = ctx.fid
    tr = ctx.settings["traces"][tk]
    current_color = tr.get("color", "#000000")

    st.markdown("**1. Origin 24색 팔레트 (빠른 적용)**")
    
    # 💡 [수정1] 6x4 배열의 30x30 정사각형 스와치를 HTML/CSS + st.button으로 완벽 복원
    cols = st.columns(6, gap="small")
    for i, (name, hexv) in enumerate(constants.ORIGIN_COLORS.items()):
        with cols[i % 6]:
            # 버튼 텍스트를 공백으로 두고 고유 key 할당
            if st.button(" ", key=f"pal_{safe}_{name}", help=name):
                tr["color"] = hexv
                st.rerun()
            # CSS로 버튼 크기를 강제 30x30px 정사각형으로 고정하고 마진을 없앰
            st.html(
                f"<style>"
                f".st-key-pal_{safe}_{name} button {{"
                f"  background-color: {hexv} !important; "
                f"  width: 30px !important; "
                f"  height: 30px !important; "
                f"  min-height: 30px !important; "
                f"  padding: 0 !important; "
                f"  border: 1px solid #d0d0d0 !important; "
                f"  border-radius: 4px !important; "
                f"}} "
                f".st-key-pal_{safe}_{name} button:hover {{ border: 2px solid #000 !important; }}"
                f"</style>"
            )

    st.markdown("<br>**2. 커스텀 색상 및 투명도 조절**", unsafe_allow_html=True)
    c_preview, c_hex, c_trans = st.columns([1, 2, 2], vertical_alignment="bottom")
    
    # 💡 [수정2] 네이티브 컬러 피커 튕김 버그를 우회하는 텍스트 기반 헥스(Hex) 편집기
    with c_preview:
        # 현재 입력된 Hex 색상을 실시간으로 보여주는 미리보기 박스
        st.html(
            f"<div style='width: 40px; height: 40px; background-color: {current_color}; "
            f"border: 1px solid #ccc; border-radius: 6px; margin-bottom: 5px; "
            f"box-shadow: inset 0 0 4px rgba(0,0,0,0.2);'></div>"
        )
        
    with c_hex:
        # 컬러 피커 대신 Hex 코드를 직접 입력 (예: #FF5733). 
        temp_color = st.text_input("Hex 코드 입력", value=current_color, key=f"hex_{safe}", max_chars=7)
        # 잘못된 입력 방어 (항상 #으로 시작하도록)
        if not temp_color.startswith("#"):
            temp_color = "#" + temp_color.lstrip("#")
            
    with c_trans:
        temp_trans = st.number_input(
            "투명도 (%)", min_value=0, max_value=100, 
            value=int(float(tr.get("transparency", 0))), 
            step=5, key=f"trans_{safe}", help="0: 완전 불투명, 100: 완전 투명"
        )

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("✅ 설정 적용", type="primary", use_container_width=True, key=f"apply_{safe}"):
        tr["color"] = temp_color
        tr["transparency"] = temp_trans
        st.rerun()

def _color_control(ctx, tk, tr, col):
    """색상 컬럼: 현재 색/투명도를 반영한 버튼(다이얼로그 트리거)."""
    safe = _SAFE.sub("_", tk)
    cur_name = _color_name_of(tr["color"])
    trans_pct = int(float(tr.get("transparency", 0)))
    trans_text = f" (투명도 {trans_pct}%)" if trans_pct > 0 else ""
    opacity_val = 1.0 - (trans_pct / 100.0)

    with col:
        # 버튼에 선택된 색상과 투명도(opacity)를 주입하여 직관적으로 보이게 합니다.
        st.html(
            f"<style>.st-key-pd_sw_{safe} button "
            f"{{background:{tr['color']} !important; opacity: {opacity_val}; min-height: 30px; border: 1px solid #ccc; border-radius: 4px;}} "
            f".st-key-pd_sw_{safe} button:hover {{filter: brightness(0.8);}}</style>"
        )
        with st.container(key=f"pd_sw_{safe}"):
            # 💡 [핵심 수정] 똑같은 색상이 여러 개 있어도 에러가 나지 않도록 고유 key(btn_key)를 추가합니다!
            btn_key = state.wkey("trace", f"{tk}.color_btn", fid=ctx.fid)
            if st.button(" ", key=btn_key, use_container_width=True, help=f"색상: {cur_name}{trans_text} — 클릭해서 변경"):
                _color_dialog(ctx, tk, safe)


def _render_row(ctx, tk, tr):
    fid = ctx.fid
    c_on, c_color, c_dash, c_text = st.columns(
        [1.6, 0.7, 1.1, 1.2], vertical_alignment="center")

    tr["visible"] = c_on.checkbox(
        tr["label"], value=bool(tr["visible"]),
        key=state.wkey("trace", f"{tk}.visible", fid=fid),
        help="그래프에 이 트레이스를 표시합니다.",
    )

    _color_control(ctx, tk, tr, c_color)

    dash_label = _DASH_BY_VALUE.get(tr["dash"], _DASH_LABELS[0])
    tr["dash"] = constants.DASH_OPTIONS[
        c_dash.selectbox(
            "선 종류", _DASH_LABELS, index=_DASH_LABELS.index(dash_label),
            key=state.wkey("trace", f"{tk}.dash", fid=fid),
            label_visibility="collapsed",
        )
    ]

    with c_text.popover("텍스트", use_container_width=True):
        tr["legend_raw"] = rich_input(
            "레전드 텍스트", tr.get("legend_raw", ""),
            key=state.wkey("trace", f"{tk}.legend_raw", fid=fid)
        )


def render(ctx) -> None:
    traces = ctx.traces
    if not traces:
        st.caption("표시할 트레이스가 없습니다.")
        return

    h_on, h_color, h_dash, h_text = st.columns([1.6, 0.7, 1.1, 1.2])
    h_on.caption("표시")
    h_color.caption("색상")
    h_dash.caption("선 종류")
    h_text.caption("텍스트")

    for tk, tr in traces.items():
        _render_row(ctx, tk, tr)

    n_on = sum(1 for t in traces.values() if t["visible"])
    st.caption(f"{n_on} / {len(traces)} 개 표시 중")