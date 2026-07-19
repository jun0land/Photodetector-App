"""인셋(레전드 인셋 + 샘플명 인셋) 그리기. 소유: WP2.

⚠️ `add_inset_legend` 는 축자 이동 보호 대상이 **아니다**. PLAN §4.3 이 shape/annotation
의 ref 를 `paper` → `x domain`/`y domain` 으로 바꾼다 (V8: margin=0 이면 paper 가
페이지 전체에 매핑되어 B1 의 Left/Top 을 건드릴 때마다 어긋남).

원본 본문은 `_legacy_reference.py.txt` 약 598-653 줄. **ref 와 호출 인자만** 바뀌었고
px→비율 행 높이 수식(`_row_height_px`, 1.75 sup/sub 계수, `INSET_PAD_PX`)은 그대로다.
호출 측 규약 (PLAN §4.3):

    dom = domains(geom); _, fig_h = px_size(geom)
    plot_h_px = (dom["y1"] - dom["y0"]) * fig_h     # margin 박스가 아니라 domain 박스 기준
    insets.add_inset_legend(fig, inset, plot_h_px)

기하 수식은 `_anchor_rect` 한 곳에만 있다. `inset_box`(WP8 의 드래그 히트박스)와
`add_inset_legend`(실제 렌더)가 같은 함수를 쓰므로 둘이 어긋날 수 없다.
"""

from __future__ import annotations

from pd_app import constants, state
from pd_app.markup import apply_markup


# ---------------- 기하 (렌더와 히트박스가 공유) ----------------
def _row_height_px(html, font_size):
    """행 높이(px). 위/아래첨자는 줄 상자를 키우므로 행마다 따로 계산."""
    lines = html.count("<br>") + 1
    factor = 1.75 if ("<sup>" in html or "<sub>" in html) else 1.5
    return lines * font_size * factor


def _anchor_rect(x, y, w, h, xanchor, yanchor):
    """(앵커점, 크기, 앵커) → (left, top). 레거시 605-625 의 수식 그대로."""
    left = x if xanchor == "left" else (x - w / 2 if xanchor == "center" else x - w)
    top = y if yanchor == "top" else (y + h / 2 if yanchor == "middle" else y + h)
    return left, top


def legend_rows(settings):
    """settings → 레전드 인셋의 행 목록. **WP1/WP8 도 이걸 써야 한다.**

    행 = 보이는(visible) 트레이스 중 include_in_inset 인 것. 색·두께·대시는 실제
    트레이스 설정을 그대로 따라가므로 인셋 스와치가 곡선과 항상 일치한다.
    """
    rows = []
    for tr in (settings.get("traces") or {}).values():
        if not tr.get("visible", True) or not tr.get("include_in_inset", True):
            continue
        rows.append({
            "html": apply_markup(tr.get("inset_raw") or tr.get("label") or ""),
            "color": tr["color"],
            "width": tr["width"],
            "dash": tr["dash"],
        })
    return rows


def _legend_metrics(inset, plot_h_px):
    """(heights, left, top, w, total_h) 또는 rows 가 없으면 None."""
    rows = inset.get("rows") or []
    if not rows or plot_h_px <= 0:
        return None
    fs = inset["font_size"]
    heights = [_row_height_px(r["html"], fs) for r in rows]
    total_h = (sum(heights) + 2 * constants.INSET_PAD_PX) / plot_h_px  # domain y
    w = inset["width"]
    left, top = _anchor_rect(inset["x"], inset["y"], w, total_h,
                             inset["xanchor"], inset["yanchor"])
    return heights, left, top, w, total_h


def _plot_px(settings):
    """(plot_w_px, plot_h_px) = domain 박스의 픽셀 크기. figure.py 가 유일한 기준."""
    from pd_app import figure  # 지연 import: figure.py 가 insets.py 를 import 한다

    geom = settings["geom"]
    dom = figure.domains(geom)
    fig_w, fig_h = figure.px_size(geom)
    return (dom["x1"] - dom["x0"]) * fig_w, (dom["y1"] - dom["y0"]) * fig_h


