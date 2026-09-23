"""데이터 요약 + 성능 지표(Responsivity/Detectivity) + 내보내기. 소유: WP7.

ctx = SimpleNamespace(fid, settings, traces, parsed, fig_px, domains)
"""

from __future__ import annotations

import copy
import io
import json
import math

import numpy as np
import pandas as pd
import streamlit as st

from pd_app import constants, figure, postproc, state

_Q_ELECTRON = 1.602e-19  # C

# 내보낸 엑셀의 Info 시트에 기계가 읽을 설정을 담는 행 이름.
# parsing._parse_exported() 가 같은 이름을 찾는다 — 바꾸면 양쪽을 같이 바꿀 것.
_SETTINGS_KEY = "Settings (JSON) — 다시 불러오기용"


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
    """V_op 의 암전류를 **부호 그대로** 반환.

    광전류는 부호 있는 차(I_light - I_dark)의 절댓값으로 구해야 두 전류의 부호가
    갈리는 구간에서도 값이 맞는다. D* 분모에 쓸 때만 호출부에서 abs() 를 취한다.
    """
    darks = [t["df"] for t in parsed["traces"]
             if t["label"] == "Dark" and t["df"] is not None and len(t["df"])]
    if not darks:
        return None
    cat = pd.concat(darks, ignore_index=True)
    return _current_at(cat, v_op)


def _metrics_of(settings):
    m = settings.setdefault("metrics", copy.deepcopy(constants.DEFAULTS["metrics"]))
    m.setdefault("v_op1", -1.0)
    m.setdefault("v_op2", 1.0)
    m.setdefault("area", 0.031416)
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
    """V_op1, V_op2 두 전압에서의 파장별 R, D* 동시 계산."""
    rows, i_dark1, i_dark2 = [], None, None
    v_op1, v_op2, area_cm2 = -1.0, 1.0, 1.0
    try:
        m = _metrics_of(ctx.settings)
        v_op1 = float(m.get("v_op1", -1.0))
        v_op2 = float(m.get("v_op2", 1.0))
        area_cm2 = float(m["area"]) * (1e-2 if m["area_unit"] == "mm2" else 1.0)
        irr = m["irradiance"]

        i_dark1 = _dark_current_at(ctx.parsed, v_op1)
        i_dark2 = _dark_current_at(ctx.parsed, v_op2)

        df_by_label = {}
        for t in ctx.parsed["traces"]:
            if t["label"] != "Dark":
                df_by_label.setdefault(t["label"], t["df"])

        for label in _wavelength_labels(ctx.parsed):
            ee = irr.get(label)
            i_light1 = _current_at(df_by_label.get(label), v_op1)
            i_light2 = _current_at(df_by_label.get(label), v_op2)

            R1 = D1 = R2 = D2 = None
            if ee is not None and ee > 0 and area_cm2 > 0:
                ee_w = float(ee) * 1e-3  # mW/cm² → W/cm²

                # V_op1 계산 (-1V 기본)
                if i_light1 is not None and i_dark1 is not None:
                    # 광전류 = 같은 바이어스에서의 (광 - 암) 차. 절댓값의 차가 아니라
                    # 차의 절댓값이어야 두 전류의 부호가 갈려도 크기가 맞는다. R 은 항상 양수.
                    i_ph1 = abs(i_light1 - i_dark1)
                    R1 = i_ph1 / (ee_w * area_cm2)
                    if abs(i_dark1) > 0:
                        D1 = R1 * math.sqrt(area_cm2) / math.sqrt(2.0 * _Q_ELECTRON * abs(i_dark1))

                # V_op2 계산 (+1V 기본)
                if i_light2 is not None and i_dark2 is not None:
                    i_ph2 = abs(i_light2 - i_dark2)
                    R2 = i_ph2 / (ee_w * area_cm2)
                    if abs(i_dark2) > 0:
                        D2 = R2 * math.sqrt(area_cm2) / math.sqrt(2.0 * _Q_ELECTRON * abs(i_dark2))

            rows.append({
                "파장": label,
                "E_e": ee,
                "R_v1": R1, "D_v1": D1,
                "R_v2": R2, "D_v2": D2
            })
    except Exception:
        pass
    return rows, i_dark1, i_dark2, v_op1, v_op2, area_cm2


def _fmt(x) -> str:
    return "N/A" if x is None else f"{x:.3e}"


