"""[서식] 탭: 폰트 (C1), 크기 스테퍼 (C2/C3), 선 두께 0.5 (C4), geometry (B1). 소유: WP3.

ctx = SimpleNamespace(fid, settings, traces, parsed, fig_px, domains)
    fid       현재 활성 파일 id
    settings  state.file_settings(fid) — 모델이 유일한 진실
    traces    settings["traces"] (TKey -> dict)
    parsed    parsing.parse_file() 결과
    fig_px    figure.px_size(geom) → (w, h)
    domains   figure.domains(geom) → {"x0","x1","y0","y1"}

패널은 read-render-writeback. 위젯키는 반드시 `state.wkey(group, name, fid=fid)`.
폰트 크기는 슬라이더 금지 — `st.number_input` 스테퍼, 전 항목 6~50 통일 (C2/C3).
이 모듈은 `render` 외에 아무것도 공개하지 않는다.
"""

from __future__ import annotations

import streamlit as st

from pd_app import constants, state


def _font_size(label, style, field, fid, help=None):
    """C2/C3: 모든 폰트 크기는 동일 규격 — number_input 스테퍼, 6~50, 기본 30.
    슬라이더는 SPEC C3 가 명시적으로 금지한다."""
    try:
        cur = int(style[field])
    except (TypeError, ValueError):
        cur = 30
    cur = max(constants.FONT_SIZE_MIN, min(constants.FONT_SIZE_MAX, cur))
    style[field] = st.number_input(
        label, min_value=constants.FONT_SIZE_MIN, max_value=constants.FONT_SIZE_MAX,
        value=cur, step=1,
        key=state.wkey("style", field, fid=fid), help=help,
    )


def _geom_num(col, label, geom, field, fid, *, step, min_value, max_value, fmt, help=None):
    """B1: 배경(inch) / 그래프(% of page) 수치. 높이 슬라이더는 폐기됐다 — 되살리지 말 것."""
    try:
        cur = float(geom[field])
    except (TypeError, ValueError):
        cur = float(constants.DEFAULTS["geom"][field])
    cur = max(min_value, min(max_value, cur))
    geom[field] = col.number_input(
        label, value=cur, step=step, min_value=min_value, max_value=max_value,
        format=fmt, key=state.wkey("geom", field, fid=fid), help=help,
    )


def _fonts(ctx):
    style = ctx.settings["style"]
    fid = ctx.fid

    # C1: Pretendard / Myriad Pro 포함. 기본값은 의도적으로 "Arial" (논문용) 이므로
    # 절대 index=0 을 쓰지 말고 모델 값에서 시드한다.
    fam = style["font_family"]
    idx = (constants.FONT_FAMILIES.index(fam)
           if fam in constants.FONT_FAMILIES else
           constants.FONT_FAMILIES.index(constants.DEFAULTS["style"]["font_family"]))
    style["font_family"] = st.selectbox(
        "폰트", constants.FONT_FAMILIES, index=idx,
        key=state.wkey("style", "font_family", fid=fid),
    )

    c1, c2 = st.columns(2)
    with c1:
        _font_size("축 제목 크기", style, "title_font_size", fid)
    with c2:
        _font_size("눈금 크기", style, "tick_font_size", fid)

    # C4: 선 두께는 0.5 간격 (int 아님)
    style["line_width"] = st.number_input(
        "선 두께", value=float(style["line_width"]),
        min_value=0.5, max_value=20.0, step=constants.LINE_WIDTH_STEP, format="%.1f",
        key=state.wkey("style", "line_width", fid=fid),
        help="0.5 간격으로 조절합니다.",
    )

    c3, c4 = st.columns(2)
    style["show_grid"] = c3.checkbox(
        "격자선 표시", value=bool(style["show_grid"]),
        key=state.wkey("style", "show_grid", fid=fid),
    )
    style["show_markers"] = c4.checkbox(
        "마커 표시", value=bool(style["show_markers"]),
        key=state.wkey("style", "show_markers", fid=fid),
    )


def _geometry(ctx):
    """B1: Origin 방식 2단계. Background(inch) -> Graph(% of page)."""
    geom = ctx.settings["geom"]
    fid = ctx.fid

    st.caption("Background — 페이지 크기 (inch)")
    c1, c2 = st.columns(2)
    _geom_num(c1, "Width", geom, "page_w_in", fid, step=0.5,
              min_value=1.0, max_value=40.0, fmt="%.2f")
    _geom_num(c2, "Height", geom, "page_h_in", fid, step=0.5,
              min_value=1.0, max_value=40.0, fmt="%.2f")

    st.caption("Graph — 페이지 대비 위치·크기 (%)")
    c3, c4 = st.columns(2)
    _geom_num(c3, "Left", geom, "graph_left_pct", fid, step=0.1,
              min_value=0.0, max_value=100.0, fmt="%.2f")
    _geom_num(c4, "Top", geom, "graph_top_pct", fid, step=0.1,
              min_value=0.0, max_value=100.0, fmt="%.2f",
              help="페이지 위쪽에서부터의 거리입니다.")
    c5, c6 = st.columns(2)
    _geom_num(c5, "Width", geom, "graph_width_pct", fid, step=0.1,
              min_value=1.0, max_value=100.0, fmt="%.2f")
    _geom_num(c6, "Height", geom, "graph_height_pct", fid, step=0.1,
              min_value=1.0, max_value=100.0, fmt="%.2f")

    w_px, h_px = ctx.fig_px
    st.caption(
        f"내보내기 크기 {geom['page_w_in']:g} × {geom['page_h_in']:g} in "
        f"= {w_px} × {h_px} px · 화면의 그래프는 비례 축소된 미리보기입니다."
    )


def render(ctx) -> None:
    """서식 탭 렌더."""
    tab_font, tab_geom = st.tabs(["폰트·선", "크기·배치"])
    with tab_font:
        _fonts(ctx)
    with tab_geom:
        _geometry(ctx)
