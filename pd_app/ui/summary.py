"""데이터 요약 + 성능 지표(Responsivity/Detectivity) + 내보내기. 소유: WP7.

ctx = SimpleNamespace(fid, settings, traces, parsed, fig_px, domains)
    fid       현재 활성 파일 id
    settings  state.file_settings(fid) — 모델이 유일한 진실
    traces    settings["traces"] (TKey -> dict)
    parsed    parsing.parse_file() 결과
    fig_px    figure.px_size(geom) → (w, h)
    domains   figure.domains(geom) → {"x0","x1","y0","y1"}

성능 지표(사용자 검수 완료 식, 임의 변형 금지):
    R(λ)  = (I_light − I_dark) / (E_e × A)                 [A/W]
    D*(λ) = R × √A / √(2·q·I_dark)                         [Jones = cm·√Hz/W]
전류는 동작전압 V_op 에서의 값(로그축이라 |I| 사용):
    I_ph = |I_light(V_op)| − |I_dark(V_op)|, D* 분모의 I_dark = |I_dark(V_op)|.
V_op 보간은 np.interp(외삽 금지 — 범위 밖이면 N/A).

두 개의 진입점:
    render(ctx)          → 데이터 요약 표 ("데이터 요약" expander)
    render_metrics(ctx)  → R/D 입력 UI + 결과 표 + 내보내기 ("성능 지표 · 내보내기")

PLAN §7 / V15: HTML 내보내기는 `include_plotlyjs=True` (오프라인 실험실 PC 대비).
"""

from __future__ import annotations

import copy
import io
import json
import math

import numpy as np
import pandas as pd
import streamlit as st

from pd_app import constants, figure, state

# to_html 은 기본적으로 div id 를 매번 새로 뽑는다 → 같은 그래프인데도 바이트가 달라져
# Streamlit ForwardMsgCache(V17) 가 매 rerun 마다 4.9MB 를 다시 전송하게 된다.
# id 를 고정하면 figure 가 그대로일 때 바이트도 그대로 = 캐시 적중.
_EXPORT_DIV_ID = "pd-export"

# 내보내기 HTML 대략 크기 (캡션용). include_plotlyjs=True 라 plotly.min.js 4.63MB 가 인라인된다.
_INLINE_MB = 4.9

# 전자 전하량 (D* 분모). 사용자 검수 완료 상수.
_Q_ELECTRON = 1.602e-19  # C


# ---------------- 데이터 요약 ----------------
def _range_i_warning(parsed) -> None:
    """Range I 불일치 경고 (유지 대상). 레인지가 다르면 노이즈 바닥·분해능이 달라
    곡선을 나란히 비교할 수 없다 — 조용히 넘기면 안 되는 값이다.
    """
    traces = parsed["traces"]
    uniq = sorted({t["range_i"] for t in traces if t["range_i"]})
    if len(uniq) <= 1:
        return
    detail = ", ".join(f"{t['label']}: {t['range_i']}" for t in traces)
    st.warning(
        f"⚠️ Range I 불일치 경고 — 서로 다른 값이 사용되었습니다: "
        f"{', '.join(uniq)}  ({detail})"
    )


def _rows(ctx) -> list[dict]:
    """요약 표의 행. 레전드는 사용자가 편집한 값(settings)이 있으면 그것을 보여준다 —
    화면의 인셋과 같은 글자여야 사용자가 행을 알아본다.
    """
    rows = []
    seen: dict[str, int] = {}
    for t in ctx.parsed["traces"]:
        label = t["label"]
        seen[label] = seen.get(label, 0) + 1
        ts = ctx.traces.get(state.tkey_of(t, seen[label])) or {}
        df = t["df"]
        rows.append({
            "Legend": ts.get("legend_raw") or t["legend"],
            "Label": label,
            "Range I": t["range_i"],
            "Sheets": ", ".join(t["sheets"]),
            "Points": len(df),
            "V min": float(df["AnodeV"].min()) if len(df) else None,
            "V max": float(df["AnodeV"].max()) if len(df) else None,
        })
    return rows


