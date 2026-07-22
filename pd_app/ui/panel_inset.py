"""[인셋] 탭: rows/텍스트 (D2/D3) + PLAN §4.7 수동 위치 폴백. 소유: WP2.

ctx = SimpleNamespace(fid, settings, traces, parsed, fig_px, domains)
    fid       현재 활성 파일 id
    settings  state.file_settings(fid) — 모델이 유일한 진실
    traces    settings["traces"] (TKey -> dict)
    parsed    parsing.parse_file() 결과
    fig_px    figure.px_size(geom) → (w, h)
    domains   figure.domains(geom) → {"x0","x1","y0","y1"}

PLAN §4.7: **WP2 의 수동 위치 UI 가 먼저 출하된다.** WP8(드래그)은 마지막이고 이걸
*교체*할 뿐 — WP8 시작 전에 앱은 이미 출하 가능해야 한다.
수동 UI = 3×3 앵커 `st.segmented_control` (9개 정위치) + `st.number_input` X/Y 미세조정.
같은 `settings["insets"][which]["x"/"y"]` 에 쓴다 → 프리셋/figure/export 가 어느 쪽이든 동일.

SPEC D2: 인셋은 **필수**다. 레거시의 `인셋 레전드 표시` on/off 체크박스는 없앴다.
SPEC C5: 이 패널은 **짧게** 유지한다. 편집 대상을 하나만 렌더하고, 길어질 수 있는
트레이스 행 목록은 높이 제한 컨테이너에 넣어 맨 아래에 둔다 — 폰트 선택이 스크롤
밖으로 밀려나던 레거시 버그의 원인 제거.

패널은 read-render-writeback. 위젯키는 반드시 `state.wkey(group, name, fid=fid)`.
이 모듈은 `render` 외에 아무것도 공개하지 않는다.
"""

from __future__ import annotations

import streamlit as st

from pd_app import constants, state
from pd_app.ui.toolbar import rich_input

# 3×3 정위치 (domain 좌표). 실사용의 ~90% 를 한 번의 클릭으로 커버한다.
_SPOTS = {
    "↖": (0.01, 0.995, "left", "top"),
    "↑": (0.50, 0.995, "center", "top"),
    "↗": (0.99, 0.995, "right", "top"),
    "←": (0.01, 0.50, "left", "middle"),
    "•": (0.50, 0.50, "center", "middle"),
    "→": (0.99, 0.50, "right", "middle"),
    "↙": (0.01, 0.005, "left", "bottom"),
    "↓": (0.50, 0.005, "center", "bottom"),
    "↘": (0.99, 0.005, "right", "bottom"),
}

_INHERIT = "(서식 탭 폰트 상속)"


def _current_spot(cfg):
    """모델이 마침 9개 정위치 중 하나면 그 글리프, 아니면 None(선택 없음)."""
    for glyph, (x, y, xa, ya) in _SPOTS.items():
        if (abs(cfg["x"] - x) < 1e-6 and abs(cfg["y"] - y) < 1e-6
                and cfg["xanchor"] == xa and cfg["yanchor"] == ya):
            return glyph
    return None


def _position_ui(cfg, which, fid):
    """3×3 앵커 + X/Y 미세조정. WP8 의 드래그가 쓸 바로 그 x/y 에 쓴다."""
    kx = state.wkey("inset", f"{which}.x", fid=fid)
    ky = state.wkey("inset", f"{which}.y", fid=fid)

    spot = st.segmented_control(
        "위치", list(_SPOTS), default=_current_spot(cfg),
        key=state.wkey("inset", f"{which}.spot", fid=fid),
        help="9개 정위치 중 하나로 즉시 이동. 미세조정은 아래 X/Y.",
    )
    if spot is not None and spot != _current_spot(cfg):
        cfg["x"], cfg["y"], cfg["xanchor"], cfg["yanchor"] = _SPOTS[spot]
        # 위젯키가 이미 있으면 Streamlit 이 아래 number_input 의 value= 를 무시한다
        # (PLAN §2.3 함정2). 그대로 두면 낡은 위젯 값이 방금 쓴 모델을 되돌린다.
        # bump_rev() 는 프리셋 전용이므로 해당 키만 직접 다시 심는다.
        st.session_state[kx] = cfg["x"]
        st.session_state[ky] = cfg["y"]

    c1, c2 = st.columns(2)
    cfg["x"] = c1.number_input("X", 0.0, 1.0, value=float(min(max(cfg["x"], 0.0), 1.0)),
                               step=0.01, format="%.3f", key=kx)
    cfg["y"] = c2.number_input("Y", 0.0, 1.0, value=float(min(max(cfg["y"], 0.0), 1.0)),
                               step=0.01, format="%.3f", key=ky)


