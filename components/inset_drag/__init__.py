"""인셋 드래그 컴포넌트 (D4). 소유: WP8 — **마지막 WP**.

PLAN §4. `st.components.v2.component` 사용 (v1 `declare_component` 아님 — v1 은 iframe
이라 차트에 물리적으로 접근 불가).

§4.2 기존 `st.plotly_chart` 를 **오버레이**한다. 컴포넌트 안에서 figure 를 다시 그리지
않는다. 파이썬이 figure 의 유일한 진실이고, 컴포넌트는 "어디에 놓았는지"만 보고하는
**두 float 를 위한 순수 입력 장치**. Plotly 내부 SVG 파싱 안 함. 유일한 결합:
`document.querySelector('.stPlotlyChart .js-plotly-plot')` + `getBoundingClientRect()`.

§4.4 멱등성 (V5 — 실측된 필수 규칙):
 1. 안정 id 로 재사용: `layer = parentElement.querySelector('#pd-drag-layer') ?? create()`,
    그 다음 `layer.innerHTML=''`. 맹목적 append 금지.
 2. property 핸들러만 (`el.onmousedown=`). bare `addEventListener` 금지(중첩됨).
 3. `document.body` 에 append 금지. `parentElement` 안에 만들고 `position:fixed`.
 4. unmount 용 cleanup 은 그래도 반환.

§4.5 rerun 불변식: **`setStateValue` 는 오직 `mouseup` 핸들러 한 곳에서만 호출.
`default()` 는 절대 값을 내보내지 않는다.** 라이브 프리뷰는 `layer.style.transform` 만.
데드존 `dx²+dy² > 4`, 4dp 반올림 동등 래치. 드래그는 `bump_rev()` 를 호출하지 않는다.

§4.7 폴백: WP2 의 수동 위치 UI 가 먼저 출하되고 이 컴포넌트는 그것을 *교체*할 뿐이다.
자동 폴백 조건: `st.components.v2` import 실패 / 마운트 후 2회 연속 `None` /
`.js-plotly-plot` 못 찾음.
"""

from __future__ import annotations


def inset_drag(*, items, domain, fig_px, epoch, key="pd_drag") -> dict | None:
    """인셋 드래그 오버레이. 제스처 시 {"id","x","y"}, 아니면 None. WP8 구현."""
    raise NotImplementedError