def _table(ctx) -> None:
    rows = _rows(ctx)
    if not rows:
        st.caption("표시할 트레이스가 없습니다.")
        return
    st.dataframe(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
        # 좁은 패널에 들어가야 한다 — 행이 많아도 표가 레이아웃을 밀어내지 않게 상한을 둔다.
        height=min(38 + 35 * len(rows), 230),
        column_config={
            "V min": st.column_config.NumberColumn(format="%.3g", width="small"),
            "V max": st.column_config.NumberColumn(format="%.3g", width="small"),
            "Points": st.column_config.NumberColumn(format="%d", width="small"),
        },
    )


# ---------------- 성능 지표 계산 ----------------
def _current_at(df, v_op):
    """V_op 에서의 전류(부호 유지). V 오름차순 정렬 후 np.interp.
    V_op 가 데이터 V 범위 밖이면 None (외삽 금지 — 최근접 끝값도 쓰지 않는다).
    데이터가 없으면 None.
    """
    if df is None or len(df) == 0:
        return None
    v = df["AnodeV"].to_numpy(dtype=float)
    i = df["AnodeI"].to_numpy(dtype=float)
    good = np.isfinite(v) & np.isfinite(i)
    v, i = v[good], i[good]
    if len(v) == 0:
        return None
    order = np.argsort(v)
    v, i = v[order], i[order]
    if v_op < v[0] or v_op > v[-1]:
        return None  # 외삽 금지 → N/A
    return float(np.interp(v_op, v, i))


def _dark_current_at(parsed, v_op):
    """|I_dark(V_op)|. 모든 Dark 트레이스를 **계산용으로만** concat → V 정렬 → 보간.
    Dark 없거나 V_op 범위 밖이면 None.
    """
    darks = [t["df"] for t in parsed["traces"]
             if t["label"] == "Dark" and t["df"] is not None and len(t["df"])]
    if not darks:
        return None
    cat = pd.concat(darks, ignore_index=True)
    i_dark = _current_at(cat, v_op)
    return None if i_dark is None else abs(i_dark)


def _metrics_of(settings):
    """settings 의 metrics 블록 (없으면 기본값으로 시드). irradiance dict 보장."""
    m = settings.setdefault("metrics", copy.deepcopy(constants.DEFAULTS["metrics"]))
    m.setdefault("v_op", -1.0)
    m.setdefault("area", 1.0)
    m.setdefault("area_unit", "cm2")
    if not isinstance(m.get("irradiance"), dict):
        m["irradiance"] = {}
    return m


def _wavelength_labels(parsed):
    """파일의 파장 라벨(Dark 제외), 첫 등장 순서. 중복 라벨은 한 번만."""
    out, seen = [], set()
    for t in parsed["traces"]:
        lb = t["label"]
        if lb == "Dark" or lb in seen:
            continue
        seen.add(lb)
        out.append(lb)
    return out


def _compute_metrics(ctx):
    """파장별 R, D* 계산. 반환 (rows, i_dark_abs, v_op, area_cm2).

    rows = [{"파장", "E_e", "R", "D"}] — R/D 는 float 또는 None(N/A).
    엣지: E_e≤0/미입력 → R,D=N/A. I_dark 없음/≤0 → D=N/A(그리고 R 도 I_dark 필요).
          V_op 범위 밖 트레이스 → 그 행 N/A. I_ph≤0 → R 음수/0 그대로(가리지 않음).
    """
    m = _metrics_of(ctx.settings)
    v_op = float(m["v_op"])
    area_cm2 = float(m["area"]) * (1e-2 if m["area_unit"] == "mm2" else 1.0)
    irr = m["irradiance"]
    i_dark_abs = _dark_current_at(ctx.parsed, v_op)

    # 파장 라벨 → 대표 트레이스 df (첫 등장)
    df_by_label = {}
    for t in ctx.parsed["traces"]:
        if t["label"] != "Dark":
            df_by_label.setdefault(t["label"], t["df"])

    rows = []
    for label in _wavelength_labels(ctx.parsed):
        ee = irr.get(label)
        i_light = _current_at(df_by_label.get(label), v_op)
        R = D = None
        if (ee is not None and ee > 0 and area_cm2 > 0
                and i_light is not None and i_dark_abs is not None):
            ee_w = float(ee) * 1e-3                      # mW/cm² → W/cm²
            i_ph = abs(i_light) - i_dark_abs             # I_ph = |I_light| − |I_dark|
            R = i_ph / (ee_w * area_cm2)                 # A / (W/cm² · cm²) = A/W
            if i_dark_abs > 0:
                # D* = R·√A / √(2·q·I_dark)  → cm·√Hz/W (Jones)
                D = R * math.sqrt(area_cm2) / math.sqrt(2.0 * _Q_ELECTRON * i_dark_abs)
        rows.append({"파장": label, "E_e": ee, "R": R, "D": D})
    return rows, i_dark_abs, v_op, area_cm2


