"""[트레이스] 탭: 트레이스 on/off (D5), 색, dash, 레전드 텍스트. 소유: WP3.

ctx = SimpleNamespace(fid, settings, traces, parsed, fig_px, domains)
"""

from __future__ import annotations

import re

import streamlit as st

from pd_app import constants, state

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
    """팝업 꺼짐 및 Hex 튕김 버그를 완벽 우회한 대시보드 제어 모달."""
    fid = ctx.fid
    tr = ctx.settings["traces"][tk]
    current_color = tr.get("color", "#000000")

    st.markdown("**1. Origin 24색 팔레트 (8×3 배열)**")
    
    colors = list(constants.ORIGIN_COLORS.items())
    for row in range(0, 24, 8):
        cols = st.columns(8)
        for col_idx in range(8):
            idx = row + col_idx
            if idx < len(colors):
                name, hexv = colors[idx]
                with cols[col_idx]:
                    btn_key = f"pal_btn_{safe}_{idx}"
                    if st.button(" ", key=btn_key, help=name, use_container_width=True):
                        tr["color"] = hexv
                        st.rerun()
                    
                    st.html(
                        f"<style>"
                        f".st-key-{btn_key} button {{"
                        f"  background-color: {hexv} !important; "
                        f"  width: 32px !important; "
                        f"  height: 32px !important; "
                        f"  min-height: 32px !important; "
                        f"  padding: 0 !important; "
                        f"  margin: 0 auto !important; "
                        f"  border: 1px solid #ccc !important; "
                        f"  border-radius: 4px !important; "
                        f"}} "
                        f".st-key-{btn_key} button:hover {{"
                        f"  border: 2px solid #000 !important; transform: scale(1.1);"
                        f"}}"
                        f"</style>"
                    )

    st.markdown("<br>**2. 커스텀 색상 및 투명도 조절**", unsafe_allow_html=True)
    c_preview, c_hex, c_trans = st.columns([1.2, 2, 2], vertical_alignment="bottom")
    
    with c_preview:
        html_picker = f"""
        <div style="display:flex; flex-direction:column; align-items:center; margin-bottom:5px;">
            <span style="font-size:11px; color:#666; margin-bottom:2px; font-weight:bold;">컬러맵</span>
            <input type="color" value="{current_color}" 
                   style="width:38px; height:38px; padding:0; border:1px solid #ccc; border-radius:6px; cursor:pointer;"
                   oninput="
                        var hexInput = window.parent.document.querySelector('.st-key-hex_input_{safe} input');
                        if (hexInput) {{
                            var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                            nativeSetter.call(hexInput, this.value);
                            hexInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        }}
                   ">
        </div>
        """
        st.components.v1.html(html_picker, height=70)
        
    with c_hex:
        temp_color = st.text_input("Hex 코드", value=current_color, key=f"hex_input_{safe}", max_chars=7)
        if temp_color and not temp_color.startswith("#"):
            temp_color = "#" + temp_color.lstrip("#")
            
    with c_trans:
        # 💡 [수정] 투명도 데이터가 없을 때의 기본값을 0에서 40으로 수정했습니다.
        temp_trans = st.number_input(
            "투명도 (%)", min_value=0, max_value=100, 
            value=int(float(tr.get("transparency", 40))), 
            step=5, key=f"trans_{safe}"
        )

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("✅ 설정 적용", type="primary", use_container_width=True, key=f"apply_{safe}"):
        if re.match(r"^#[0-9A-Fa-f]{6}$", temp_color):
            tr["color"] = temp_color
        tr["transparency"] = temp_trans
        st.rerun()


def _color_control(ctx, tk, tr, col):
    """색상 컬럼: 메인 편집 창 리스트에 렌더링되는 정사각형 트리거 위젯."""
    safe = _SAFE.sub("_", tk)
    cur_name = _color_name_of(tr["color"])
    # 💡 [수정] 메인 리스트 스와치 렌더링 시에도 기본 투명도를 40%로 반영합니다.
    trans_pct = int(float(tr.get("transparency", 40)))
    trans_text = f" (투명도 {trans_pct}%)" if trans_pct > 0 else ""
    opacity_val = 1.0 - (trans_pct / 100.0)

    with col:
        st.html(
            f"<style>"
            f".st-key-pd_sw_{safe} button {{"
            f"  background: {tr['color']} !important; "
            f"  opacity: {opacity_val} !important; "
            f"  width: 32px !important; "
            f"  height: 32px !important; "
            f"  min-width: 32px !important; "
            f"  min-height: 32px !important; "
            f"  padding: 0 !important; "
            f"  border: 1px solid #aaa !important; "
            f"  border-radius: 6px !important; "
            f"  display: block !important; "
            f"  margin: 0 auto !important; "
            f"}} "
            f".st-key-pd_sw_{safe} button:hover {{ filter: brightness(0.8); border-color:#000 !important; }}"
            f"</style>"
        )
        with st.container(key=f"pd_sw_{safe}"):
            btn_key = state.wkey("trace", f"{tk}.color_btn", fid=ctx.fid)
            if st.button(" ", key=btn_key, use_container_width=False, help=f"색상: {cur_name}{trans_text} — 클릭해서 변경"):
                _color_dialog(ctx, tk, safe)


def _range_i_by_tk(ctx) -> dict:
    """parsed 트레이스의 range_i 를 settings 트레이스 키(tk)에 매핑."""
    out, seen = {}, {}
    for t in ctx.parsed["traces"]:
        seen[t["label"]] = seen.get(t["label"], 0) + 1
        out[state.tkey_of(t, seen[t["label"]])] = t.get("range_i")
    return out


def _render_row(ctx, tk, tr, ri_suffix=""):
    fid = ctx.fid
    c_on, c_color, c_dash = st.columns(3, vertical_alignment="center")

    tr["visible"] = c_on.checkbox(
        tr["label"] + ri_suffix, value=bool(tr["visible"]),
        key=state.wkey("trace", f"{tk}.visible", fid=fid),
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


def render(ctx) -> None:
    traces = ctx.traces
    if not traces:
        st.caption("표시할 트레이스가 없습니다.")
        return

    h_on, h_color, h_dash = st.columns(3)
    h_on.caption(
        "표시",
        help="측정에 사용된 Range I(전류 레인지)가 트레이스마다 다를 경우에만, "
             "구분용으로 각 트레이스 이름 옆에 그 값이 표시됩니다. "
             "모두 같으면 표시되지 않습니다. (그래프·인셋에는 영향 없음)",
    )
    h_color.caption("색상")
    h_dash.caption("선 종류")

    # Range I 가 서로 다를 때만 구분용으로 라벨에 표기 (인셋/레전드에는 영향 없음)
    ri_map = _range_i_by_tk(ctx)
    show_ri = len({v for v in ri_map.values() if v}) > 1

    for tk, tr in traces.items():
        ri_suffix = f"  ·  {ri_map.get(tk) or 'N/A'}" if show_ri else ""
        _render_row(ctx, tk, tr, ri_suffix)

    n_on = sum(1 for t in traces.values() if t["visible"])
    st.caption(f"{n_on} / {len(traces)} 개 표시 중")