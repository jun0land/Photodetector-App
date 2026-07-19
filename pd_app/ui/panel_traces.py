"""[트레이스] 탭: 트레이스 on/off (D5), 색, dash, 레전드 텍스트. 소유: WP3.

ctx = SimpleNamespace(fid, settings, traces, parsed, fig_px, domains)
    fid       현재 활성 파일 id
    settings  state.file_settings(fid) — 모델이 유일한 진실
    traces    settings["traces"] (TKey -> dict)
    parsed    parsing.parse_file() 결과
    fig_px    figure.px_size(geom) → (w, h)
    domains   figure.domains(geom) → {"x0","x1","y0","y1"}

패널은 read-render-writeback. 위젯키는 반드시 `state.wkey(group, name, fid=fid)`.
이 모듈은 `render` 외에 아무것도 공개하지 않는다.
"""

from __future__ import annotations

import re

import streamlit as st

from pd_app import constants, state
from pd_app.ui.toolbar import rich_input

# st-key 클래스에 안전한 문자로 tk("940 nm#1")를 정규화. CSS 훅(theme.py)이 이걸 쓴다.
_SAFE = re.compile(r"\W+")

_CUSTOM = "Custom"
_COLOR_NAMES = list(constants.ORIGIN_COLORS.keys())
_COLOR_OPTIONS = _COLOR_NAMES + [_CUSTOM]
_DASH_LABELS = list(constants.DASH_OPTIONS.keys())          # ["Solid", "Dash", ...]
_DASH_BY_VALUE = {v: k for k, v in constants.DASH_OPTIONS.items()}


def _color_name_of(hex_color):
    """hex -> Origin 팔레트 이름. 팔레트에 없으면 'Custom'."""
    h = str(hex_color).upper()
    return next((k for k, v in constants.ORIGIN_COLORS.items() if v.upper() == h), _CUSTOM)


def _palette(ctx, tk, tr, safe):
    """popover 안: OriginLab 24색 그리드 + Custom("C") + (Custom 시)color_picker.

    각 색 칸은 빈 라벨 st.button(`help`=색상명 → hover 툴팁). 위치→색 매핑과 30px 정사각형·
    회색 Custom 칸은 theme.py CSS 가 st-key 훅(`pd_palette_*`)으로 그린다.
    """
    fid = ctx.fid
    with st.container(key=f"pd_palette_{safe}"):
        for name, hexv in constants.ORIGIN_COLORS.items():
            if st.button("", key=state.wkey("trace", f"{tk}.pal.{name}", fid=fid),
                         help=name):
                tr["color"] = hexv
                st.rerun()
    # 1. vertical_alignment="center"를 과감하게 지웁니다. (이게 어긋남의 원인입니다)
    c_pick, c_lbl = st.columns([1, 4])
    with c_pick:
        tr["color"] = st.color_picker(
            "Custom", value=tr["color"],
            key=state.wkey("trace", f"{tk}.color", fid=fid),
            label_visibility="collapsed",
        )
        
    # 2. display: flex 와 height: 30px 를 적용해 박스 크기를 컬러 피커와 똑같이 맞춥니다.
    c_lbl.html(
        "<div style='display: flex; align-items: center; height: 30px; "
        "color: #6b6b70; font-size: 0.88rem; margin-left: -4px;'>"
        "Custom</div>"
    )


def _color_control(ctx, tk, tr, col):
    """색상 컬럼: 현재 색을 채운 30px 스와치(popover 트리거). 클릭하면 팔레트가 열린다.

    트리거 배경(=현재 색)은 동적이라 per-trace <style> 로 주입하고, 크기/모양은
    theme.py 의 정적 CSS(`pd_sw_*`)가 준다.
    """
    safe = _SAFE.sub("_", tk)
    cur_name = _color_name_of(tr["color"])
    with col:
        st.html(
            f"<style>.st-key-pd_sw_{safe} [data-testid='stPopover'] button"
            f"{{background:{tr['color']} !important;}}</style>"
        )
        with st.container(key=f"pd_sw_{safe}"):
            with st.popover(" ", use_container_width=False,
                            help=f"색상: {cur_name} — 클릭해서 변경"):
                _palette(ctx, tk, tr, safe)


def _render_row(ctx, tk, tr):
    """트레이스 한 줄. 한 파일에 8개 이상 올 수 있으므로 행 하나에 모두 담는다."""
    fid = ctx.fid
    # 스와치·dash·텍스트를 한 줄에 가지런히 — vertical_alignment="center".
    c_on, c_color, c_dash, c_text = st.columns(
        [1.6, 0.7, 1.1, 1.2], vertical_alignment="center")

    # D5: 트레이스 on/off 는 Plotly 레전드가 아니라 여기 (레전드는 D1 로 제거됨)
    tr["visible"] = c_on.checkbox(
        tr["label"], value=bool(tr["visible"]),
        key=state.wkey("trace", f"{tk}.visible", fid=fid),
        help="그래프에 이 트레이스를 표시합니다.",
    )

    # 색: 현재 색 스와치 → 클릭 시 OriginLab 24색 팔레트 popover (드롭다운 제거)
    _color_control(ctx, tk, tr, c_color)

    dash_label = _DASH_BY_VALUE.get(tr["dash"], _DASH_LABELS[0])
    tr["dash"] = constants.DASH_OPTIONS[
        c_dash.selectbox(
            "선 종류", _DASH_LABELS, index=_DASH_LABELS.index(dash_label),
            key=state.wkey("trace", f"{tk}.dash", fid=fid),
            label_visibility="collapsed",
        )
    ]

    # 텍스트는 popover 안에 — 트레이스가 많아도 패널 높이가 O(1) 로 유지된다 (G1)
    with c_text.popover("텍스트", use_container_width=True):
        tr["legend_raw"] = st.text_input(
            "레전드 텍스트", value=tr["legend_raw"],
            key=state.wkey("trace", f"{tk}.legend_raw", fid=fid),
            help=constants.MARKUP_HELP,
        )
        # 인셋 텍스트는 [인셋] 탭(panel_inset)이 단독 소유한다 (PLAN §5.3). 여기서도
        # 같은 inset_raw 를 렌더하면 st.tabs 가 매 run 두 위젯을 다 실행 → value= 무시
        # (PLAN §2.3 함정2) → 필드가 서로를 덮어써 손상된다. 그래서 제거했다 (WP9).


def render(ctx) -> None:
    """트레이스 탭 렌더."""
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