def _fmt(x) -> str:
    return "N/A" if x is None else f"{x:.3e}"


# ---------------- 성능 지표 UI ----------------
def _metrics_inputs(ctx) -> None:
    fid = ctx.fid
    m = _metrics_of(ctx.settings)

    c1, c2, c3 = st.columns([1.2, 1.2, 1])
    m["v_op"] = c1.number_input(
        "동작전압 V_op (V)", value=float(m["v_op"]), step=0.1, format="%g",
        help="이 전압에서의 전류로 지표를 계산합니다 (역바이어스 관례: 기본 -1.0 V).",
        key=state.wkey("metrics", "v_op", fid=fid),
    )
    m["area"] = c2.number_input(
        "수광 면적 A", min_value=0.0, value=float(m["area"]), step=0.1, format="%g",
        key=state.wkey("metrics", "area", fid=fid),
    )
    _AREA_UNITS = ["cm2", "mm2"]
    cur_u = m["area_unit"] if m["area_unit"] in _AREA_UNITS else "cm2"
    m["area_unit"] = c3.selectbox(
        "면적 단위", _AREA_UNITS, index=_AREA_UNITS.index(cur_u),
        format_func=lambda u: {"cm2": "cm²", "mm2": "mm²"}[u],
        key=state.wkey("metrics", "area_unit", fid=fid),
    )

    labels = _wavelength_labels(ctx.parsed)
    if not labels:
        st.caption("파장 트레이스가 없어 광 조도 입력이 없습니다.")
        return
    st.caption("파장별 광 조도 E_e (mW/cm²) — 0 이면 해당 파장 지표는 N/A")
    irr = m["irradiance"]
    ncol = min(len(labels), 4)
    cols = st.columns(ncol)
    for idx, label in enumerate(labels):
        cur = irr.get(label)
        irr[label] = cols[idx % ncol].number_input(
            label, min_value=0.0,
            value=float(cur) if cur is not None else 0.0,
            step=0.1, format="%g",
            key=state.wkey("metrics", f"irr.{label}", fid=fid),
        )


def _metrics_table(ctx):
    """R/D 결과 표를 그리고 계산된 rows 를 반환 (내보내기가 재사용)."""
    rows, i_dark_abs, v_op, _ = _compute_metrics(ctx)
    if not rows:
        st.caption("파장 트레이스가 없어 지표를 계산할 수 없습니다.")
        return rows
    disp = pd.DataFrame([
        {"파장": r["파장"], "R [A/W]": _fmt(r["R"]), "D* [Jones]": _fmt(r["D"])}
        for r in rows
    ])
    st.dataframe(disp, width="stretch", hide_index=True,
                 height=min(38 + 35 * len(rows), 320))
    if i_dark_abs is None:
        st.caption("Dark 트레이스가 없거나 V_op 가 Dark 범위 밖이라 I_dark 를 구하지 못했습니다 "
                   "— R/D*가 N/A 입니다.")
    return rows


# ---------------- 내보내기 ----------------
def _export_html(fig) -> bytes:
    """figure → 자체 완결 HTML 바이트. V15: plotly.min.js 를 인라인(오프라인 대비)."""
    return fig.to_html(
        include_plotlyjs=True,
        full_html=True,
        div_id=_EXPORT_DIV_ID,
    ).encode("utf-8")


