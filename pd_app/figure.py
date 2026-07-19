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

# major tick 대비 minor tick 길이 비율 (Origin 예시와 동일한 인상)
_TICKLEN_MAJOR = 6
_TICKLEN_MINOR = 3
_AXIS_LINEWIDTH = 1.5


def px_size(geom) -> tuple[int, int]:
    """geometry(inch) → figure 픽셀 크기 (w_in*96, h_in*96). 기본 (960, 768)."""
    w = float(geom.get("page_w_in", 10.0))
    h = float(geom.get("page_h_in", 8.0))
    return int(round(w * FIG_DPI)), int(round(h * FIG_DPI))


def domains(geom) -> dict:
    """geometry(%) → 축 domain {"x0","x1","y0","y1"}.

    Top 은 위에서부터 재므로 y 는 뒤집어서 계산한다 (SPEC B1).
    기본값 L17.9 T11.58 W68.2 H71.77 → x=[0.179, 0.861], y=[0.1665, 0.8842].
    """
    left = float(geom.get("graph_left_pct", 17.9)) / 100.0
    top = float(geom.get("graph_top_pct", 11.58)) / 100.0
    width = float(geom.get("graph_width_pct", 68.2)) / 100.0
    height = float(geom.get("graph_height_pct", 71.77)) / 100.0

    x0 = left
    x1 = left + width
    y1 = 1.0 - top
    y0 = y1 - height
    # plotly 는 domain 이 [0,1] 을 벗어나거나 뒤집히면 예외를 던진다.
    x0, x1 = _clamp01(x0), _clamp01(x1)
    y0, y1 = _clamp01(y0), _clamp01(y1)
    if x1 <= x0:
        x1 = min(1.0, x0 + 1e-3)
    if y1 <= y0:
        y1 = min(1.0, y0 + 1e-3)
    return {"x0": x0, "x1": x1, "y0": y0, "y1": y1}


def zero_count(fig) -> int:
    """로그축에서 표시할 수 없어 제외된 0 값의 개수. build_figure 가 붙여 둔 값을 읽는다.

    figure.py 는 UI-free 라 st.warning 을 부르지 않는다. 경고는 호출자가 이 값을 보고 낸다.
    """
    return int(getattr(fig, "_pd_zero_count", 0))


def _clamp01(v):
    return max(0.0, min(1.0, float(v)))


def _visible_traces(parsed, settings):
    """(tkey, trace_settings, df) 목록. D5: visible 인 것만 그린다."""
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
    """minor tick 설정 (A4). dtick 이 없으면 minor 를 끈다."""
    if dtick in (None, "", 0):
        return None
    return dict(dtick=dtick, ticks="inside", ticklen=_TICKLEN_MINOR * scale,
                tickwidth=_AXIS_LINEWIDTH * scale, tickcolor="black")


def _x_range(xs, ax):
    """A5: auto 여도 데이터 min/max 로 range 를 명시해 Plotly 의 자동 패딩을 없앤다."""
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
    return [float(lo), float(hi)]  # 패딩 0 — 곡선이 좌우 테두리에 닿는다


def _y_range(ys, ax, is_log):
    """A5 + PLAN §8.3: X 와 달리 Y(log) 는 decade 경계로 바깥쪽 스냅한다.

    Plotly 의 log 축 range 는 log10 단위임에 주의.
    """
    if not ax.get("auto", True):
        lo, hi = ax.get("min"), ax.get("max")
        if lo is not None and hi is not None and lo != hi:
            if not is_log:
                return [float(lo), float(hi)]
            if lo > 0 and hi > 0:
                return [math.log10(float(lo)), math.log10(float(hi))]
            # log 축에 0 이하의 수동 범위 → 무시하고 auto 로 (경고는 호출자 몫)
    if not ys:
        return None

    if is_log:
        # 0/음수는 log 로 못 그린다 — 범위 계산에서 제외
        pos = [s[s > 0] for s in ys]
        pos = [s for s in pos if len(s)]
        if not pos:
            return None
        lo = min(s.min() for s in pos)
        hi = max(s.max() for s in pos)
        if not (math.isfinite(lo) and math.isfinite(hi)):
            return None
        # 예시 이미지처럼 1E-11…1E-5 로 깔끔히 — 원시 극값으로 너덜너덜하게 자르지 않는다
        return [math.floor(math.log10(lo)), math.ceil(math.log10(hi))]

    lo = min(s.min() for s in ys)
    hi = max(s.max() for s in ys)
    if not (math.isfinite(lo) and math.isfinite(hi)) or lo == hi:
        return None
    return [float(lo), float(hi)]