def _font_ui(cfg, which, fid):
    """폰트 패밀리(None = style.font_family 상속) + 크기. C2/C3: 슬라이더 금지."""
    c1, c2 = st.columns([2, 1])
    opts = [_INHERIT] + list(constants.FONT_FAMILIES)
    cur = cfg.get("font")
    fam = c1.selectbox(
        "폰트", opts, index=opts.index(cur) if cur in opts else 0,
        key=state.wkey("inset", f"{which}.font", fid=fid),
    )
    cfg["font"] = None if fam == _INHERIT else fam
    cfg["font_size"] = c2.number_input(
        "글자 크기", constants.FONT_SIZE_MIN, constants.FONT_SIZE_MAX,
        value=int(cfg["font_size"]), step=1,
        key=state.wkey("inset", f"{which}.font_size", fid=fid),
    )


def _legend_ui(ctx, cfg):
    fid = ctx.fid
    if not state.S().get("use_drag"):
        _position_ui(cfg, "legend", fid)
    _font_ui(cfg, "legend", fid)

    c1, c2 = st.columns(2)
    cfg["width"] = c1.number_input(
        "인셋 너비", 0.10, 0.90, value=float(cfg["width"]), step=0.01, format="%.2f",
        help="그래프 폭 대비 비율. 라벨이 넘치면 넓히세요.",
        key=state.wkey("inset", "legend.width", fid=fid),
    )
    cfg["bg_opacity"] = c2.number_input(
        "배경 투명도", 0.0, 1.0, value=float(cfg["bg_opacity"]), step=0.05, format="%.2f",
        key=state.wkey("inset", "legend.bg_opacity", fid=fid),
    )

    c3, c4, c5 = st.columns([1.2, 1, 1])
    cfg["border"] = c3.checkbox(
        "테두리", value=bool(cfg["border"]),
        key=state.wkey("inset", "legend.border", fid=fid),
    )
    cfg["border_color"] = c4.color_picker(
        "테두리 색", value=cfg["border_color"] or "#000000",
        key=state.wkey("inset", "legend.border_color", fid=fid),
    )
    cfg["bg_color"] = c5.color_picker(
        "배경색", value=cfg["bg_color"],
        key=state.wkey("inset", "legend.bg_color", fid=fid),
    )

    # 길어질 수 있는 유일한 블록 → 높이 제한 + 맨 아래 (C5)
    st.caption("표시할 항목 · 텍스트")
    with st.container(height=180):
        for tk, tr in (ctx.traces or {}).items():
            c6, c7 = st.columns([1, 5])
            tr["include_in_inset"] = c6.checkbox(
                f"포함 {tk}", value=bool(tr.get("include_in_inset", True)),
                label_visibility="collapsed",
                key=state.wkey("inset", f"legend.rows.{tk}.include", fid=fid),
            )
            with c7:
                tr["inset_raw"] = rich_input(
                    f"텍스트 {tk}", tr.get("inset_raw") or "",
                    key=state.wkey("inset", f"legend.rows.{tk}.text", fid=fid),
                )
            if not tr.get("visible", True):
                c7.caption("숨긴 트레이스라 인셋에도 안 나옵니다.")


def _sample_ui(ctx, cfg):
    fid = ctx.fid
    cfg["text_raw"] = rich_input(
        "샘플 이름", cfg.get("text_raw") or "",
        key=state.wkey("inset", "sample.text_raw", fid=fid),
        placeholder="Sample",
    )
    if not state.S().get("use_drag"):
        _position_ui(cfg, "sample", fid)
    _font_ui(cfg, "sample", fid)


def render(ctx) -> None:
    """인셋 탭 렌더. D2 — 인셋은 필수라 on/off 체크박스가 없다."""
    if ctx.settings is None:
        return
    insets = ctx.settings["insets"]

    which = st.segmented_control(
        "편집 대상", ["레전드", "샘플 이름"], default="레전드",
        label_visibility="collapsed",
        key=state.wkey("inset", "which", fid=ctx.fid),
    )
    # 한 번에 하나만 렌더한다 (C5: 패널을 짧게). 모델이 진실이므로 안 그려진 위젯의
    # 캐시가 사라져도 값은 안 잃는다 (V14) — 다시 그릴 때 value= 로 모델에서 재시드.
    if which == "샘플 이름":
        _sample_ui(ctx, insets["sample"])
    else:
        _legend_ui(ctx, insets["legend"])
