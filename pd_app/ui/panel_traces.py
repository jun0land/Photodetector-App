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
    """팝업 꺼짐 버그를 해결한 모달 다이얼로그. 6x4 정방형 스와치 복구 및 JS 네이티브 컬러 맵."""
    fid = ctx.fid
    tr = ctx.settings["traces"][tk]
    current_color = tr.get("color", "#000000")

    st.markdown("**1. Origin 24색 팔레트 (빠른 적용)**")
    
    # 💡 [수정 1] 팔레트 누락 방지: HTML Grid 컨테이너를 먼저 깔고, 그 안에 버튼들을 렌더링합니다.
    st.html(
        """
        <style>
        .pd-palette-grid {
            display: grid;
            grid-template-columns: repeat(6, 40px);
            gap: 8px;
            margin-bottom: 20px;
        }
        .pd-palette-btn button {
            width: 40px !important;
            height: 40px !important;
            min-height: 40px !important;
            padding: 0 !important;
            border: 1px solid #d0d0d0 !important;
            border-radius: 4px !important;
            transition: transform 0.1s;
        }
        .pd-palette-btn button:hover {
            transform: scale(1.1);
            border: 2px solid #000 !important;
            z-index: 1;
        }
        </style>
        """
    )
    
    with st.container():
        # HTML 그리드 느낌을 주기 위해 Streamlit 컬럼 배열을 보다 견고하게 짭니다.
        cols = st.columns(6)
        for i, (name, hexv) in enumerate(constants.ORIGIN_COLORS.items()):
            with cols[i % 6]:
                btn_key = f"pal_{safe}_{i}"
                if st.button(" ", key=btn_key, help=name, use_container_width=True):
                    tr["color"] = hexv
                    st.rerun()
                st.html(f"<style>.st-key-{btn_key} {{ class: pd-palette-btn; }} .st-key-{btn_key} button {{ background-color: {hexv} !important; }}</style>")


    st.markdown("**2. 커스텀 색상 및 투명도 조절**", unsafe_allow_html=True)
    c_preview, c_hex, c_trans = st.columns([1, 2, 2], vertical_alignment="bottom")
    
    # 💡 [수정 2] HTML5 네이티브 컬러 피커 주입 (JS로 Hex Input과 연동)
    with c_preview:
        html_picker = f"""
        <div style="display:flex; flex-direction:column; align-items:center; gap: 4px;">
            <label for="color_picker_{safe}" style="font-size:0.8rem; color:#555;">컬러맵</label>
            <input type="color" id="color_picker_{safe}" value="{current_color}" 
                   style="width:45px; height:45px; padding:0; border:none; border-radius:6px; cursor:pointer;"
                   oninput="
                        // 사용자가 색을 고를 때마다 부모 창(Streamlit)의 특정 Input 창으로 값을 넘깁니다.
                        var hexInput = window.parent.document.querySelector('.st-key-hex_{safe} input');
                        if (hexInput) {{
                            hexInput.value = this.value;
                            var event = new Event('input', {{ bubbles: true }});
                            hexInput.dispatchEvent(event);
                        }}
                   ">
        </div>
        """
        st.components.v1.html(html_picker, height=70)
        
    with c_hex:
        # 네이티브 컬러 피커에서 값을 쏴주거나 직접 입력할 수 있는 텍스트 박스
        temp_color = st.text_input("Hex 코드", value=current_color, key=f"hex_{safe}", max_chars=7)
        if not temp_color.startswith("#"):
            temp_color = "#" + temp_color.lstrip("#")
            
    with c_trans:
        temp_trans = st.number_input(
            "투명도 (%)", min_value=0, max_value=100, 
            value=int(float(tr.get("transparency", 0))), 
            step=5, key=f"trans_{safe}"
        )

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("✅ 설정 적용", type="primary", use_container_width=True, key=f"apply_{safe}"):
        tr["color"] = temp_color
        tr["transparency"] = temp_trans
        st.rerun()


def _color_control(ctx, tk, tr, col):
    """색상 컬럼: 현재 색/투명도를 반영한 30x30 고정 버튼."""
    safe = _SAFE.sub("_", tk)
    cur_name = _color_name_of(tr["color"])
    trans_pct = int(float(tr.get("transparency", 0)))
    trans_text = f" (투명도 {trans_pct}%)" if trans_pct > 0 else ""
    opacity_val = 1.0 - (trans_pct / 100.0)

    with col:
        # 💡 [수정 3] 트레이스 패널의 기본 버튼 너비/높이를 30px로 단단히 고정하여 일그러짐 방지
        st.html(
            f"<style>"
            f".st-key-pd_sw_{safe} button {{"
            f"  background: {tr['color']} !important; "
            f"  opacity: {opacity_val}; "
            f"  width: 35px !important; "
            f"  height: 35px !important; "
            f"  min-height: 35px !important; "
            f"  padding: 0 !important; "
            f"  border: 1px solid #aaa !important; "
            f"  border-radius: 6px !important; "
            f"  margin: auto !important; "
            f"}} "
            f".st-key-pd_sw_{safe} button:hover {{filter: brightness(0.8); border-color:#000 !important;}}"
            f"</style>"
        )
        with st.container(key=f"pd_sw_{safe}"):
            btn_key = state.wkey("trace", f"{tk}.color_btn", fid=ctx.fid)
            # use_container_width=False 로 변경하여 CSS width 강제 할당이 먹히도록 합니다.
            if st.button(" ", key=btn_key, use_container_width=False, help=f"색상: {cur_name}{trans_text} — 클릭해서 변경"):
                _color_dialog(ctx, tk, safe)


def _render_row(ctx, tk, tr):
    fid = ctx.fid
    # 색상 버튼 공간(c_color)을 조금 줄이고 여백을 재조정
    c_on, c_color, c_dash, c_text = st.columns(
        [1.7, 0.5, 1.1, 1.2], vertical_alignment="center")

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

    h_on, h_color, h_dash, h_text = st.columns([1.7, 0.5, 1.1, 1.2])
    h_on.caption("표시")
    h_color.caption("색상")
    h_dash.caption("선 종류")
    h_text.caption("텍스트")

    for tk, tr in traces.items():
        _render_row(ctx, tk, tr)

    n_on = sum(1 for t in traces.values() if t["visible"])
    st.caption(f"{n_on} / {len(traces)} 개 표시 중")