def build_figure(fid, *, px_scale: float = 1.0) -> go.Figure:
    """파일 설정으로 완성된 figure 를 만든다.

    px_scale != 1.0 이면 figure 크기와 폰트·선을 비례 축소한다 (PLAN §5.5 폴백).
    내보내기는 항상 px_scale=1.0 — 정확히 10×8in.
    """
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
    # A2 / PLAN §8.2: log 는 |I| 강제, linear 는 사용자 선택. 제목과의 결합은 없다.
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
        width = float(ts.get("width", style["line_width"])) * scale  # C4: 0.5 스텝 float
        fig.add_trace(go.Scatter(
            x=x, y=y,
            mode="lines+markers" if show_markers else "lines",
            name=apply_markup(ts.get("legend_raw", "")),
            line=dict(color=color, width=width, dash=ts.get("dash", "solid")),
            marker=dict(color=color, size=5 * scale),
            hoverlabel=dict(font=dict(family=font_family)),
        ))

    # 로그축에서 제외된 0 값 — st.warning 은 여기서 못 부른다 (UI-free). 호출자가 zero_count() 로 읽는다.
    fig._pd_zero_count = zeros

    tick_font = dict(family=font_family, size=style["tick_font_size"] * scale, color="black")
    title_font = dict(family=font_family, size=style["title_font_size"] * scale, color="black")
    axis_common = dict(
        showline=True, linecolor="black", linewidth=_AXIS_LINEWIDTH * scale,
        mirror=True,                      # A7: 4면 박스
        ticks="inside", tickwidth=_AXIS_LINEWIDTH * scale, tickcolor="black",
        ticklen=_TICKLEN_MAJOR * scale,
        showgrid=show_grid, gridcolor="#D9D9D9", zeroline=False,
        exponentformat="E", showexponent="all",   # A3: 1E-11 (power 아님)
        tickfont=tick_font,
    )

    x_kw = dict(axis_common)
    x_kw["domain"] = [dom["x0"], dom["x1"]]                      # B1
    x_kw["type"] = ax_x.get("type", "linear")
    x_kw["title"] = dict(text=apply_markup(ax_x.get("title_raw", "")), font=title_font)
    if ax_x.get("title_standoff") is not None:                   # B2 (V9)
        x_kw["title"]["standoff"] = ax_x["title_standoff"] * scale
    if ax_x.get("dtick") is not None:                            # A6
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
    y_kw["type"] = "log" if is_log else "linear"                 # A1
    # A2: Y 제목은 언제나 사용자의 title_raw. 절댓값 기호를 주입하지 않는다.
    y_kw["title"] = dict(text=apply_markup(ax_y.get("title_raw", "")), font=title_font)
    if ax_y.get("title_standoff") is not None:
        y_kw["title"]["standoff"] = ax_y["title_standoff"] * scale
    if ax_y.get("dtick") is not None:
        y_kw["dtick"] = ax_y["dtick"]
    my = _minor(ax_y.get("minor_dtick"), scale)                  # log 는 "D1"/"D2" (V9)
    if my:
        y_kw["minor"] = my
    ry = _y_range(ys, ax_y, is_log)
    if ry:
        y_kw["range"] = ry
        y_kw["autorange"] = False

    fig.update_layout(
        template="simple_white",
        plot_bgcolor="white", paper_bgcolor="white",   # A7: 논문용 — 절대 투명화 금지
        font=dict(family=font_family, color="black"),
        xaxis=x_kw, yaxis=y_kw,
        showlegend=False,                              # D1: 인셋이 레전드를 대체
        margin=dict(l=0, r=0, t=0, b=0),               # B1 / PLAN §4.3 (V8)
        width=fig_w, height=fig_h,
    )

    # 인셋은 WP2 소유. 스텁이 아직 NotImplementedError 라 독립 테스트를 위해 방어한다.
    # import 를 함수 안에 두어 WP2 가 insets.py 에서 figure 를 참조해도 순환하지 않게 한다.
    from pd_app import insets

    # inset_box 는 WP8 드래그 히트박스용(rows 없음)이라 렌더에 넘기면 조용히 빈다.
    # add_inset_legend 는 rows 가 담긴 실제 설정 dict 를 원한다 → legend_rows 로 합쳐 넘긴다.
    # px_scale<1 일 때 인셋 font_size·스와치 선두께도 축·틱과 같은 비율로 줄여야
    # 인셋이 축 라벨 대비 과대해 보이지 않는다 (insets.py 는 건드리지 않고 cfg 만 스케일).
    plot_h_px = (dom["y1"] - dom["y0"]) * fig_h
    try:
        lg = settings["insets"]["legend"]
        legend_cfg = dict(lg, rows=insets.legend_rows(settings),
                          font_size=lg["font_size"] * scale)
        for r in legend_cfg["rows"]:
            r["width"] = r["width"] * scale        # 스와치 선두께도 축소
        insets.add_inset_legend(fig, legend_cfg, plot_h_px)
    except NotImplementedError:
        pass
    try:
        sp = settings["insets"]["sample"]
        insets.add_sample_inset(fig, dict(sp, font_size=sp["font_size"] * scale))
    except NotImplementedError:
        pass

    return fig
