"""앱 레이아웃. 소유: WP5 / 배선: WP9.

`render_app()` 은 `app.py` 가 부르는 **유일한 진입점**이다 (PLAN §5.2 배치).

- 헤더 (G2): 로고 + 제목 + 우측 정렬 `st.popover("＋ 파일 추가")` 안의
  `st.file_uploader` (→ G3 버그 자체가 소멸).
- 파일 배너 (F2): `st.segmented_control` — `st.tabs` 아님 (V13 이 여기선 역효과).
- 본문: `st.columns([5,11])` 좌 편집패널 / 우 그래프.
  좌 = `key="pd_edit_panel"` 안의 `st.tabs`([트레이스][축][서식][인셋][포맷]).
      높이는 theme 의 `--pd-panel-h` 가 바인딩한다 — 768 하드코딩 금지 (C5).
  우 = `key="pd_graph_stage"` 그래프 스테이지 (figure 960×768, 표시만 CSS 축소).

각 패널에 넘길 ctx (PLAN §1.2):
    ctx = SimpleNamespace(fid, settings, traces, parsed, fig_px, domains)
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import streamlit as st

from pd_app import figure, parsing, state, theme
from pd_app.ui import (
    panel_axes,
    panel_inset,
    panel_presets,
    panel_style,
    panel_traces,
    summary,
    toolbar,
)


@st.dialog("📖 앱 사용 설명서", width="large")
def show_manual() -> None:
    """확정된 파일명 매핑 규칙을 반영한 종합 사용 설명서 모달 창."""
    st.markdown("""
    ### 1. 기본 사용 흐름
    1. 우측 상단의 **[＋ 파일 추가]** 버튼을 눌러 Keithley 결과 파일(`.xls`, `.xlsx`)을 업로드합니다.
    2. 좌측 패널의 탭들을 이용해 **트레이스 서식, 축 범위, 스케일, 인셋 레전드** 등을 편집합니다.
    3. 우측 그래프 스테이지에서 실시간 정밀 렌더링된 결과를 확인합니다.
    
    ### 2. 🚨 파일 이름 작성 규칙 (자동 파장 매핑)
    장비에서 측정된 데이터 시트들을 올바른 파장 라벨로 자동 변환하려면 아래의 명확한 네이밍 규칙을 준수해야 합니다.
    
    * **작성 형식**: `날짜 [측정순서] #샘플명.xlsx`
    * **규칙 핵심**: 
      * 대괄호 `[...]` 안의 매핑 코드 글자 수는 엑셀 내 **데이터 시트 개수와 정확히 일치**해야 합니다.
      * **`#` 문자 뒤의 샘플명은 시스템이 읽지 않고 조용히 제외**하므로, 개별 식별을 위한 자유로운 메모 공간으로 활용하시면 됩니다.
    
    **[대괄호 안의 코드별 파장 매핑 목록]**
    * `d` : Dark (암전류)
    * `1` : 365 nm  |  `2` : 405 nm  |  `3` : 470 nm  |  `4` : 530 nm
    * `5` : 625 nm  |  `6` : 740 nm  |  `7` : 850 nm  |  `8` : 940 nm
    
    *예시: 암전류 측정 후 365nm, 470nm, 940nm를 순서대로 추가 측정하여 총 4개의 데이터 시트가 있는 경우*
    $\rightarrow$ `20260720 [d138] #Device_A_Run01.xlsx` (여기서 `#Device_A_Run01` 부분은 시스템이 분석하지 않습니다.)
    
    ### 3. 마크업 텍스트 서식 가이드
    축 제목이나 인셋 레이블 입력란에는 아래와 같은 리치 마크업 문법을 지원합니다.
    * **텍스트 굵게**: `**텍스트**`
    * **기울임꼴**: `*텍스트*`
    * **위첨자**: `^{텍스트}` (예: `cm^{2}` $\rightarrow$ cm²)
    * **아래첨자**: `_{텍스트}` (예: `V_{OP}` $\rightarrow$ V_OP)
    * **글자 색상**: `{#원하는Hex색상|텍스트}` (예: `{#FF0000|적색}` $\rightarrow$ 빨간 글씨)
    
    ### 4. 고화질 데이터 내보내기
    * 우측 하단의 **[성능 지표 · 내보내기]** 확장 패널을 열어 논문 및 보고서 게재용 고해상도(10×8인치 네이티브 출력) PNG 이미지 또는 대화형 HTML 파일로 영구 저장할 수 있습니다.
    """)


def _header() -> None:
    """로고 + 제목 (좌) · 사용 설명서 버튼 (중) · ＋ 파일 추가 popover (우)."""
    # 헤더 정렬 및 공간 분할 (5:1:1 비율)
    c_title, c_manual, c_upload = st.columns([5, 1, 1], vertical_alignment="center")

    with c_title:
        logo = theme.logo_url()
        img = f"<img src='{logo}' alt='logo'/>" if logo else ""
        st.html(
            f"<div class='pd-title-glass'>{img}"
            "<h2>Photodetector I-V Studio</h2></div>"
        )

    with c_manual:
        # 파일 추가 버튼과 시각적 높이 및 너비를 맞춰 정렬 배치
        if st.button("📖 사용 설명서", use_container_width=True):
            show_manual()

    with c_upload:
        with st.container(key="pd_upload"):
            with st.popover("＋ 파일 추가", use_container_width=True):
                uploaded = st.file_uploader(
                    "Keithley 측정 파일 (.xls / .xlsx)",
                    accept_multiple_files=True,
                    type=["xls", "xlsx"],
                    key="pd_file_uploader",
                )
    _ingest(uploaded)


def _ingest(uploaded) -> None:
    """업로드된 파일을 상태에 추가. sha 로 이미 있는 파일은 건너뛴다 —
    매 rerun 마다 uploader 가 같은 파일을 계속 돌려주므로, 그대로 add_file 을
    부르면 add_file 이 active 를 매번 그 파일로 되돌려 배너 선택이 씹힌다.
    """
    if not uploaded:
        return
    existing = {f["sha"] for f in state.S()["files"].values()}
    for uf in uploaded:
        data = uf.getvalue()
        sha = hashlib.sha1(data).hexdigest()
        if sha in existing:
            continue
        try:
            state.add_file(uf.name, data)
            existing.add(sha)
        except Exception as exc:  # 파싱 실패는 표시만 하고 앱은 계속 산다
            st.error(f"'{uf.name}' 을(를) 열지 못했습니다: {exc}")


def _banner() -> str | None:
    """파일 배너 (F2). 활성 fid 반환 (없으면 None)."""
    s = state.S()
    order = s["order"]
    if not order:
        return None

    files = s["files"]
    with st.container(key="pd_banner"):
        c_sel, c_del = st.columns([9, 1], vertical_alignment="center")
        with c_sel:
            sel = st.segmented_control(
                "파일",
                order,
                format_func=lambda fid: files[fid]["name"],
                default=state.active_fid() or order[0],
                label_visibility="collapsed",
                key="pd_banner_sel",
            )
        if sel:
            state.set_active(sel)
        with c_del:
            if st.button("✕", help="현재 파일 제거", use_container_width=True):
                state.remove_file(state.active_fid())
                st.rerun()
    return state.active_fid()


def _empty_state() -> None:
    """파일이 하나도 없을 때의 안내 (레거시 동작 미러)."""
    st.info(
        "오른쪽 위 **＋ 파일 추가** 버튼으로 Keithley 측정 **.xls / .xlsx** 파일을 "
        "올리면 논문·보고서용 I-V 그래프가 여기에 표시됩니다."
    )
    st.stop()


def _range_i_warning(parsed) -> None:
    """Range I 불일치 경고 (레거시 894-899 로직 그대로) — 페이지 상단."""
    traces = parsed["traces"]
    uniq = sorted({t["range_i"] for t in traces if t["range_i"]})
    if len(uniq) <= 1:
        return
    detail = ", ".join(f"{t['label']}: {t['range_i']}" for t in traces)
    st.warning(
        "⚠️ Range I 불일치 경고 — 서로 다른 값이 사용되었습니다: "
        f"{', '.join(uniq)}  ({detail})"
    )


def _build_ctx(fid) -> SimpleNamespace:
    """PLAN §1.2 의 ctx 조립."""
    settings = state.file_settings(fid)
    f = state.S()["files"][fid]
    parsed = parsing.parse_file(f["bytes"], f["name"])
    return SimpleNamespace(
        fid=fid,
        settings=settings,
        traces=settings["traces"],
        parsed=parsed,
        fig_px=figure.px_size(settings["geom"]),
        domains=figure.domains(settings["geom"]),
    )


def _edit_panel(ctx) -> None:
    """좌: 편집 패널. 높이는 theme 의 --pd-panel-h 가 바인딩한다 (C5: 768 금지)."""
    with st.container(key="pd_edit_panel"):
        t_tr, t_ax, t_st, t_in, t_fmt = st.tabs(
            ["트레이스", "축", "서식", "인셋", "포맷"]
        )
        with t_tr:
            panel_traces.render(ctx)
        with t_ax:
            panel_axes.render(ctx)
        with t_st:
            panel_style.render(ctx)
        with t_in:
            panel_inset.render(ctx)
        with t_fmt:
            panel_presets.render(ctx)


def _display_scale() -> float:
    """표시 배율 s. **CSS transform 대신 figure 를 s배 네이티브 축소**해 렌더한다
    (라벨이 수평으로 나온다). 뷰포트 자동측정은 ResizeObserver busy 루프/rerun 루프
    위험이 커 폐기하고, 절대 안 깨지는 number_input 으로 사용자가 조절한다.
    첫 paint 기본값 0.72 (1536×695 에서 스크롤 없이 들어가는 값).
    """
    return float(
        st.number_input(
            "표시 배율", min_value=0.30, max_value=1.00, value=0.72, step=0.02,
            format="%.2f", key="pd_display_scale",
            help="화면 미리보기 크기만 바꿉니다. 내보내기(PNG·HTML)는 항상 10×8인치입니다.",
        )
    )


def _graph_stage(ctx) -> None:
    """우: 그래프 스테이지. figure 를 px_scale 로 네이티브 축소해 렌더 (transform 없음).
    내보내기는 summary 가 px_scale=1.0 별도 figure 로 만든다 → 정확히 960×768."""
    fid = ctx.fid
    stem = str(state.S()["files"][fid]["name"]).rsplit(".", 1)[0] or "graph"

    c_gap, c_scale = st.columns([3, 1], vertical_alignment="bottom")
    with c_scale:
        s = _display_scale()

    # 좌측 편집 패널 높이를 축소된 그래프 높이에 맞춘다 (단방향, busy 루프 없음)
    fig_h_px = int(round(ctx.fig_px[1] * s))
    theme.panel_height(fig_h_px)

    with st.container(key="pd_graph_stage"):
        fig = figure.build_figure(fid, px_scale=s)
        st.plotly_chart(
            fig,
            width="content",
            config={
                # transform 을 안 쓰므로 plotly 는 s*960 × s*768 를 그대로 정상 레이아웃한다.
                # responsive 는 꺼서 컬럼 폭에 맞춰 재축소되는 것만 막는다.
                "displaylogo": False,
                "responsive": False,
                # 카메라 PNG 는 화면 배율(s)과 무관하게 항상 네이티브 960×768 을 scale 3
                # 으로 내보낸다 — width/height 를 명시해 s-축소된 표시 figure 를 따르지 않게.
                "toImageButtonOptions": {
                    "format": "png",
                    "width": int(ctx.fig_px[0]),
                    "height": int(ctx.fig_px[1]),
                    "scale": 3,
                    "filename": stem,
                },
            },
        )

    # 로그축에서 못 그린 (<=0) 점 수
    zeros = figure.zero_count(fig)
    if zeros > 0:
        st.caption(
            f"로그 스케일이라 0 이하인 점 {zeros}개는 표시에서 제외되었습니다."
        )

    # 데이터 요약 / 성능 지표·내보내기 를 별도 expander 로 분리 (둘 다 접힘 → 스크롤 최소)
    with st.expander("데이터 요약", expanded=False):
        summary.render(ctx)
    with st.expander("성능 지표 · 내보내기", expanded=False):
        summary.render_metrics(ctx)


def render_app() -> None:
    """헤더 + 파일 배너 + 좌 편집패널/우 그래프 전체를 렌더."""
    theme.install()

    _header()
    fid = _banner()
    if fid is None:
        _empty_state()

    ctx = _build_ctx(fid)
    _range_i_warning(ctx.parsed)

    with st.container(key="pd_body"):
        col_l, col_r = st.columns([5, 11], gap="medium", vertical_alignment="top")
        with col_l:
            _edit_panel(ctx)
        with col_r:
            _graph_stage(ctx)
