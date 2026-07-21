"""Plotly figure 조립. 소유: WP1.

figure 는 항상 정확히 `page_w_in*96 × page_h_in*96` (기본 960×768) 로 만든다.
화면 축소는 CSS 가 담당 (PLAN §5.5/§8.1) — 여기서 줄이지 않는다.
`px_scale` 은 §5.5 의 hover 히트테스트 폴백 전용 (내보내기는 항상 1.0).

축 domain 은 B1 의 % 지정에서 나온다: x=[L, L+W], y=[1-(T+H), 1-T], margin 0.

이 모듈은 **UI-free** 다. st.* 를 절대 부르지 않는다. 로그축에서 제외된 0 값의 개수는
`fig._pd_zero_count` 에 붙여 두고 `zero_count(fig)` 로 읽는다 — 경고는 호출자 몫.
"""

from __future__ import annotations

import math

import plotly.graph_objects as go

from pd_app import parsing, state
from pd_app.markup import apply_markup

FIG_DPI = 96

_TICKLEN_MAJOR = 6
_TICKLEN_MINOR = 3
_AXIS_LINEWIDTH = 1.5


def px_size(geom) -> tuple[int, int]:
    w = float(geom.get("page_w_in", 10.0))
    h = float(geom.get("page_h_in", 8.0))
    return int(round(w * FIG_DPI)), int(round(h * FIG_DPI))


def domains(geom) -> dict:
    left = float(geom.get("graph_left_pct", 17.9)) / 100.0
    top = float(geom.get("graph_top_pct", 11.58)) / 100.0
    width = float(geom.get("graph_width_pct", 68.2)) / 100.0
    height = float(geom.get("graph_height_pct", 71.77)) / 100.0

    x0 = left
    x1 = left + width
    y1 = 1.0 - top
    y0 = y1 - height
    x0, x1 = _clamp01(x0), _clamp01(x1)
    y0, y1 = _clamp01(y0), _clamp01(y1)
    if x1 <= x0:
        x1 = min(1.0, x0 + 1e-3)
    if y1 <= y0:
        y1 = min(1.0, y0 + 1e-3)
    return {"x0": x0, "x1": x1, "y0": y0, "y1": y1}


def zero_count(fig) -> int:
    return int(getattr(fig, "_pd_zero_count", 0))


def _clamp01(v):
    return max(0.0, min(1.0, float(v)))


def _visible_traces(parsed, settings):
    out = []
    seen = {}
    for t in parsed["traces"]:
        label = t["label"]
        seen[label] = seen.get(label, 0) + 1
        tk = state.tkey_of(t, seen[label])
        ts = settings["traces"].get(tk)
        if ts is None or not ts.get("visible", True):
            continue
        out.append((tk, ts, t["df"]))
    return out


def _series(df, use_abs):
    y = df["AnodeI"].abs() if use_abs else df["AnodeI"]
    return df["AnodeV"], y


def _minor(dtick, scale):
    if dtick in (None, "", 0):
        return None
    return dict(dtick=dtick, ticks="inside", ticklen=_TICKLEN_MINOR * scale,
                tickwidth=_AXIS_LINEWIDTH * scale, tickcolor="black")


def _x_range(xs, ax):
    if not ax.get("auto", True):
        lo, hi = ax.get("min"), ax.get("max")
        if lo is not None and hi is not None and lo != hi:
            return [float(lo), float(hi)]
    if not xs:
        return None
    lo = min(s.min() for s in xs)
    hi = max(s.max() for s in xs)
    if not (math.isfinite(lo) and math.isfinite(hi)) or lo == hi:
        return None
    return [float(lo), float(hi)]


def _y_range(ys, ax, is_log):
    if not ax.get("auto", True):
        lo, hi = ax.get("min"), ax.get("max")
        if lo is not None and hi is not None and lo != hi:
            if not is_log:
                return [float(lo), float(hi)]
            if lo > 0 and hi > 0:
                return [math.log10(float(lo)), math.log10(float(hi))]
    if not ys:
        return None

    if is_log:
        pos = [s[s > 0] for s in ys]
        pos = [s for s in pos if len(s)]
        if not pos:
            return None
        lo = min(s.min() for s in pos)
        hi = max(s.max() for s in pos)
        if not (math.isfinite(lo) and math.isfinite(hi)):
            return None
        return [math.floor(math.log10(lo)), math.ceil(math.log10(hi))]

    lo = min(s.min() for s in ys)
    hi = max(s.max() for s in ys)
    if not (math.isfinite(lo) and math.isfinite(hi)) or lo == hi:
        return None
    return [float(lo), float(hi)]


