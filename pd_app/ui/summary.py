"""데이터 요약 + 성능 지표(Responsivity/Detectivity) + 내보내기. 소유: WP7."""

from __future__ import annotations

import copy
import io
import json
import math

import numpy as np
import pandas as pd
import streamlit as st

from pd_app import constants, figure, state

_Q_ELECTRON = 1.602e-19  # C


# ---------------- 데이터 요약 ----------------
def _range_i_warning(parsed) -> None:
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
        height=min(38 + 35 * len(rows), 230),
        column_config={
            "V min": st.column_config.NumberColumn(format="%.3g", width="small"),
            "V max": st.column_config.NumberColumn(format="%.3g", width="small"),
            "Points": st.column_config.NumberColumn(format="%d", width="small"),
        },
    )


# ---------------- 성능 지표 계산 ----------------
def _current_at(df, v_op):
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
        return None
    return float(np.interp(v_op, v, i))


def _dark_current_at(parsed, v_op):
    darks = [t["df"] for t in parsed["traces"]
             if t["label"] == "Dark" and t["df"] is not None and len(t["df"])]
    if not darks:
        return None
    cat = pd.concat(darks, ignore_index=True)
    i_dark = _current_at(cat, v_op)
    return None if i_dark is None else abs(i_dark)


def _metrics_of(settings):
    m = settings.setdefault("metrics", copy.deepcopy(constants.DEFAULTS["metrics"]))
    m.setdefault("v_op", -1.0)
    m.setdefault("area", 1.0)
    m.setdefault("area_unit", "cm2")
    if not isinstance(m.get("irradiance"), dict):
        m["irradiance"] = {}
    return m


def _wavelength_labels(parsed):
    out, seen = [], set()
    for t in parsed["traces"]:
        lb = t["label"]
        if lb == "Dark" or lb in seen:
            continue
        seen.add(lb)
        out.append(lb)
    return out


def _compute_metrics(ctx):
    rows, i_dark_abs, v_op, area_cm2 = [], None, -1.0, 1.0
    try:
        m = _metrics_of(ctx.settings)
        v_op = float(m["v_op"])
        area_cm2 = float(m["area"]) * (1e-2 if m["area_unit"] == "mm2" else 1.0)
        irr = m["irradiance"]
        i_dark_abs = _dark_current_at(ctx.parsed, v_op)

        df_by_label = {}
        for t in ctx.parsed["traces"]:
            if t["label"] != "Dark":
                df_by_label.setdefault(t["label"], t["df"])

        for label in _wavelength_labels(ctx.parsed):
            ee = irr.get(label)
            i_light = _current_at(df_by_label.get(label), v_op)
            R = D = None
            if (ee is not None and ee > 0 and area_cm2 > 0
                    and i_light is not None and i_dark_abs is not None):
                ee_w = float(ee) * 1e-3
                i_ph = abs(i_light) - i_dark_abs
                R = i_ph / (ee_w * area_cm2)
                if i_dark_abs > 0:
                    D = R * math.sqrt(area_cm2) / math.sqrt(2.0 * _Q_ELECTRON * i_dark_abs)
            rows.append({"파장": label, "E_e": ee, "R": R, "D": D})
    except Exception:
        pass
    return rows, i_dark_abs, v_op, area_cm2


def _fmt(x) -> str:
    return "N/A" if x is None else f"{x:.3e}"