@st.cache_data(max_entries=2, show_spinner=False)
def _export_html_cached(_fig, sig: str) -> bytes:
    """`_fig` 는 밑줄 접두사라 해시 대상에서 빠진다 — 캐시 키는 `sig` 뿐이다."""
    return _export_html(_fig)


def _sig(ctx) -> str:
    """figure 를 결정하는 것 = fid + settings. 둘 다 같으면 HTML 도 같다."""
    return json.dumps([ctx.fid, ctx.settings], sort_keys=True, default=str)


def _stem(fid) -> str:
    """내보내기 파일명 = 업로드 파일명에서 확장자만 뗀 것 (레거시와 동일)."""
    f = state.S()["files"].get(fid) or {}
    return str(f.get("name", "graph")).rsplit(".", 1)[0] or "graph"


def _report_csv(ctx, metric_rows) -> bytes:
    """데이터 요약 + 성능 지표를 하나의 CSV 로. utf-8-sig 라 Excel 이 한글을 바로 연다."""
    m = _metrics_of(ctx.settings)
    buf = io.StringIO()
    buf.write("# Photodetector I-V Studio — report\n")
    buf.write(f"# file,{_stem(ctx.fid)}\n")
    buf.write(f"# V_op (V),{m['v_op']}\n")
    buf.write(f"# Area,{m['area']},{m['area_unit']}\n")
    buf.write(f"# Irradiance unit,{m.get('irr_unit', 'mW/cm2')}\n")

    buf.write("\n# Data summary\n")
    pd.DataFrame(_rows(ctx)).to_csv(buf, index=False)

    buf.write("\n# Performance metrics\n")
    mdf = pd.DataFrame([
        {"Wavelength": r["파장"],
         "E_e (mW/cm2)": r["E_e"],
         "R (A/W)": r["R"],
         "D* (Jones)": r["D"]}
        for r in metric_rows
    ])
    mdf.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8-sig")


def _export(ctx, metric_rows) -> None:
    """리포트 CSV(요약+지표) + 그래프 HTML 다운로드 + PNG 안내."""
    st.download_button(
        "요약·지표 CSV 다운로드",
        data=_report_csv(ctx, metric_rows),
        file_name=f"{_stem(ctx.fid)}_report.csv",
        mime="text/csv",
        width="stretch",
    )

    # PLAN §8.1: 화면 그래프는 미리보기 축소본이다. 내보내기는 px_scale 기본값(1.0)으로
    # **새로** 만든다 — 정확히 960×768 = 10×8in.
    try:
        fig = figure.build_figure(ctx.fid)
    except NotImplementedError:
        st.caption("figure 모듈(WP1)이 아직 준비 중이라 HTML 내보내기를 잠시 사용할 수 없습니다.")
        return

    st.download_button(
        "그래프 HTML 다운로드",
        data=_export_html_cached(fig, _sig(ctx)),
        file_name=f"{_stem(ctx.fid)}.html",
        mime="text/html",
        width="stretch",
    )

    w_in = float(ctx.settings["geom"]["page_w_in"])
    h_in = float(ctx.settings["geom"]["page_h_in"])
    st.caption(
        f"HTML 은 plotly.js 를 파일 안에 담아 **인터넷 없이도** 열립니다 (그래서 ~{_INLINE_MB:g}MB). · "
        f"PNG 는 그래프 우측 상단 모드바의 **카메라** 아이콘 (300dpi 상당, scale 3). · "
        f"둘 다 화면 미리보기 배율과 무관하게 정확히 **{w_in:g}×{h_in:g}인치**로 나갑니다."
    )


# ---------------- 진입점 ----------------
def render(ctx) -> None:
    """데이터 요약 ("데이터 요약" expander). Range I 경고 + 요약 표."""
    _range_i_warning(ctx.parsed)
    _table(ctx)


def render_metrics(ctx) -> None:
    """성능 지표 + 내보내기 ("성능 지표 · 내보내기" expander).

    입력 UI → 파장별 R/D* 결과 표 → 요약·지표 CSV + 그래프 HTML 내보내기.
    """
    _metrics_inputs(ctx)
    st.markdown("---")
    metric_rows = _metrics_table(ctx)
    _export(ctx, metric_rows)