def _metrics_inputs(ctx) -> None:
    fid = ctx.fid
    m = _metrics_of(ctx.settings)

    c1, c2, c3, c4 = st.columns([1, 1, 1.2, 1])
    m["v_op1"] = c1.number_input(
        "동작전압 V_op1 (V)", value=float(m.get("v_op1", -1.0)), step=0.1, format="%g",
        key=state.wkey("metrics", "v_op1", fid=fid),
    )
    m["v_op2"] = c2.number_input(
        "동작전압 V_op2 (V)", value=float(m.get("v_op2", 1.0)), step=0.1, format="%g",
        key=state.wkey("metrics", "v_op2", fid=fid),
    )
    # 소수점 미세 조정을 위해 step을 0.001 로 세밀하게 설정했습니다.
    m["area"] = c3.number_input(
        "수광 면적 A", min_value=0.0, value=float(m["area"]), step=0.001, format="%g",
        key=state.wkey("metrics", "area", fid=fid),
    )
    _AREA_UNITS = ["cm2", "mm2"]
    cur_u = m["area_unit"] if m["area_unit"] in _AREA_UNITS else "cm2"
    m["area_unit"] = c4.selectbox(
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
    rows, i_dark1, i_dark2, v_op1, v_op2, _ = _compute_metrics(ctx)
    if not rows:
        st.caption("파장 트레이스가 없어 지표를 계산할 수 없습니다.")
        return rows

    v1_str = f"{v_op1:g}V"
    v2_str = f"{v_op2:g}V"

    disp = pd.DataFrame([
        {
            "파장": r["파장"],
            f"R ({v1_str}) [A/W]": _fmt(r["R_v1"]),
            f"D* ({v1_str}) [Jones]": _fmt(r["D_v1"]),
            f"R ({v2_str}) [A/W]": _fmt(r["R_v2"]),
            f"D* ({v2_str}) [Jones]": _fmt(r["D_v2"]),
        }
        for r in rows
    ])
    st.dataframe(disp, width="stretch", hide_index=True,
                 height=min(38 + 35 * len(rows), 320))
    if i_dark1 is None or i_dark2 is None:
        st.caption("Dark 트레이스가 없거나 설정 전압이 범위 밖이라 일부 전압의 I_dark 를 구하지 못했습니다 — 해당 지표는 N/A 입니다.")
    return rows


def _stem(fid) -> str:
    f = state.S()["files"].get(fid) or {}
    return str(f.get("name", "graph")).rsplit(".", 1)[0] or "graph"


# 파장 정렬 기준. SYMBOL_MAP 은 d,8,7,6,5,4,3,2,1 순(= 940→365 내림차순)이라
# 그 값 순서가 곧 데이터셋 시트의 열 순서다. 측정 순서(파일명 대괄호)가 달라도
# 붙여넣기 블록의 열 순서는 항상 이 기준을 따라야 열이 어긋나지 않는다.
_WL_ORDER = [v for v in constants.SYMBOL_MAP.values() if v != "Dark"]


def _sorted_wavelengths(labels) -> list:
    rank = {w: i for i, w in enumerate(_WL_ORDER)}
    return sorted(labels, key=lambda lb: (rank.get(lb, 999), str(lb)))


def _write_paste_block(buf, metric_rows, v1_lab: str, v2_lab: str) -> None:
    """데이터셋 시트에 바로 붙여넣을 수 있는 가로 배치 블록 (Responsivity 만).

    A: 파장 = 열, 바이어스 = 행 (2행)  — 각 행을 따로 붙여넣을 때
    B: 한 행에 12개 값                  — Data 시트 D~O 열에 한 번에 붙여넣을 때
    """
    by = {r["파장"]: r for r in metric_rows}
    labels = _sorted_wavelengths(by.keys())
    if not labels:
        return

    def cell(lb, key):
        v = by[lb].get(key)
        return "" if v is None else f"{v:.6e}"

    buf.write("\n# Paste-ready A — Responsivity (A/W) · 파장=열, 바이어스=행\n")
    buf.write("," + ",".join(labels) + "\n")
    for lab, key in ((v1_lab, "R_v1"), (v2_lab, "R_v2")):
        buf.write(f"R({lab})," + ",".join(cell(lb, key) for lb in labels) + "\n")

    # 데이터셋 시트(Data)의 R 열은 R(-1 V)_940 … R(+1 V)_470 순의 한 행이다.
    heads, vals = [], []
    for lab, key in ((v1_lab, "R_v1"), (v2_lab, "R_v2")):
        for lb in labels:
            heads.append(f"R({lab})_{str(lb).split()[0]}")
            vals.append(cell(lb, key))
    buf.write("\n# Paste-ready B — 위 열 순서 그대로 한 행 (Data 시트 R 열 구간에 한 번에)\n")
    buf.write(",".join(heads) + "\n")
    buf.write(",".join(vals) + "\n")


def _write_report(buf, ctx, metric_rows, *, include_summary=True) -> None:
    """한 파일의 리포트 본문을 buf 에 기록 (단일·일괄 내보내기 공용)."""
    m = _metrics_of(ctx.settings)
    buf.write(f"# file,{_stem(ctx.fid)}\n")
    buf.write(f"# V_op1 (V),{m.get('v_op1', -1.0)}\n")
    buf.write(f"# V_op2 (V),{m.get('v_op2', 1.0)}\n")
    buf.write(f"# Area,{m['area']},{m['area_unit']}\n")
    buf.write(f"# Irradiance unit,{m.get('irr_unit', 'mW/cm2')}\n")

    if include_summary:
        buf.write("\n# Data summary\n")
        pd.DataFrame(_rows(ctx)).to_csv(buf, index=False)

    v1_str = f"{m.get('v_op1', -1.0):g}V"
    v2_str = f"{m.get('v_op2', 1.0):g}V"

    buf.write("\n# Performance metrics\n")
    mdf = pd.DataFrame([
        {
            "Wavelength": r["파장"],
            "E_e (mW/cm2)": r["E_e"],
            f"R_{v1_str} (A/W)": r["R_v1"],
            f"D*_{v1_str} (Jones)": r["D_v1"],
            f"R_{v2_str} (A/W)": r["R_v2"],
            f"D*_{v2_str} (Jones)": r["D_v2"]
        }
        for r in metric_rows
    ])
    mdf.to_csv(buf, index=False)

    # 데이터셋 시트 붙여넣기용 가로 배치. 바이어스 라벨은 목표 시트 헤더와 같은
    # 표기를 쓴다 — 양수에도 부호를 붙여야 R(+1 V)_940 과 정확히 일치한다.
    _write_paste_block(buf, metric_rows,
                       f"{m.get('v_op1', -1.0):+g} V", f"{m.get('v_op2', 1.0):+g} V")


def _report_csv(ctx, metric_rows) -> bytes:
    buf = io.StringIO()
    buf.write("# Photodetector I-V Studio — report\n")
    _write_report(buf, ctx, metric_rows)
    return buf.getvalue().encode("utf-8-sig")


def _bulk_report_csv(ctxs) -> bytes:
    """열려 있는 모든 파일의 리포트를 하나의 CSV 로 이어붙인다."""
    buf = io.StringIO()
    buf.write(f"# Photodetector I-V Studio — bulk report ({len(ctxs)} files)\n")
    for i, ctx in enumerate(ctxs):
        buf.write("\n\n" if i else "\n")
        rows, *_ = _compute_metrics(ctx)
        _write_report(buf, ctx, rows, include_summary=False)
    return buf.getvalue().encode("utf-8-sig")


# ---------------- 이미지 내보내기 공용 ----------------
_BTN_STYLE = (
    "width:100%; height:38px; margin:0; padding:0; "
    "background-color:rgb(255, 255, 255); color:rgb(49, 51, 63); "
    "border:1px solid rgba(49, 51, 63, 0.2); border-radius:0.5rem; "
    "cursor:pointer; font-size:14px; font-weight:400; "
    "font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; "
    "display:inline-flex; align-items:center; justify-content:center; "
    "transition: border-color 0.15s ease, color 0.15s ease; box-sizing:border-box;"
)
_BTN_HOVER = "this.style.borderColor='#ed542b'; this.style.color='#ed542b';"
_BTN_LEAVE = "this.style.borderColor='rgba(49, 51, 63, 0.2)'; this.style.color='rgb(49, 51, 63)';"


def _fig_json(ctx, *, transparent: bool) -> str:
    """ctx 파일의 그림을 내보내기용 JSON 문자열로. transparent=투명 PNG용, False=흰 배경 JPG용."""
    if transparent:
        stored = state.S()["files"][ctx.fid]["settings"]
        png_settings = copy.deepcopy(ctx.settings)
        ins = png_settings.get("insets", {})
        if "legend" in ins:
            ins["legend"]["bg_opacity"] = 0.0
            ins["legend"]["border"] = False
        if "sample" in ins:
            ins["sample"]["bg_opacity"] = 0.0
            ins["sample"]["border"] = False
        state.S()["files"][ctx.fid]["settings"] = png_settings
        try:
            fig = figure.build_figure(ctx.fid, px_scale=1.0)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            return fig.to_json().replace("</script>", "<\\/script>")
        finally:
            state.S()["files"][ctx.fid]["settings"] = stored
    fig = figure.build_figure(ctx.fid, px_scale=1.0)
    fig.update_layout(paper_bgcolor="white", plot_bgcolor="white")
    return fig.to_json().replace("</script>", "<\\/script>")


def _bulk_image_html(items, fmt: str, btn_id: str, label: str) -> str:
    """items=[(filename, fig_json), ...] 를 클릭 시 순차 다운로드하는 버튼 HTML."""
    entries = ",\n".join(f"{{name: {json.dumps(name)}, fig: {fig}}}" for name, fig in items)
    return f"""
    <html>
    <head><script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script></head>
    <body style="margin:0; padding:0; background:transparent; overflow:hidden;">
    <button id="{btn_id}" style="{_BTN_STYLE}"
            onmouseover="{_BTN_HOVER}" onmouseout="{_BTN_LEAVE}">{label}</button>
    <script>
    var FIGS = [{entries}];
    document.getElementById('{btn_id}').addEventListener('click', async function() {{
        if (typeof Plotly === 'undefined') {{
            alert('이미지 생성 엔진 로딩 중입니다. 1~2초 뒤 다시 클릭해주세요.');
            return;
        }}
        var btn = this; btn.disabled = true; var orig = btn.textContent;
        for (var i = 0; i < FIGS.length; i++) {{
            btn.textContent = '내보내는 중… (' + (i + 1) + '/' + FIGS.length + ')';
            var item = FIGS[i];
            var d = document.createElement('div');
            d.style.position = 'absolute'; d.style.left = '-9999px';
            d.style.width = '960px'; d.style.height = '768px';
            document.body.appendChild(d);
            await Plotly.newPlot(d, item.fig.data, item.fig.layout);
            await Plotly.downloadImage(d, {{format: '{fmt}', width: 960, height: 768, scale: 3, filename: item.name}});
            document.body.removeChild(d);
            await new Promise(function(r) {{ setTimeout(r, 700); }});
        }}
        btn.textContent = orig; btn.disabled = false;
    }});
    </script>
    </body>
    </html>
    """


def render_bulk_export(ctxs) -> None:
    """열려 있는 모든 파일 일괄 내보내기 — 성능지표 CSV 1개 + PNG/JPG 개별 다운로드 버튼 (세로 배치)."""
    if len(ctxs) < 2:
        return
    st.caption(f"🗂 전체 {len(ctxs)}개 파일 일괄 내보내기")

    st.download_button(
        "📊 성능지표 일괄 CSV",
        data=_bulk_report_csv(ctxs),
        file_name="photodetector_bulk_report.csv",
        mime="text/csv",
        use_container_width=True,
        key="pd_bulk_csv",
    )

    png_items, jpg_items = [], []
    for ctx in ctxs:
        stem = _stem(ctx.fid)
        try:
            png_items.append((stem, _fig_json(ctx, transparent=True)))
            jpg_items.append((stem, _fig_json(ctx, transparent=False)))
        except Exception:
            continue

    st.components.v1.html(
        _bulk_image_html(png_items, "png", "btn-bulk-png",
                         f"🖼️ 일괄 PNG (투명) · {len(png_items)}개"),
        height=46,
    )
    st.components.v1.html(
        _bulk_image_html(jpg_items, "jpeg", "btn-bulk-jpg",
                         f"📷 일괄 JPG (흰 배경) · {len(jpg_items)}개"),
        height=46,
    )
    st.caption("이미지는 파일마다 개별 저장됩니다. 브라우저가 다중 다운로드를 물으면 허용하세요.")


# ---------------- 내보내기 ----------------
def _image_button_html(fig_json: str, fmt: str, btn_id: str, label: str, stem: str) -> str:
    """단일 파일 이미지 다운로드 버튼 HTML (일괄용 _bulk_image_html 과 같은 스타일)."""
    return f"""
    <html>
    <head><script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script></head>
    <body style="margin:0; padding:0; background:transparent; overflow:hidden;">
    <button id="{btn_id}" style="{_BTN_STYLE}"
            onmouseover="{_BTN_HOVER}" onmouseout="{_BTN_LEAVE}">{label}</button>
    <script>
    document.getElementById('{btn_id}').addEventListener('click', function() {{
        if (typeof Plotly === 'undefined') {{
            alert('이미지 생성 엔진 로딩 중입니다. 1~2초 뒤 다시 클릭해주세요.');
            return;
        }}
        var d = document.createElement('div');
        d.style.position = 'absolute'; d.style.left = '-9999px';
        d.style.width = '960px'; d.style.height = '768px';
        document.body.appendChild(d);
        var fig = {fig_json};
        Plotly.newPlot(d, fig.data, fig.layout).then(function() {{
            Plotly.downloadImage(d, {{format: '{fmt}', width: 960, height: 768, scale: 3,
                                      filename: {json.dumps(stem)}}}).then(function() {{
                document.body.removeChild(d);
            }});
        }});
    }});
    </script>
    </body>
    </html>
    """


# ---------------- 엑셀 내보내기 (Origin 편집용) ----------------
def _export_traces(ctx) -> list[dict]:
    """내보낼 트레이스 목록. Dark 먼저, 그 다음 파장 내림차순(940→365). 같은 라벨은
    측정 순서대로 #2, #3 … 을 붙인다. 각 항목: name, label, df, visible, range_i.
    """
    rank = {w: i for i, w in enumerate(_WL_ORDER)}
    seen: dict[str, int] = {}
    items = []
    for idx, t in enumerate(ctx.parsed["traces"]):
        lb = t["label"]
        seen[lb] = seen.get(lb, 0) + 1
        occ = seen[lb]
        ts = ctx.traces.get(state.tkey_of(t, occ)) or {}
        items.append({
            "idx": idx,                      # postproc.process 결과와 짝 맞추는 키
            "name": lb if occ == 1 else f"{lb} #{occ}",
            "label": lb,
            "df": t["df"],
            "visible": bool(ts.get("visible", True)),
            "range_i": t.get("range_i", ""),
            "_key": (-1 if lb == "Dark" else rank.get(lb, 999), idx),
        })
    items.sort(key=lambda it: it["_key"])
    return items


def _same_x(a, b) -> bool:
    """두 스윕이 같은 X 축을 쓰는가.

    허용오차는 **스텝 크기의 5%**. 장비가 매 스윕 실측 전압을 기록하면 같은 설정이어도
    µV 수준으로 흔들린다 (실측: 신형 Keithley 산출물에서 파장 간 최대 3µV 차이,
    스텝은 0.01V — 0.03%). 고정 허용오차로는 이걸 다른 축으로 오판한다.
    """
    if len(a) != len(b) or len(a) < 2:
        return False
    step = float(np.median(np.abs(np.diff(a))))
    tol = max(step * 0.05, 1e-9)
    d = np.abs(a - b)
    return bool(np.all(np.isnan(d) | (d <= tol)))


def _write_xy_sheet(ws, items, source, *, y_suffix: str = "") -> str:
    """X 가 같은 트레이스끼리 **X 열 하나를 공유**하도록 쓴다.

    배치는 [X][Y][Y]…[X][Y]… — Origin 이 "왼쪽 X 를 오른쪽 Y 들이 공유"로 읽는
    바로 그 관례다. 파장마다 X 를 반복하면 Origin 에서 매번 열 지정을 다시 해야 해서
    불편하다는 요청에 따른 배치다.

    1행 = Long Name, 2행 = Units. 3행부터 데이터. 점 개수가 다른 조각(Dark 0→-1V /
    0→+1V 처럼)은 자연히 별도 X 그룹이 된다.
    `source(item) -> (v, i)` 가 어떤 단계의 값을 쓸지 정한다.
    반환값은 X 공유 시 생긴 최대 X 편차 요약 (없으면 빈 문자열).
    """
    from openpyxl.styles import Font, Alignment
    from openpyxl.utils import get_column_letter

    # --- X 가 같은 것끼리 묶기 ---
    groups: list[dict] = []
    max_dev = 0.0
    for it in items:
        v, i = source(it)
        v = np.asarray(v, dtype=float)
        i = np.asarray(i, dtype=float)
        g = next((g for g in groups if _same_x(g["v"], v)), None)
        if g is None:
            groups.append({"v": v, "cols": [(it["name"], i)]})
        else:
            d = np.abs(g["v"] - v)
            if np.isfinite(d).any():
                max_dev = max(max_dev, float(np.nanmax(d)))
            g["cols"].append((it["name"], i))

    bold = Font(bold=True)
    center = Alignment(horizontal="center")

    def put(col, title, unit, arr):
        c = ws.cell(row=1, column=col, value=title); c.font = bold; c.alignment = center
        c = ws.cell(row=2, column=col, value=unit); c.alignment = center
        for r, val in enumerate(arr, start=3):
            ws.cell(row=r, column=col,
                    value=(None if not np.isfinite(val) else float(val)))
        ws.column_dimensions[get_column_letter(col)].width = 16

    col = 1
    for g in groups:
        put(col, "Voltage", "V", g["v"])
        col += 1
        for name, arr in g["cols"]:
            put(col, f"{name}{y_suffix}", "A", arr)
            col += 1
    ws.freeze_panes = "A3"
    return (f"{max_dev:.3e} V" if max_dev > 0 else "")


def _excel_bytes(ctx, metric_rows) -> bytes:
    """Origin 에서 바로 열어 편집할 수 있는 .xlsx.

    Raw        원본 AnodeV / AnodeI 전 트레이스 (후처리·오프셋 전혀 없음, **항상 부호 유지**)
    Processed  후처리(이어붙이기·스무딩) 적용 — 기본은 |I| (export_abs)
    Plot       그래프에 그려진 값 그대로 (Processed + 0V 오프셋 + |I|, 숨긴 것 제외)
    Metrics    성능지표 표 + 데이터셋 붙여넣기 블록  ※ 지표는 **항상 Raw** 기준
    Info       파일·샘플·측정 조건·후처리 설정·Range I

    Origin 로그축에 바로 올릴 수 있도록 Processed·Plot 은 기본이 |I| 다. Raw 만은
    부호를 지킨다 — 부호가 필요하면 Raw 에서 가져오면 된다.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font

    settings = ctx.settings
    parsed = ctx.parsed
    m = _metrics_of(settings)
    items = _export_traces(ctx)

    # 그래프와 동일한 변환 (figure.build_figure 의 규칙을 그대로 따른다)
    is_log = settings["axes"]["y"].get("type", "log") == "log"
    use_abs = True if is_log else bool(settings.get("use_abs", False))
    i_off = float(parsed.get("i_offset") or 0.0) if settings.get("dark_offset") else 0.0
    proc = postproc.process(parsed, settings)

    def raw_src(it):
        df = it["df"]
        return df["AnodeV"].to_numpy(dtype=float), df["AnodeI"].to_numpy(dtype=float)

    # Origin 로그축에 바로 올리려면 양수여야 한다. Raw 는 예외 — 원본 보존이 역할이다.
    exp_abs = bool(settings.get("export_abs", True))
    suffix = " |I|" if exp_abs else ""

    def proc_src(it):
        v, i = proc[it["idx"]]
        return v, (np.abs(i) if exp_abs else i)

    def plot_src(it):
        return figure._series_xy(*proc[it["idx"]], use_abs or exp_abs, i_off)

    wb = Workbook()

    ws = wb.active; ws.title = "Raw"
    x_dev = _write_xy_sheet(ws, items, raw_src)

    ws = wb.create_sheet("Processed")
    _write_xy_sheet(ws, items, proc_src, y_suffix=suffix)

    ws = wb.create_sheet("Plot")
    _write_xy_sheet(ws, [it for it in items if it["visible"]], plot_src,
                    y_suffix=" |I|" if (use_abs or exp_abs) else "")

    # --- Metrics ---
    ws = wb.create_sheet("Metrics")
    bold = Font(bold=True)
    v1_lab = f"{m.get('v_op1', -1.0):+g} V"
    v2_lab = f"{m.get('v_op2', 1.0):+g} V"
    heads = ["Wavelength", "E_e (mW/cm2)",
             f"R({v1_lab}) (A/W)", f"D*({v1_lab}) (Jones)",
             f"R({v2_lab}) (A/W)", f"D*({v2_lab}) (Jones)"]
    for j, h in enumerate(heads, start=1):
        ws.cell(row=1, column=j, value=h).font = bold
    for r, row in enumerate(metric_rows, start=2):
        ws.cell(row=r, column=1, value=row["파장"])
        ws.cell(row=r, column=2, value=row["E_e"])
        for j, k in enumerate(("R_v1", "D_v1", "R_v2", "D_v2"), start=3):
            ws.cell(row=r, column=j, value=row[k])

    # 붙여넣기 블록 (CSV 의 Paste-ready 와 동일)
    by = {r["파장"]: r for r in metric_rows}
    labels = _sorted_wavelengths(by.keys())
    r0 = len(metric_rows) + 4
    ws.cell(row=r0, column=1, value="Paste-ready A — 파장=열, 바이어스=행").font = bold
    for j, lb in enumerate(labels, start=2):
        ws.cell(row=r0 + 1, column=j, value=lb).font = bold
    for k, (lab, key) in enumerate(((v1_lab, "R_v1"), (v2_lab, "R_v2"))):
        ws.cell(row=r0 + 2 + k, column=1, value=f"R({lab})").font = bold
        for j, lb in enumerate(labels, start=2):
            ws.cell(row=r0 + 2 + k, column=j, value=by[lb].get(key))
    r1 = r0 + 6
    ws.cell(row=r1, column=1, value="Paste-ready B — 한 행 (Data 시트 R 열 구간)").font = bold
    j = 1
    for lab, key in ((v1_lab, "R_v1"), (v2_lab, "R_v2")):
        for lb in labels:
            ws.cell(row=r1 + 1, column=j, value=f"R({lab})_{str(lb).split()[0]}").font = bold
            ws.cell(row=r1 + 2, column=j, value=by[lb].get(key))
            j += 1
    for c in range(1, 14):
        ws.column_dimensions[ws.cell(row=1, column=c).column_letter].width = 18

    # --- Info ---
    ws = wb.create_sheet("Info")
    f = state.S()["files"].get(ctx.fid) or {}
    info = [
        ("File", f.get("name", "")),
        ("Sample", settings["insets"]["sample"].get("text_raw", "")),
        ("V_op1 (V)", m.get("v_op1", -1.0)),
        ("V_op2 (V)", m.get("v_op2", 1.0)),
        ("Area", m["area"]),
        ("Area unit", m["area_unit"]),
        ("Irradiance unit", m.get("irr_unit", "mW/cm2")),
        ("Y axis", "log |I|" if is_log else "linear"),
        ("Dark 0V offset applied to Plot", bool(settings.get("dark_offset"))),
        ("Dark 0V offset value (A)", parsed.get("i_offset")),
        ("Post-processing (Processed·Plot)", postproc.describe(settings)),
        ("Export as |I| (Processed·Plot)", exp_abs),
        ("Raw sheet sign", "부호 유지 (항상)"),
        ("Metrics computed from", "Raw (후처리·오프셋 미적용)"),
        # X 를 공유시키면 그룹 대표 X 를 쓰므로, 스윕 간 실측 전압 차이가 있었다면 남긴다.
        ("Shared-X max deviation", x_dev or "0 (완전 일치)"),
        # 위 'Post-processing' 은 사람이 읽는 요약이라 되돌려 읽을 수 없다. 이 파일을
        # 앱에 다시 올렸을 때 보정 설정을 그대로 복원하려고 기계가 읽을 형태로 한 번 더 적는다.
        (_SETTINGS_KEY, json.dumps({
            "dark_offset": bool(settings.get("dark_offset")),
            "export_abs": exp_abs,
            "postproc": postproc.cfg(settings),
            "use_abs": bool(settings.get("use_abs", True)),
            "metrics": {"v_op1": m.get("v_op1", -1.0), "v_op2": m.get("v_op2", 1.0),
                        "area": m["area"], "area_unit": m["area_unit"],
                        "irradiance": dict(m["irradiance"])},
            "visible": {it["name"]: it["visible"] for it in items},
            "range_i": {it["name"]: it["range_i"] for it in items},
        }, ensure_ascii=False)),
    ]
    for r, (k, v) in enumerate(info, start=1):
        ws.cell(row=r, column=1, value=k).font = bold
        ws.cell(row=r, column=2, value=v)
    r = len(info) + 2
    ws.cell(row=r, column=1, value="E_e per wavelength (mW/cm2)").font = bold
    for lb in _sorted_wavelengths(m["irradiance"].keys()):
        r += 1
        ws.cell(row=r, column=1, value=lb); ws.cell(row=r, column=2, value=m["irradiance"][lb])
    r += 2
    ws.cell(row=r, column=1, value="Trace").font = bold
    ws.cell(row=r, column=2, value="Range I").font = bold
    ws.cell(row=r, column=3, value="Points").font = bold
    ws.cell(row=r, column=4, value="Visible").font = bold
    for it in items:
        r += 1
        ws.cell(row=r, column=1, value=it["name"])
        ws.cell(row=r, column=2, value=it["range_i"])
        ws.cell(row=r, column=3, value=int(len(it["df"])))
        ws.cell(row=r, column=4, value=it["visible"])
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 22

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------- 진입점 ----------------
def render(ctx) -> None:
    _range_i_warning(ctx.parsed)
    _table(ctx)


def render_metrics(ctx) -> None:
    """[성능 지표] 익스팬더 — 입력 + 표. 내보내기 버튼은 좌측 [내보내기] 탭으로 옮겼다."""
    _metrics_inputs(ctx)
    st.markdown("---")
    _metrics_table(ctx)


def render_export(ctx) -> None:
    """좌측 편집 패널 [내보내기] 탭 — 현재 파일 하나의 개별 내보내기.

    ⚠️ 반드시 render_metrics(성능 지표 위젯) **뒤**에 호출할 것. 이 함수는
    settings["metrics"] 를 읽는데, 위젯이 값을 써넣는 건 render_metrics 안이다.
    앞에 두면 V_op·면적·E_e 를 바꾼 첫 run 에서 한 run 늦은 값으로 파일이 만들어진다.
    """
    stem = _stem(ctx.fid)
    rows, *_ = _compute_metrics(ctx)

    st.caption("현재 파일 하나를 내보냅니다. 여러 파일 한 번에는 우측 일괄 내보내기.")

    st.markdown("**데이터**")
    # ⚠️ 엑셀을 만들기 **전에** 읽어야 같은 run 에 반영된다.
    ctx.settings["export_abs"] = st.checkbox(
        "전류를 절댓값 |I| 로 내보내기",
        value=bool(ctx.settings.get("export_abs", True)),
        key=state.wkey("export", "abs", fid=ctx.fid),
        help="Origin 로그축에 바로 올리려면 양수여야 합니다. `Processed`·`Plot` 시트에 "
             "적용되며, **`Raw` 시트는 언제나 부호를 유지**합니다 — 부호가 필요하면 "
             "거기서 가져오세요.",
    )
    try:
        xlsx = _excel_bytes(ctx, rows)
    except Exception as e:  # noqa: BLE001
        xlsx = None
        st.error(f"엑셀 생성 실패: {type(e).__name__}: {e}")
    st.download_button(
        "📗 엑셀 (.xlsx) — Origin 편집용",
        data=xlsx or b"",
        file_name=f"{stem}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        disabled=xlsx is None,
        key=state.wkey("export", "xlsx", fid=ctx.fid),
        help="Plot(그래프 값) · Raw(원본) · Metrics(지표+붙여넣기 블록) · Info 시트. "
             "트레이스마다 V/I 열 쌍이라 Origin 에서 X/Y 로 바로 지정할 수 있습니다.",
    )
    st.download_button(
        "📊 요약 · 지표 CSV",
        data=_report_csv(ctx, rows),
        file_name=f"{stem}_report.csv",
        mime="text/csv",
        use_container_width=True,
        key=state.wkey("export", "csv", fid=ctx.fid),
    )

    st.markdown("**이미지 (10×8 in · 300 dpi 상당)**")
    try:
        png_json = _fig_json(ctx, transparent=True)
        jpg_json = _fig_json(ctx, transparent=False)
    except Exception as e:  # noqa: BLE001
        st.error(f"이미지 준비 실패: {type(e).__name__}")
        return
    st.components.v1.html(
        _image_button_html(png_json, "png", "btn-png", "🖼️ PNG (투명 배경)", stem), height=44)
    st.components.v1.html(
        _image_button_html(jpg_json, "jpeg", "btn-jpg", "📷 JPG (흰 배경)", stem), height=44)

    w_in = float(ctx.settings["geom"]["page_w_in"])
    h_in = float(ctx.settings["geom"]["page_h_in"])
    st.caption(f"화면 배율과 무관하게 {w_in:g}×{h_in:g} in 를 3배 스케일로 추출합니다.")