def build_figure(fid, *, px_scale: float = 1.0) -> go.Figure:
    s = state.S()
    settings = state.file_settings(fid)
    if settings is None:
        raise KeyError(f"unknown fid: {fid!r}")
    f = s["files"][fid]
    parsed = parsing.parse_file(f["bytes"], f["name"])

    scale = float(px_scale)
    geom = settings["geom"]
    style = settings["style"]
    ax_x = settings["axes"]["x"]
    ax_y = settings["axes"]["y"]

    fig_w, fig_h = px_size(geom)
    fig_w = int(round(fig_w * scale))
    fig_h = int(round(fig_h * scale))
    dom = domains(geom)

    is_log = ax_y.get("type", "log") == "log"
    use_abs = True if is_log else bool(settings.get("use_abs", False))

    font_family = style["font_family"]
    show_markers = bool(style.get("show_markers", False))
    show_grid = bool(style.get("show_grid", False))

    fig = go.Figure()
    zeros = 0
    xs, ys = [], []
    for tk, ts, df in _visible_traces(parsed, settings):
        x, y = _series(df, use_abs)
        if is_log:
            zeros += int((y <= 0).sum())
        xs.append(x)
        ys.append(y)
        color = ts["color"]
        width = float(ts.get("width", style["line_width"])) * scale
        
        # 💡 [핵심] 설정된 투명도(0~100%)를 Plotly opacity(1.0~0.0)로 변환
        opacity = 1.0 - (float(ts.get("transparency", 0)) / 100.0)

        fig.add_trace(go.Scatter(
            x=x, y=y,
            mode="lines+markers" if show_markers else "lines",
            name=apply_markup(ts.get("legend_raw", "")),
            line=dict(color=color, width=width, dash=ts.get("dash", "solid")),
            marker=dict(color=color, size=5 * scale),
            opacity=opacity,  # 👈 투명도 적용
            hoverlabel=dict(font=dict(family=font_family)),
        ))

    fig._pd_zero_count = zeros

    tick_font = dict(family=font_family, size=style["tick_font_size"] * scale, color="black")
    title_font = dict(family=font_family, size=style["title_font_size"] * scale, color="black")
    axis_common = dict(
        showline=True, linecolor="black", linewidth=_AXIS_LINEWIDTH * scale,
        mirror=True,
        ticks="inside", tickwidth=_AXIS_LINEWIDTH * scale, tickcolor="black",
        ticklen=_TICKLEN_MAJOR * scale,
        showgrid=show_grid, gridcolor="#D9D9D9", zeroline=False,
        exponentformat="E", showexponent="all",
        tickfont=tick_font,
    )

    x_kw = dict(axis_common)
    x_kw["domain"] = [dom["x0"], dom["x1"]]
    x_kw["type"] = ax_x.get("type", "linear")
    x_kw["title"] = dict(text=apply_markup(ax_x.get("title_raw", "")), font=title_font)
    if ax_x.get("title_standoff") is not None:
        x_kw["title"]["standoff"] = ax_x["title_standoff"] * scale
    if ax_x.get("dtick") is not None:
        x_kw["dtick"] = ax_x["dtick"]
    mx = _minor(ax_x.get("minor_dtick"), scale)
    if mx:
        x_kw["minor"] = mx
    rx = _x_range(xs, ax_x)
    if rx:
        x_kw["range"] = rx
        x_kw["autorange"] = False

    y_kw = dict(axis_common)
    y_kw["domain"] = [dom["y0"], dom["y1"]]
    y_kw["type"] = "log" if is_log else "linear"
    y_kw["title"] = dict(text=apply_markup(ax_y.get("title_raw", "")), font=title_font)
    if ax_y.get("title_standoff") is not None:
        y_kw["title"]["standoff"] = ax_y["title_standoff"] * scale
    if ax_y.get("dtick") is not None:
        y_kw["dtick"] = ax_y["dtick"]
    my = _minor(ax_y.get("minor_dtick"), scale)
    if my:
        y_kw["minor"] = my
    ry = _y_range(ys, ax_y, is_log)
    if ry:
        y_kw["range"] = ry
        y_kw["autorange"] = False

    fig.update_layout(
        template="simple_white",
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family=font_family, color="black"),
        xaxis=x_kw, yaxis=y_kw,
        showlegend=False,
        margin=dict(l=0, r=0, t=0, b=0),
        width=fig_w, height=fig_h,
    )

    from pd_app import insets

    plot_h_px = (dom["y1"] - dom["y0"]) * fig_h
    try:
        lg = settings["insets"]["legend"]
        legend_cfg = dict(lg, rows=insets.legend_rows(settings),
                          font_size=lg["font_size"] * scale)
        for r in legend_cfg["rows"]:
            r["width"] = r["width"] * scale
        insets.add_inset_legend(fig, legend_cfg, plot_h_px)
    except NotImplementedError:
        pass
    try:
        sp = settings["insets"]["sample"]
        insets.add_sample_inset(fig, dict(sp, font_size=sp["font_size"] * scale))
    except NotImplementedError:
        pass

    return fig