"""[축] 탭: X/Y 스케일·범위, major/minor dtick (A4/A6), 제목 텍스트+standoff (B2). 소유: WP3.

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

import streamlit as st

from pd_app import state
from pd_app.ui.toolbar import rich_input

_TYPES = ["linear", "log"]
_TYPE_LABELS = {"linear": "Linear", "log": "Log"}

# A4: Log 축 minor 는 D1/D2 계열 (V9 로 검증). Linear 축에는 절대 보이면 안 된다.
_LOG_MINOR = [None, "D1", "D2"]
_LOG_MINOR_LABELS = {
    None: "없음",
    "D1": "D1 (2~9, 8개)",
    "D2": "D2 (2·5, 2개)",
}


def _as_float(v, fallback=None):
    """모델 값 -> float. 축 타입을 바꾸면 minor_dtick 이 'D1' 같은 문자열일 수 있다."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return fallback


def _range_controls(ax, axis, fid):
    """A5: auto 여도 figure.py 가 데이터 min/max 로 range 를 명시한다(패딩 제거).
    여기서는 모델의 auto/min/max 만 다룬다."""
    ax["auto"] = st.checkbox(
        "범위 자동", value=bool(ax["auto"]),
        key=state.wkey("axes", f"{axis}.auto", fid=fid),
        help="끄면 Min/Max 를 직접 지정합니다.",
    )
    if ax["auto"]:
        return
    c_min, c_max = st.columns(2)
    ax["min"] = c_min.number_input(
        "Min", value=_as_float(ax["min"]), format="%g",
        key=state.wkey("axes", f"{axis}.min", fid=fid),
    )
    ax["max"] = c_max.number_input(
        "Max", value=_as_float(ax["max"]), format="%g",
        key=state.wkey("axes", f"{axis}.max", fid=fid),
    )


def _tick_controls(ax, axis, fid):
    """A6 major scale step + A4 minor tick. 컨트롤은 축 타입에 맞는 것만 보여준다."""
    is_log = ax["type"] == "log"

    # --- Log 축(사용자 확정): Major 는 1 decade, Minor 는 8개(D1) 고정. 조절 없음 ---
    # 로그 major 는 1E-11, 1E-10 … 처럼 항상 1 decade, minor 는 decade 안 2~9 (8개).
    if is_log:
        ax["dtick"] = 1
        ax["minor_dtick"] = "D1"
        st.caption("로그축: Major 1 decade (1E-11, 1E-10 …) · Minor 8개 (2~9) 고정")
        return

    # --- A6: (Linear 전용) major dtick (축 scale step). 예시 X 축은 0.5 ---
    major_auto = st.checkbox(
        "Major 간격 자동", value=(ax["dtick"] is None),
        key=state.wkey("axes", f"{axis}.dtick_auto", fid=fid),
        help="끄면 눈금 간격(step)을 직접 지정합니다.",
    )
    if major_auto:
        ax["dtick"] = None
    else:
        cur = _as_float(ax["dtick"], 0.5)
        ax["dtick"] = st.number_input(
            "Major 간격 (step)",
            value=cur, step=0.1, format="%g",
            key=state.wkey("axes", f"{axis}.dtick", fid=fid),
        )

    # --- A4: (Linear 전용) minor tick 숫자 간격 ---

    minor_on = st.checkbox(
        "Minor 눈금 표시", value=(_as_float(ax["minor_dtick"]) is not None),
        key=state.wkey("axes", f"{axis}.minor_on", fid=fid),
    )
    if not minor_on:
        ax["minor_dtick"] = None
        return
    ax["minor_dtick"] = st.number_input(
        "Minor 간격", value=_as_float(ax["minor_dtick"], 0.1),
        step=0.05, format="%g", min_value=0.0,
        key=state.wkey("axes", f"{axis}.minor_lin", fid=fid),
        help="Major 간격을 나누는 눈금 간격입니다.",
    )


def _title_controls(ax, axis, fid):
    """B2: 축 제목 텍스트 + 제목 위치(standoff, V9 로 검증)."""
    ax["title_raw"] = rich_input(
        "축 제목", ax["title_raw"],
        key=state.wkey("axes", f"{axis}.title_raw", fid=fid),
    )
    standoff_auto = st.checkbox(
        "제목 위치 자동", value=(ax["title_standoff"] is None),
        key=state.wkey("axes", f"{axis}.standoff_auto", fid=fid),
        help="끄면 축에서 제목까지의 거리(px)를 직접 지정합니다.",
    )
    if standoff_auto:
        ax["title_standoff"] = None
    else:
        ax["title_standoff"] = st.number_input(
            "제목 위치 (px)", value=_as_float(ax["title_standoff"], 20.0),
            step=1.0, min_value=0.0, max_value=200.0, format="%g",
            key=state.wkey("axes", f"{axis}.standoff", fid=fid),
        )


def _axis(ctx, axis):
    """축 하나 (x 또는 y)."""
    fid = ctx.fid
    ax = ctx.settings["axes"][axis]

    # A1: Y 기본은 Log (constants.DEFAULTS 가 보유). 여기서는 모델에서 시드만 한다.
    ax["type"] = st.radio(
        "스케일", _TYPES, index=_TYPES.index(ax["type"] if ax["type"] in _TYPES else "linear"),
        format_func=lambda v: _TYPE_LABELS[v], horizontal=True,
        key=state.wkey("axes", f"{axis}.type", fid=fid),
    )

    if axis == "y":
        # PLAN §8.2: Log 는 절댓값 강제, Linear 는 사용자 선택.
        # A2 가 제거하라고 한 것은 use_abs <-> Y 제목의 결합이지 이 옵션 자체가 아니다.
        if ax["type"] == "log":
            ctx.settings["use_abs"] = True
            st.checkbox("절댓값 (|I|)", value=True, disabled=True,
                        key=state.wkey("axes", "use_abs_locked", fid=fid),
                        help="로그 스케일에서는 절댓값이 필수입니다.")
        else:
            ctx.settings["use_abs"] = st.checkbox(
                "절댓값 (|I|)", value=bool(ctx.settings["use_abs"]),
                key=state.wkey("axes", "use_abs", fid=fid),
                help="AnodeI 에 절댓값을 적용합니다.",
            )

    _range_controls(ax, axis, fid)
    _tick_controls(ax, axis, fid)
    _title_controls(ax, axis, fid)


def render(ctx) -> None:
    """축 탭 렌더. X/Y 를 중첩 탭으로 나눠 패널 높이를 max(X, Y) 로 유지한다 (G1/V13)."""
    tab_x, tab_y = st.tabs(["X축", "Y축"])
    with tab_x:
        _axis(ctx, "x")
    with tab_y:
        _axis(ctx, "y")
