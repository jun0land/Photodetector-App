"""인셋(레전드 인셋 + 샘플명 인셋) 그리기. 소유: WP2.

⚠️ `add_inset_legend` 는 축자 이동 보호 대상이 **아니다**. PLAN §4.3 이 shape/annotation
의 ref 를 `paper` → `x domain`/`y domain` 으로 바꾼다.
"""

from __future__ import annotations

from pd_app import constants, state
from pd_app.markup import apply_markup

# 연구실 표준 인셋 정렬 우선순위 (측정 순서 무관 지정 렌더링용)
INSET_ORDER_PRIORITY = {
    "Dark": 0,
    "940 nm": 1,
    "850 nm": 2,
    "740 nm": 3,
    "625 nm": 4,
    "530 nm": 5,
    "470 nm": 6,
    "405 nm": 7,
    "365 nm": 8
}

def _get_inset_priority(tr) -> int:
    label = str(tr.get("label", "")).strip()
    for key, priority in INSET_ORDER_PRIORITY.items():
        if label.startswith(key):
            return priority
    return 99

def _row_height_px(html, font_size):
    lines = html.count("<br>") + 1
    factor = 1.75 if ("<sup>" in html or "<sub>" in html) else 1.5
    return lines * font_size * factor

def _anchor_rect(x, y, w, h, xanchor, yanchor):
    left = x if xanchor == "left" else (x - w / 2 if xanchor == "center" else x - w)
    top = y if yanchor == "top" else (y + h / 2 if yanchor == "middle" else y + h)
    return left, top

def legend_rows(settings):
    rows = []
    traces = list((settings.get("traces") or {}).values())
    traces.sort(key=_get_inset_priority)

    for tr in traces:
        if not tr.get("visible", True) or not tr.get("include_in_inset", True):
            continue
        rows.append({
            "html": apply_markup(tr.get("inset_raw") or tr.get("label") or ""),
            "color": tr["color"],
            "width": tr["width"],
            "dash": tr["dash"],
            # 💡 [추가됨] 인셋 스와치용 투명도 값 매핑 (0~100을 1.0~0.0으로)
            "opacity": 1.0 - (float(tr.get("transparency", 0)) / 100.0),
        })
    return rows

def _legend_metrics(inset, plot_h_px):
    rows = inset.get("rows") or []
    if not rows or plot_h_px <= 0:
        return None
    fs = inset["font_size"]
    heights = [_row_height_px(r["html"], fs) for r in rows]
    total_h = (sum(heights) + 2 * constants.INSET_PAD_PX) / plot_h_px
    w = inset["width"]
    left, top = _anchor_rect(inset["x"], inset["y"], w, total_h,
                             inset["xanchor"], inset["yanchor"])
    return heights, left, top, w, total_h

def _plot_px(settings):
    from pd_app import figure
    geom = settings["geom"]
    dom = figure.domains(geom)
    fig_w, fig_h = figure.px_size(geom)
    return (dom["x1"] - dom["x0"]) * fig_w, (dom["y1"] - dom["y0"]) * fig_h

def _text_w_domain(html, font_size, plot_w_px):
    plain = html
    for tag in ("<b>", "</b>", "<i>", "</i>", "<sup>", "</sup>", "<sub>", "</sub>"):
        plain = plain.replace(tag, "")
    longest = max((len(ln) for ln in plain.split("<br>")), default=0)
    if plot_w_px <= 0:
        return 0.0
    return longest * font_size * 0.55 / plot_w_px

def inset_box(fid, which) -> dict:
    settings = state.file_settings(fid)
    if settings is None:
        return None
    cfg = (settings.get("insets") or {}).get(which)
    if cfg is None:
        return None

    plot_w_px, plot_h_px = _plot_px(settings)
    box = {"x": cfg["x"], "y": cfg["y"],
           "xanchor": cfg["xanchor"], "yanchor": cfg["yanchor"]}

    if which == "legend":
        inset = dict(cfg, rows=legend_rows(settings))
        m = _legend_metrics(inset, plot_h_px)
        box["w"] = cfg["width"]
        box["h"] = m[4] if m else (2 * constants.INSET_PAD_PX / plot_h_px
                                   if plot_h_px > 0 else 0.0)
        return box

    html = apply_markup(cfg.get("text_raw") or "")
    box["w"] = _text_w_domain(html, cfg["font_size"], plot_w_px)
    box["h"] = _row_height_px(html, cfg["font_size"]) / plot_h_px if plot_h_px > 0 else 0.0
    return box

def add_inset_legend(fig, inset, plot_h_px) -> None:
    m = _legend_metrics(inset, plot_h_px)
    if m is None:
        return
    heights, left, top, w, total_h = m
    rows = inset["rows"]
    fs = inset["font_size"]

    fig.add_shape(
        type="rect", xref="x domain", yref="y domain", layer="below",
        x0=left, x1=left + w, y0=top - total_h, y1=top,
        fillcolor=constants.hex_to_rgba(inset["bg_color"], inset["bg_opacity"]),
        line=dict(
            color=inset["border_color"] if inset["border"] else "rgba(0,0,0,0)",
            width=1.2 if inset["border"] else 0,
        ),
    )

    cursor = top - constants.INSET_PAD_PX / plot_h_px
    for r, h_px in zip(rows, heights):
        cy = cursor - (h_px / 2) / plot_h_px
        x0 = left + constants.INSET_PAD_X
        x1 = x0 + constants.INSET_SWATCH_W
        fig.add_shape(
            type="line", xref="x domain", yref="y domain", layer="above",
            x0=x0, x1=x1, y0=cy, y1=cy,
            line=dict(color=r["color"], width=r["width"], dash=r["dash"]),
            opacity=r.get("opacity", 1.0) # 👈 인셋 스와치에도 투명도 적용
        )
        fig.add_annotation(
            x=x1 + constants.INSET_GAP, y=cy, xref="x domain", yref="y domain",
            xanchor="left", yanchor="middle", text=r["html"],
            showarrow=False, align="left",
            font=dict(family=inset.get("font"), size=fs, color="black"),
        )
        cursor -= h_px / plot_h_px

def add_sample_inset(fig, inset) -> None:
    text = apply_markup(inset.get("text_raw") or "")
    if not text:
        return

    ann = dict(
        x=inset["x"], y=inset["y"], xref="x domain", yref="y domain",
        xanchor=inset["xanchor"], yanchor=inset["yanchor"],
        text=text, showarrow=False, align="left",
        font=dict(family=inset.get("font"), size=inset["font_size"], color="black"),
    )
    if inset.get("border"):
        ann["bordercolor"] = inset.get("border_color") or "#000000"
        ann["borderwidth"] = 1.2
        ann["borderpad"] = 4
    if inset.get("bg_color") and inset.get("bg_opacity", 0) > 0:
        ann["bgcolor"] = constants.hex_to_rgba(inset["bg_color"], inset["bg_opacity"])
    fig.add_annotation(**ann)