def _text_w_domain(html, font_size, plot_w_px):
    """렌더 폭 추정치(domain x). 히트박스용 근사 — 렌더에는 안 쓴다."""
    plain = html
    for tag in ("<b>", "</b>", "<i>", "</i>", "<sup>", "</sup>", "<sub>", "</sub>"):
        plain = plain.replace(tag, "")
    longest = max((len(ln) for ln in plain.split("<br>")), default=0)
    if plot_w_px <= 0:
        return 0.0
    return longest * font_size * 0.55 / plot_w_px


def inset_box(fid, which) -> dict:
    """인셋의 바운딩 박스 (domain 단위). WP8 의 드래그 히트박스가 이걸 쓴다.

    반환 {"x","y","w","h","xanchor","yanchor"} — x/y 는 settings 에 저장된 앵커점
    그대로이고 w/h 가 실제 크기다. 사각형은 `_anchor_rect(x, y, w, h, xanchor, yanchor)`
    로 얻는다 (렌더가 쓰는 바로 그 함수).
    모르는 fid/which 면 None.
    """
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
        # 행이 없으면 패딩만 남은 빈 상자 — 그래도 잡을 수 있게 폭은 유지한다
        box["w"] = cfg["width"]
        box["h"] = m[4] if m else (2 * constants.INSET_PAD_PX / plot_h_px
                                   if plot_h_px > 0 else 0.0)
        return box

    html = apply_markup(cfg.get("text_raw") or "")
    box["w"] = _text_w_domain(html, cfg["font_size"], plot_w_px)
    box["h"] = _row_height_px(html, cfg["font_size"]) / plot_h_px if plot_h_px > 0 else 0.0
    return box


# ---------------- 렌더 ----------------
def add_inset_legend(fig, inset, plot_h_px) -> None:
    """그래프 안쪽에 Origin 풍 레전드를 직접 그린다.

    세로는 px -> domain 으로 환산해 정확히 계산하고, 가로는 domain 비율을 그대로 쓴다.
    스와치와 라벨은 같은 y(중앙 정렬)를 공유하므로 행 수/폰트 크기가 바뀌어도
    어긋나지 않는다.

    ref 는 `x domain`/`y domain` (PLAN §4.3). `paper` 를 쓰면 margin=0 인 B1 레이아웃
    에서 페이지 구석으로 날아간다 (V8).
    """
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
        cy = cursor - (h_px / 2) / plot_h_px          # 행의 세로 중앙
        x0 = left + constants.INSET_PAD_X
        x1 = x0 + constants.INSET_SWATCH_W
        fig.add_shape(  # 실제 선: 색 + 두께 + 대시까지 그대로
            type="line", xref="x domain", yref="y domain", layer="above",
            x0=x0, x1=x1, y0=cy, y1=cy,
            line=dict(color=r["color"], width=r["width"], dash=r["dash"]),
        )
        fig.add_annotation(
            x=x1 + constants.INSET_GAP, y=cy, xref="x domain", yref="y domain",
            xanchor="left", yanchor="middle", text=r["html"],
            showarrow=False, align="left",
            font=dict(family=inset.get("font"), size=fs, color="black"),
        )
        cursor -= h_px / plot_h_px


def add_sample_inset(fig, inset) -> None:
    """샘플 이름 인셋(D3). 예시 이미지의 `Quasi-2D x3` — 테두리/배경 없는 맨 텍스트.

    `font=None` 이면 family 를 안 넘겨 layout.font (style.font_family) 를 상속한다.
    """
    text = apply_markup(inset.get("text_raw") or "")
    if not text:
        return

    ann = dict(
        x=inset["x"], y=inset["y"], xref="x domain", yref="y domain",
        xanchor=inset["xanchor"], yanchor=inset["yanchor"],
        text=text, showarrow=False, align="left",
        font=dict(family=inset.get("font"), size=inset["font_size"], color="black"),
    )
    # 기본은 맨 텍스트. 사용자가 켠 경우에만 테두리/배경이 붙는다.
    if inset.get("border"):
        ann["bordercolor"] = inset.get("border_color") or "#000000"
        ann["borderwidth"] = 1.2
        ann["borderpad"] = 4
    if inset.get("bg_color") and inset.get("bg_opacity", 0) > 0:
        ann["bgcolor"] = constants.hex_to_rgba(inset["bg_color"], inset["bg_opacity"])
    fig.add_annotation(**ann)
