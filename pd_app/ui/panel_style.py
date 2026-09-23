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

import copy

import streamlit as st

from pd_app import constants, postproc, state


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

    # 👇 기존의 꼬인 인덱스 추적을 초기화하고, constants.py의 기본값(Myriad Pro)을 강제로 추적하도록 수정
    fam = style.get("font_family", "Myriad Pro")
    
    # 만약 기존 캐시나 세션에 Arial이 남아있어 Myriad Pro로 강제 전환하고 싶다면 아래 주석 처리를 해제하세요
    # if fam == "Arial": fam = "Myriad Pro"
    
    if fam in constants.FONT_FAMILIES:
        idx = constants.FONT_FAMILIES.index(fam)
    else:
        idx = constants.FONT_FAMILIES.index("Myriad Pro")

    # 변경된 인덱스로 가리키고, 선택된 값을 다시 모델(style)에 저장
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


def _dark_offset(ctx) -> None:
    """Dark 0V 영점 보정 토글 — 표시 전용, 기본 꺼짐, 현재 파일에만 적용."""
    off = ctx.parsed.get("i_offset")
    ctx.settings["dark_offset"] = st.checkbox(
        "Dark 0V 영점 보정 (그래프 전용)",
        value=bool(ctx.settings.get("dark_offset", False)),
        disabled=off is None,
        key=state.wkey("style", "dark_offset", fid=ctx.fid),
        help="암전류를 광전류용 Range I 로 함께 측정하면 레인지 분해능 바닥에 깔려 "
             "0V 골짜기가 안 보이고 직선처럼 그려집니다. 이 옵션을 켜면 Dark 의 0V "
             "전류를 모든 트레이스에서 빼서 골짜기를 복원합니다. "
             "**그래프 모양에만 영향을 주며 성능지표(R·D*)는 항상 raw 로 계산됩니다.** "
             "현재 파일에만 적용됩니다.",
    )
    if off is None:
        st.caption("Dark 트레이스에 0V 부근(±0.05V) 지점이 없어 보정할 수 없습니다.")
    elif ctx.settings["dark_offset"]:
        st.caption(f"적용 중 — 모든 트레이스에서 {off:+.3e} A 를 뺀 값으로 그립니다.")
    else:
        st.caption(f"현재 무보정(raw). 켜면 {off:+.3e} A 를 뺍니다.")


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


