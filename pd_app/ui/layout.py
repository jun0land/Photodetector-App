"""앱 레이아웃. 소유: WP5 / 배선: WP9.

`render_app()` 은 `app.py` 가 부르는 **유일한 진입점**이다 (PLAN §5.2 배치).
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
    """간소화된 파일명 매핑 규칙이 반영된 사용 설명서 모달 창."""
    st.markdown("""
    ### 1. 기본 사용 흐름
    1. 우측 상단의 **[＋ 파일 추가]** 버튼을 눌러 Keithley 결과 파일(`.xls`, `.xlsx`)을 업로드합니다.
    2. 좌측 패널의 탭들을 이용해 **트레이스 서식, 축 범위, 스케일, 인셋 레전드** 등을 편집합니다.
    3. 우측 그래프 스테이지에서 실시간 정밀 렌더링된 결과를 확인합니다.
    
    ### 2. 🚨 파일 이름 작성 규칙 (자동 파장 매핑)
    장비에서 측정된 데이터 시트들을 올바른 파장 라벨로 자동 변환하려면 아래의 단순 규칙을 준수해야 합니다.
    
    * **작성 형식**: `샘플명 [측정순서].xlsx` (예: `Device_A [d138].xlsx`)
    * **규칙 핵심**: 
      * **대괄호 `[...]` 외부에 있는 모든 문구(샘플명, 날짜, 메모 등)는 완전히 무시**됩니다. `#` 기호도 붙이실 필요가 없습니다.
      * 오직 **대괄호 `[...]` 내부의 코드 글자 수만 엑셀 내 데이터 시트 개수와 1:1로 정확히 일치**하면 됩니다.
    
    **[대괄호 안의 코드별 파장 매핑 목록]**
    * `d` : Dark (암전류)
    * `1` : 365 nm  |  `2` : 405 nm  |  `3` : 470 nm  |  `4` : 530 nm
    * `5` : 625 nm  |  `6` : 740 nm  |  `7` : 850 nm  |  `8` : 940 nm
    
    *예시: 샘플명이 DeviceA 이고, 암전류(d) 후 365nm(1), 470nm(3), 940nm(8)를 순서대로 측정하여 총 4개의 시트가 있는 경우*
    $\rightarrow$ **`DeviceA [d138].xlsx`**
    
    ### 3. 마크업 텍스트 서식 가이드
    축 제목이나 인셋 레이블 입력란에는 아래와 같은 리치 마크업 문법을 지원합니다.
    * **텍스트 굵게**: `**텍스트**`
    * **기울임꼴**: `*텍스트*`
    * **위첨자**: `^{텍스트}` (예: `cm^{2}` $\rightarrow$ cm²)
    * **아래첨자**: `_{텍스트}` (예: `V_{OP}` $\rightarrow$ V_OP)
    * **글자 색상**: `{#원하는Hex색상|텍스트}` (예: `{#FF0000|적색}`)
    
    ### 4. 고화질 데이터 내보내기
    * 우측 하단의 **[성능 지표 · 내보내기]** 패널에서 출판용 고해상도(10×8인치) PNG 및 JPG로 추출할 수 있습니다.
    """)


def _header() -> None:
    if "uploader_key" not in st.session_state:
        st.session_state["uploader_key"] = 0

    c_title, c_manual, c_del, c_upload = st.columns([5, 1, 1, 1], vertical_alignment="center")

    with c_title:
        logo = theme.logo_url()
        img = f"<img src='{logo}' alt='logo'/>" if logo else ""
        st.html(
            f"<div class='pd-title-glass'>{img}"
            "<h2>Photodetector I-V Studio</h2></div>"
        )

    with c_manual:
        if st.button("📖 사용 설명서", use_container_width=True):
            show_manual()

    with c_del:
        s = state.S()
        if s["order"] and state.active_fid():
            def _handle_header_remove():
                target_fid = state.active_fid()
                if target_fid:
                    state.remove_file(target_fid)
                    if "pd_banner_sel" in st.session_state:
                        del st.session_state["pd_banner_sel"]
                    st.session_state["uploader_key"] += 1

            st.button(
                "✕ 제거", 
                help="현재 보고 있는 활성 파일 제거", 
                type="secondary",
                use_container_width=True, 
                on_click=_handle_header_remove
            )

    with c_upload:
        with st.container(key="pd_upload"):
            with st.popover("＋ 파일 추가", use_container_width=True):
                uploaded = st.file_uploader(
                    "Keithley 측정 파일 (.xls / .xlsx)",
                    accept_multiple_files=True,
                    type=["xls", "xlsx"],
                    key=f"pd_file_uploader_{st.session_state['uploader_key']}",
                )
    _ingest(uploaded)


def _ingest(uploaded) -> None:
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
        except Exception as exc:
            st.error(f"'{uf.name}' 을(를) 열지 못했습니다: {exc}")


def _banner() -> str | None:
    s = state.S()
    order = s["order"]
    if not order:
        return None

    files = s["files"]
    with st.container(key="pd_banner"):
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
            
    return state.active_fid()


def _empty_state() -> None:
    st.info(
        "오른쪽 위 **＋ 파일 추가** 버튼으로 Keithley 측정 **.xls / .xlsx** 파일을 "
        "올리면 논문·보고서용 I-V 그래프가 여기에 표시됩니다."
    )
    st.stop()


def _range_i_warning(parsed) -> None:
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
    return float(
        st.number_input(
            "표시 배율", min_value=0.30, max_value=1.00, value=0.72, step=0.02,
            format="%.2f", key="pd_display_scale",
            label_visibility="visible",
            help="화면 미리보기 크기만 바꿉니다. 내보내기(PNG·JPG)는 항상 10×8인치 정규 크기입니다.",
        )
    )


def _graph_stage(ctx, s: float) -> None:
    fid = ctx.fid
    stem = str(state.S()["files"][fid]["name"]).rsplit(".", 1)[0] or "graph"

    fig_h_px = int(round(ctx.fig_px[1] * s))
    theme.panel_height(fig_h_px)

    with st.container(key="pd_graph_stage"):
        fig = figure.build_figure(fid, px_scale=s)
        st.plotly_chart(
            fig,
            width="content",
            config={
                "displaylogo": False,
                "responsive": False,
                "toImageButtonOptions": {
                    "format": "png",
                    "width": int(ctx.fig_px[0]),
                    "height": int(ctx.fig_px[1]),
                    "scale": 3,
                    "filename": stem,
                },
            },
        )

    zeros = figure.zero_count(fig)
    if zeros > 0:
        st.caption(f"로그 스케일이라 0 이하인 점 {zeros}개는 표시에서 제외되었습니다.")

    with st.expander("데이터 요약", expanded=False):
        summary.render(ctx)
    with st.expander("성능 지표 · 내보내기", expanded=False):
        summary.render_metrics(ctx)


def render_app() -> None:
    theme.install()

    _header()
    fid = _banner()
    if fid is None:
        _empty_state()

    ctx = _build_ctx(fid)
    _range_i_warning(ctx.parsed)

    with st.container(key="pd_body"):
        col_l, col_mid, col_r = st.columns([5.0, 11.0, 2.3], gap="medium", vertical_alignment="top")
        
        with col_l:
            _edit_panel(ctx)
        with col_r:
            s_val = _display_scale()
        with col_mid:
            _graph_stage(ctx, s_val)