def _metrics_inputs(ctx) -> None:
    fid = ctx.fid
    m = _metrics_of(ctx.settings)

    c1, c2, c3 = st.columns([1.2, 1.2, 1])
    m["v_op"] = c1.number_input(
        "동작전압 V_op (V)", value=float(m["v_op"]), step=0.1, format="%g",
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
        st.caption("Dark 트레이스가 없거나 V_op 가 Dark 범위 밖이라 I_dark 를 구하지 못했습니다 — R/D*가 N/A 입니다.")
    return rows


def _stem(fid) -> str:
    f = state.S()["files"].get(fid) or {}
    return str(f.get("name", "graph")).rsplit(".", 1)[0] or "graph"


def _report_csv(ctx, metric_rows) -> bytes:
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


# ---------------- 내보내기 ----------------
def _export(ctx, metric_rows) -> None:
    st.download_button(
        "📊 요약 · 지표 CSV 다운로드",
        data=_report_csv(ctx, metric_rows),
        file_name=f"{_stem(ctx.fid)}_report.csv",
        mime="text/csv",
        use_container_width=True
    )

    st.markdown("<br><b>이미지 내보내기 (출판용 고화질 300dpi)</b>", unsafe_allow_html=True)
    
    try:
        # =========================================================
        # 1. 완전 투명 PNG용 데이터 조립 (그래프 안/밖 및 인셋 투명화)
        # =========================================================
        png_settings = copy.deepcopy(ctx.settings)
        if "insets" in png_settings:
            if "legend" in png_settings["insets"]:
                png_settings["insets"]["legend"]["bg_opacity"] = 0.0
                png_settings["insets"]["legend"]["border"] = False
            if "sample" in png_settings["insets"]:
                png_settings["insets"]["sample"]["bg_opacity"] = 0.0
                png_settings["insets"]["sample"]["border"] = False
                
        original_settings = copy.deepcopy(ctx.settings)
        state.S()["files"][ctx.fid]["settings"] = png_settings
        
        export_fig_png = figure.build_figure(ctx.fid, px_scale=1.0)
        export_fig_png.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        export_json_png = export_fig_png.to_json().replace("</script>", "<\\/script>")

        # =========================================================
        # 2. 불투명 흰색 JPG용 데이터 조립 (원상 복구 후 생성)
        # =========================================================
        state.S()["files"][ctx.fid]["settings"] = original_settings
        
        export_fig_jpg = figure.build_figure(ctx.fid, px_scale=1.0)
        export_fig_jpg.update_layout(paper_bgcolor="white", plot_bgcolor="white")
        export_json_jpg = export_fig_jpg.to_json().replace("</script>", "<\\/script>")
        
    except Exception as e:
        st.error("내보내기 데이터 준비 중 오류가 발생했습니다.")
        state.S()["files"][ctx.fid]["settings"] = original_settings
        return

    c_png, c_jpg = st.columns(2)
    stem_name = _stem(ctx.fid)
    accent_color = "#ed542b"

    btn_style = (
        "width:100%; height:38px; margin:0; padding:0; "
        "background-color:rgb(255, 255, 255); color:rgb(49, 51, 63); "
        "border:1px solid rgba(49, 51, 63, 0.2); border-radius:0.5rem; "
        "cursor:pointer; font-size:14px; font-weight:400; "
        "font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; "
        "display:inline-flex; align-items:center; justify-content:center; "
        "transition: border-color 0.15s ease, color 0.15s ease; box-sizing:border-box;"
    )
    
    on_hover = f"this.style.borderColor='{accent_color}'; this.style.color='{accent_color}';"
    on_leave = "this.style.borderColor='rgba(49, 51, 63, 0.2)'; this.style.color='rgb(49, 51, 63)';"

    with c_png:
        # 💡 [핵심 해결] iframe 탐색 코드를 완전 삭제! 이제 버튼 자체가 Plotly.js를 들고 직접 그려서 뽑아냅니다.
        png_html = f"""
        <html>
        <head><script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script></head>
        <body style="margin:0; padding:0; background:transparent; overflow:hidden;">
        <button id="btn-png" style="{btn_style}" onmouseover="{on_hover}" onmouseout="{on_leave}">
        🖼️ PNG (완전 투명) 다운로드
        </button>
        <script>
        document.getElementById('btn-png').addEventListener('click', function() {{
            if (typeof Plotly === 'undefined') {{
                alert('이미지 생성 엔진 로딩 중입니다. 1~2초 뒤 다시 클릭해주세요.');
                return;
            }}
            var tempDiv = document.createElement('div');
            tempDiv.style.position = 'absolute';
            tempDiv.style.left = '-9999px';
            tempDiv.style.width = '960px';
            tempDiv.style.height = '768px';
            document.body.appendChild(tempDiv);
            
            var figData = {export_json_png};
            
            Plotly.newPlot(tempDiv, figData.data, figData.layout).then(function() {{
                Plotly.downloadImage(tempDiv, {{format: 'png', width: 960, height: 768, scale: 3, filename: '{stem_name}'}}).then(function() {{
                    document.body.removeChild(tempDiv);
                }});
            }});
        }});
        </script>
        </body>
        </html>
        """
        st.components.v1.html(png_html, height=40)

    with c_jpg:
        # 💡 [핵심 해결] JPG 다운로드 버튼도 마찬가지로 완벽히 격리된 자체 엔진으로 렌더링.
        jpg_html = f"""
        <html>
        <head><script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script></head>
        <body style="margin:0; padding:0; background:transparent; overflow:hidden;">
        <button id="btn-jpg" style="{btn_style}" onmouseover="{on_hover}" onmouseout="{on_leave}">
        📷 JPG (흰색 배경) 다운로드
        </button>
        <script>
        document.getElementById('btn-jpg').addEventListener('click', function() {{
            if (typeof Plotly === 'undefined') {{
                alert('이미지 생성 엔진 로딩 중입니다. 1~2초 뒤 다시 클릭해주세요.');
                return;
            }}
            var tempDiv = document.createElement('div');
            tempDiv.style.position = 'absolute';
            tempDiv.style.left = '-9999px';
            tempDiv.style.width = '960px';
            tempDiv.style.height = '768px';
            document.body.appendChild(tempDiv);
            
            var figData = {export_json_jpg};
            
            Plotly.newPlot(tempDiv, figData.data, figData.layout).then(function() {{
                Plotly.downloadImage(tempDiv, {{format: 'jpeg', width: 960, height: 768, scale: 3, filename: '{stem_name}'}}).then(function() {{
                    document.body.removeChild(tempDiv);
                }});
            }});
        }});
        </script>
        </body>
        </html>
        """
        st.components.v1.html(jpg_html, height=40)

    w_in = float(ctx.settings["geom"]["page_w_in"])
    h_in = float(ctx.settings["geom"]["page_h_in"])
    st.caption(
        f"※ **출력 해상도 정보**: 화면 미리보기 배율과 무관하게, 연구실 설정에 명시된 "
        f"네이티브 **{w_in:g}×{h_in:g} 인치** 크기를 정확히 유지한 채 **3배 고화질 스케일(300 dpi 상당)**로 영구 추출됩니다."
    )


# ---------------- 진입점 ----------------
def render(ctx) -> None:
    _range_i_warning(ctx.parsed)
    _table(ctx)


def render_metrics(ctx) -> None:
    _metrics_inputs(ctx)
    st.markdown("---")
    metric_rows = _metrics_table(ctx)
    _export(ctx, metric_rows)