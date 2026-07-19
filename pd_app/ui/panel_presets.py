"""[포맷] 탭: 프리셋 저장/불러오기/전체적용 (E1/E2). 소유: WP4.

ctx = SimpleNamespace(fid, settings, traces, parsed, fig_px, domains)
    fid       현재 활성 파일 id
    settings  state.file_settings(fid) — 모델이 유일한 진실
    traces    settings["traces"] (TKey -> dict)
    parsed    parsing.parse_file() 결과
    fig_px    figure.px_size(geom) → (w, h)
    domains   figure.domains(geom) → {"x0","x1","y0","y1"}

PLAN §8.5: E1 항목은 필수, `style`+`geom` 은 선택 블록으로 추가.
저장 UI 에 `[✓] 폰트·크기도 함께 저장` / `[✓] 페이지·그래프 크기도 함께 저장`, 둘 다 기본 켜짐.
프리셋 적용은 `presets.apply_to()` 경유 (내부에서 bump_rev() → value= 가 반영됨).

패널은 read-render-writeback. 위젯키는 반드시 `state.wkey(group, name, fid=fid)`.
이 모듈은 `render` 외에 아무것도 공개하지 않는다.
"""

from __future__ import annotations

import copy
import re

import streamlit as st

from pd_app import presets, state

# 적용 직후엔 st.rerun() 으로 전체 UI 가 새 위젯키로 다시 그려져야 하므로, 메시지는
# 세션에 실어 보내고 다음 run 의 맨 위에서 소비한다. (pd 스키마를 건드리지 않으려고
# state.S() 가 아니라 st.session_state 를 직접 쓴다 — state.py 는 READ-ONLY.)
_MSG_SLOT = "pd_preset_msgs"


def _show(msgs) -> None:
    """presets 의 메시지 규약: INFO_PREFIX 는 안내, 나머지는 경고."""
    for m in msgs:
        if m.startswith(presets.INFO_PREFIX):
            st.info(m[len(presets.INFO_PREFIX):])
        else:
            st.warning(m)


def _drain() -> None:
    msgs = st.session_state.pop(_MSG_SLOT, None)
    if msgs:
        _show(msgs)


def _defer(msgs) -> None:
    st.session_state[_MSG_SLOT] = list(msgs)


def _safe_filename(name) -> str:
    s = re.sub(r"[^\w\-. ]+", "_", str(name)).strip() or "preset"
    return f"{s}.json"


def _default_name(s, fid) -> str:
    f = s["files"].get(fid)
    stem = re.sub(r"\.[^.]+$", "", f["name"]) if f else "포맷"
    base = f"{stem} 포맷"
    if base not in s["presets"]:
        return base
    i = 2
    while f"{base} {i}" in s["presets"]:
        i += 1
    return f"{base} {i}"