def _postproc(ctx) -> None:
    """표시용 후처리 — 분할 측정 이어붙이기 + 스무딩. 전부 기본 꺼짐, 현재 파일에만 적용."""
    fid = ctx.fid
    p = ctx.settings.setdefault(
        "postproc", copy.deepcopy(constants.DEFAULTS["postproc"]))

    st.info("아래 항목은 **그래프 표시 전용**입니다. 성능지표(R·D\\*)는 어떤 설정이든 "
            "항상 원본(raw)으로 계산됩니다.", icon="ℹ️")

    _dark_offset(ctx)
    st.markdown("---")

    # --- 이어붙이기 ---
    labels = [t["label"] for t in ctx.parsed["traces"]]
    split = sorted({lb for lb in labels if labels.count(lb) > 1})
    p["stitch"] = st.checkbox(
        "분할 측정 이어붙이기",
        value=bool(p.get("stitch", False)),
        disabled=not split,
        key=state.wkey("postproc", "stitch", fid=fid),
        help="암전류를 0→-1V / 0→+1V 로 나눠 재면 두 스윕의 영점이 달라 접합부(0V)에 "
             "단차가 생깁니다. 켜면 같은 라벨의 조각들을 접합부에서 평행이동해 이어 "
             "붙입니다. 기울기는 건드리지 않고, 측정 순서상 첫 조각이 기준입니다.",
    )
    if not split:
        st.caption("같은 라벨이 2개 이상인 트레이스가 없어 이어붙일 대상이 없습니다.")
    else:
        st.caption(f"대상: {', '.join(split)} — 각 라벨의 첫 조각을 기준으로 맞춥니다.")

    if split and p["stitch"]:
        modes = list(postproc.STITCH_MODES)
        cur_m = p.get("stitch_mode", "shift")
        p["stitch_mode"] = st.radio(
            "잇는 방식", modes,
            index=modes.index(cur_m) if cur_m in modes else 0,
            format_func=lambda k: postproc.STITCH_MODES[k],
            key=state.wkey("postproc", "stitch_mode", fid=fid),
            help="**평행이동** — 조각 전체를 옮겨 단차만 없앱니다. 모양이 그대로 보존되는 "
                 "대신 접합부 기울기 차이(꺾임)는 남습니다.\n\n"
                 "**테이퍼** — 이동량을 접합부에서만 100%, 지정 반경 밖에서 0 으로 "
                 "줄입니다. 먼 쪽 끝값이 원본 그대로 남습니다.\n\n"
                 "**블렌드** — 평행이동 후 접합부 구간을 양쪽 공통 직선으로 섞어 "
                 "기울기까지 잇습니다. 가장 매끄럽지만 **그 구간 값은 합성값**입니다.",
        )
        if p["stitch_mode"] != "shift":
            p["stitch_span"] = st.number_input(
                "접합부 반경 (V)",
                min_value=postproc.SPAN_MIN, max_value=postproc.SPAN_MAX,
                value=float(p.get("stitch_span", 0.05)), step=0.005, format="%.3f",
                key=state.wkey("postproc", "stitch_span", fid=fid),
                help="접합부 좌우 이 범위만 손댑니다. 좁을수록 원본에 가깝고, "
                     "넓을수록 매끄럽습니다.",
            )
        if p["stitch_mode"] == "blend":
            st.warning(f"접합부 ±{p.get('stitch_span', 0.05):g}V 구간은 **합성값**입니다. "
                       "원본은 엑셀 `Raw` 시트에 그대로 남습니다.", icon="⚠️")

    st.markdown("---")

    # --- 스무딩 ---
    methods = list(postproc.SMOOTH_METHODS)
    cur = p.get("smooth", "none")
    p["smooth"] = st.selectbox(
        "스무딩", methods,
        index=methods.index(cur) if cur in methods else 0,
        format_func=lambda k: postproc.SMOOTH_METHODS[k],
        key=state.wkey("postproc", "smooth", fid=fid),
        help="**Savitzky-Golay 를 권장합니다.** 창 안에서 다항식을 맞추므로 I-V 곡선처럼 "
             "지수적으로 휘는 구간에서도 기울기를 지킵니다. 이동 평균은 단순한 대신 "
             "휜 구간을 평평하게 끌어내려 오히려 원본보다 어긋날 수 있습니다.",
    )
    if p["smooth"] != "none":
        c1, c2 = st.columns(2)
        p["window"] = c1.number_input(
            "창 크기 (점)", min_value=postproc.WINDOW_MIN, max_value=postproc.WINDOW_MAX,
            value=int(p.get("window", 7)), step=2,
            key=state.wkey("postproc", "window", fid=fid),
            help="클수록 매끄럽지만 세부가 뭉개집니다. 짝수를 넣어도 홀수로 맞춥니다.",
        )
        if p["smooth"] == "savgol":
            p["poly"] = c2.number_input(
                "다항 차수", min_value=postproc.POLY_MIN, max_value=postproc.POLY_MAX,
                value=int(p.get("poly", 2)), step=1,
                key=state.wkey("postproc", "poly", fid=fid),
                help="창 크기보다 작아야 합니다. 2~3 이 무난합니다.",
            )
        tgts = list(postproc.TARGETS)
        cur_t = p.get("targets", "all")
        p["targets"] = st.radio(
            "적용 대상", tgts, horizontal=True,
            index=tgts.index(cur_t) if cur_t in tgts else 0,
            format_func=lambda k: postproc.TARGETS[k],
            key=state.wkey("postproc", "targets", fid=fid),
        )

    st.markdown("---")
    st.caption(f"현재 후처리: **{postproc.describe(ctx.settings)}**")
    st.caption("엑셀 내보내기는 `Raw`(원본) · `Processed`(후처리 적용) · `Plot`(그래프 그대로) "
               "시트로 나뉘어 저장됩니다.")


def render(ctx) -> None:
    """서식 탭 렌더."""
    tab_font, tab_geom, tab_fix = st.tabs(["폰트·선", "크기·배치", "보정"])
    with tab_font:
        _fonts(ctx)
    with tab_geom:
        _geometry(ctx)
    with tab_fix:
        _postproc(ctx)