def render(ctx) -> None:
    """포맷(프리셋) 탭 렌더."""
    fid = ctx.fid
    s = state.S()

    _drain()

    if fid is None or ctx.settings is None:
        st.info("파일을 추가하면 현재 서식을 프리셋으로 저장할 수 있습니다.")
        return

    # ---------------- 저장 (E1 + PLAN §8.5) ----------------
    st.markdown("**현재 서식을 프리셋으로 저장**")
    name = st.text_input(
        "프리셋 이름",
        value=_default_name(s, fid),
        key=state.wkey("preset", "name", fid=fid),
    )
    name = (name or "").strip() or "이름 없는 프리셋"

    # 둘 다 기본 켜짐 (PLAN §8.5). 파장별 색·선 두께·XY 스케일·축 제목 위치·인셋 위치는
    # E1 필수 항목이라 체크박스와 무관하게 항상 저장된다.
    inc_style = st.checkbox(
        "폰트·크기도 함께 저장",
        value=True,
        key=state.wkey("preset", "inc_style", fid=fid),
        help="폰트 종류와 제목/눈금 글자 크기, 기본 선 두께까지 프리셋에 담습니다.",
    )
    inc_geom = st.checkbox(
        "페이지·그래프 크기도 함께 저장",
        value=True,
        key=state.wkey("preset", "inc_geom", fid=fid),
        help="배경 크기(inch)와 그래프 영역의 Left/Top/Width/Height 를 프리셋에 담습니다.",
    )

    preset = presets.extract(fid, name, include_style=inc_style, include_geom=inc_geom)

    c1, c2 = st.columns(2)
    if c1.button("프리셋으로 저장", use_container_width=True,
                 key=state.wkey("preset", "save", fid=fid)):
        s["presets"][name] = copy.deepcopy(preset)
        st.success(f"`{name}` 프리셋을 저장했습니다.")
    c2.download_button(
        "JSON 내려받기",
        data=presets.to_bytes(preset),
        file_name=_safe_filename(name),
        mime="application/json",
        use_container_width=True,
        key=state.wkey("preset", "download", fid=fid),
    )

    st.divider()

    # ---------------- 불러오기 ----------------
    st.markdown("**프리셋 불러오기**")
    up = st.file_uploader(
        "프리셋 JSON",
        type=["json"],
        key=state.wkey("preset", "upload", fid=fid),
        label_visibility="collapsed",
    )
    if up is not None:
        loaded, warns = presets.load(up.getvalue())
        _show(warns)
        st.caption(f"`{loaded['name']}` — 트레이스 {len(loaded['traces_by_label'])}개"
                   + (" · 폰트 포함" if "style" in loaded else "")
                   + (" · 크기 포함" if "geom" in loaded else ""))
        if st.button("이 프리셋을 목록에 추가", use_container_width=True,
                     key=state.wkey("preset", "add_uploaded", fid=fid)):
            s["presets"][loaded["name"]] = loaded
            st.success(f"`{loaded['name']}` 프리셋을 목록에 추가했습니다.")

    st.divider()

    # ---------------- 적용 (E2) ----------------
    st.markdown("**프리셋 적용**")
    names = list(s["presets"].keys())
    if not names:
        st.caption("저장된 프리셋이 없습니다. 위에서 저장하거나 JSON 을 불러오세요.")
        return

    sel = st.selectbox("적용할 프리셋", names, key=state.wkey("preset", "select", fid=fid))
    chosen = s["presets"][sel]

    a1, a2 = st.columns(2)
    apply_here = a1.button("현재 파일에 적용", use_container_width=True, type="primary",
                           key=state.wkey("preset", "apply_one", fid=fid))
    apply_all = a2.button("모든 파일에 적용", use_container_width=True,
                          disabled=len(s["order"]) < 2,
                          key=state.wkey("preset", "apply_all", fid=fid))

    if apply_here or apply_all:
        # apply_* 가 bump_rev() 를 호출한다 → 이미 그려진 위젯들은 옛 키를 쓰고 있으므로
        # 전체를 다시 그려야 새 값이 보인다. 메시지는 세션에 실어 다음 run 에서 표시.
        msgs = presets.apply_to_all(chosen) if apply_all else presets.apply_to(fid, chosen)
        # 새로 추가되는 파일도 같은 서식을 물려받게 한다 (PLAN §2.4).
        presets.apply_to_current_format(chosen)
        msgs.append(presets.INFO_PREFIX + (
            f"`{sel}` 을(를) 열려 있는 {len(s['order'])}개 파일 전체에 적용했습니다."
            if apply_all else f"`{sel}` 을(를) 현재 파일에 적용했습니다."))
        _defer(msgs)
        st.rerun()

    st.caption("프리셋에 이 파일에 없는 파장이 있어도 프리셋은 그대로 유지됩니다 — "
               "다른 파일로 전환해 그대로 적용할 수 있습니다.")

    if st.button("이 프리셋 삭제", key=state.wkey("preset", "delete", fid=fid)):
        s["presets"].pop(sel, None)
        st.rerun()
