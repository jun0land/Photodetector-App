# 재작성 아키텍처 계획 (2026-07-17, 스파이크로 검증됨)

`SPEC.md` 가 요구사항의 기준, 이 문서가 **구현의 기준**. 충돌 시 SPEC 이 우선.

## 0. 검증된 환경 사실 (추측 아님 — 실제 스파이크/소스 확인)

| # | 사실 | 근거 |
|---|---|---|
| V1 | `components.v1.html` 의 deprecation 은 **제거가 아니라 `st.iframe` 으로의 rename**. 기능 동일. | `streamlit/components/v1/__init__.py:23-41` |
| V2 | **`st.html(body, unsafe_allow_javascript=True)`** 존재. **메인 문서에서 JS 실행** (iframe 아님). 단 인라인 `on*` 속성은 제거됨 → 핸들러는 스크립트 안에서 붙일 것. | `elements/html.py` |
| V3 | **`st.components.v2.component(name, html=, css=, js=, isolate_styles=)`** 존재. **양방향, iframe 아님, npm 불필요.** JS 는 ES 모듈 `export default function(component)`, `{data, parentElement, setStateValue, setTriggerValue}` 제공. | `components/v2/__init__.py` |
| V4 | `setStateValue`/`setTriggerValue` 는 항상 `{fromUi:true}` → **항상 rerun**. 조용한 set 은 없음. | `BidiComponent.*.js` |
| V5 | `default(component)` 는 **`data` 바뀔 때마다 재실행**. cleanup 은 unmount 시에만. **스파이크에서 오버레이 3개 중첩 누수 실측.** | 실측 |
| V6 | v2 컴포넌트 JS 가 메인 DOM 의 `st.plotly_chart` 를 찾아 조작 가능. `window.Plotly` 도 노출. | 실측 |
| V7 | **드래그 왕복 성공, rerun 루프 없음.** paper x0 0.6700 → 0.4027. t=0/2.5/5s 안정. | 스파이크 |
| V8 | `margin=0` 이면 `xref="paper"` 는 **페이지 전체**에 매핑 (축 영역 아님). | 실측 |
| V9 | `xref="x domain"`, `title.standoff`, `exponentformat="E"`, `minor=dict(dtick="D1")` 전부 유효. | plotly 6.9.0 |
| V10 | `st.plotly_chart(fig, width="content")` 가 figure 고유 960×768 존중. | 스파이크 |
| V11 | **10×8in 그래프는 뷰포트에 안 들어감.** `stMain` clientHeight=639, 그래프 768 필요. | 실측 |
| V12 | `st.container(key="x")` → `.st-key-x` 클래스. `height=N` 은 내부 스크롤. | 스파이크 |
| V13 | **`st.tabs` 는 모든 탭 body 를 매 run 실행** (클라 show/hide) → **탭 전환 rerun 0회**. | AppTest |
| V14 | 위젯 `persist_state=None` → **렌더 안 되면 값 소실**. | docstring |
| V15 | `plotly.min.js` (4.63MB) 가 venv 에 동봉. **현재 `include_plotlyjs="cdn"` 은 오프라인 HTML 내보내기를 깨뜨림** → `True` 로. | 실측 |
| V17 | `minCachedMessageSize=10000` → 인라인 CSS 는 첫 로드만 문제, 매 rerun 아님. | `forward_msg_cache.py:63` |

## 1. 모듈 분할

```
app.py                    # 얇은 진입점(~80줄). WP0 작성, WP9 마감. 그 외 접근 금지.
pd_app/
  constants.py            # WP0 이후 READ-ONLY
  parsing.py              # 원본 app.py 656-867 축자 이동. 로직 변경 금지.
  markup.py               # 원본 app.py 510-574 축자 이동. 로직 변경 금지.
  state.py                # 세션 스키마/접근자/위젯키. WP0 이후 READ-ONLY
  presets.py  figure.py  insets.py  theme.py
  ui/ layout.py panel_traces.py panel_axes.py panel_style.py
      panel_inset.py panel_presets.py toolbar.py summary.py
components/
  inset_drag/__init__.py  inset_drag/drag.js
  rich_toolbar/__init__.py  rich_toolbar/toolbar.js
.streamlit/config.toml
static/  liquid_bg.jpg  logo.png     # 정적 서빙 (base64 인라인 금지)
```

**축자 이동 규칙**: `parsing.py`/`markup.py` 는 복붙 이동이며 import 블록만 수정.
검증 게이트 = 보호 대상 9개 함수의 **AST 덤프 동일성 체크 통과** (코드 리뷰 아님).
보호 대상: `parse_file, _load_sheets, _parse_settings, _settings_frame, _sheet_sort_key,
_is_data_sheet, _parse_seq, _parse_token, apply_markup`.
`add_inset_legend` 는 보호 대상 **아님** — ref 가 바뀜(§4.3).

### 1.2 공개 시그니처 (WP0 이 고정, 나머지는 이것에 맞춰 코딩)

```python
# state.py
def boot() -> None
def S() -> dict
def add_file(name: str, data: bytes) -> FID      # sha1 dedupe; current_format 상속
def remove_file(fid) -> None
def active_fid() -> FID | None
def set_active(fid) -> None
def file_settings(fid) -> dict
def bump_rev() -> None
def wkey(group: str, name: str, *, fid=None) -> str
def tkey_of(trace: dict, occurrence: int) -> str   # f"{label}#{n}"

# presets.py
SCHEMA_VERSION = 1
def extract(fid, name) -> dict
def to_bytes(preset) -> bytes
def load(raw) -> tuple[dict, list[str]]          # 절대 raise 하지 않음
def apply_to(fid, preset) -> list[str]           # bump_rev() 호출
def apply_to_all(preset) -> list[str]

# figure.py
FIG_DPI = 96
def px_size(geom) -> tuple[int,int]              # (w_in*96, h_in*96)
def domains(geom) -> dict                        # {"x0","x1","y0","y1"}
def build_figure(fid, *, px_scale: float = 1.0) -> go.Figure

# insets.py
def inset_box(fid, which) -> dict
def add_inset_legend(fig, inset, plot_h_px) -> None
def add_sample_inset(fig, inset) -> None

# ui/*.py — 모든 패널이 정확히 이것만 노출
def render(ctx) -> None      # ctx = SimpleNamespace(fid, settings, traces, parsed, fig_px, domains)

# components/inset_drag/__init__.py
def inset_drag(*, items, domain, fig_px, epoch, key="pd_drag") -> dict | None   # {"id","x","y"}
```

## 2. 상태 스키마

```python
st.session_state["pd"] = {
  "version": 1,
  "files": {fid: {"fid","name","sha","bytes","added_at","settings"}},
  "order": [fid...], "active": fid|None,
  "rev": 0,                       # 위젯키 epoch
  "presets": {name: preset},
  "current_format": {...},        # 새 파일이 상속
}
```
**per-file = settings 전부. global = order/active/rev/presets/current_format.**

`FileSettings`: `traces{TKey: {label,visible,color,dash,width,legend_raw,inset_raw,include_in_inset}}`,
`geom{page_w_in:10.0,page_h_in:8.0,graph_left_pct:17.9,graph_top_pct:11.58,graph_width_pct:68.2,graph_height_pct:71.77}`,
`axes{x:{type,auto,min,max,dtick:0.5,minor_dtick,title_raw:"Voltage (V)",title_standoff},
      y:{type:"log",...,minor_dtick:"D1",title_raw:"Current (A)",title_standoff}}`,
`style{font_family,title_font_size:30,tick_font_size:30,line_width:2.0,show_markers,show_grid}`,
`insets{legend{x,y,xanchor,yanchor,width,border,...,font:None,font_size:30},
        sample{x:0.04,y:0.06,xanchor:"left",yanchor:"bottom",text_raw,font_size:30}}`,
`use_abs: True`.
`font: None` = `style.font_family` 상속.

### 2.3 위젯키 — 두 가지 함정, 둘 다 해결

```python
def wkey(group, name, *, fid=None):
    return f"w:{S()['rev']}:{fid or '__global__'}:{group}:{name}"
```
- **함정1 파일 전환 시 값 누출** → 키에 `fid` 포함으로 해결.
- **함정2 `value=` 무시** (키가 이미 있으면 Streamlit 이 `value=` 무시) → **프리셋 적용해도 UI 가 안 바뀜.**
  → `presets.apply_to()` 가 `bump_rev()` 호출 → 모든 키가 새것 → `value=` 반영.
  구 rev 키는 **V14** 로 자동 GC.
- `bump_rev()` 호출 시점: **프리셋 적용 / 전체 적용 / 기본값 리셋** 뿐. 파일 전환·드래그에서는 호출 안 함.
- **모델이 유일한 진실.** 패널은 read-render-writeback:
  `tr["color"] = st.color_picker("선 색상", value=tr["color"], key=wkey("trace", f"{tk}.color", fid=fid))`

### 2.4 파장이 다른 파일로 전환
파일마다 자기 TKey 로 자기 settings 를 가짐 → **조정할 게 없음**. 전달은 두 시점만:
`add_file` 시 `current_format` 상속(label 로 시드), 프리셋 적용 시(§3.3).

## 3. 프리셋 스키마

```json
{"schema":"photodetector-app/format","version":1,"name":"...","created_at":"...",
 "traces_by_label":{"Dark":{"color":"#000000","dash":"solid","width":2.0}},
 "axes":{"x":{"type","auto","min","max","dtick","minor_dtick","title_standoff"},"y":{...}},
 "insets":{"legend":{"x","y","xanchor","yanchor","width","border",...},"sample":{"x","y","xanchor","yanchor","font_size"}},
 "style":{"font_family","title_font_size","tick_font_size","line_width"},
 "geom":{"page_w_in","page_h_in","graph_left_pct","graph_top_pct","graph_width_pct","graph_height_pct"}}
```
E1 매핑: 인셋 위치→`insets.*.{x,y,xanchor,yanchor}` · 파장별 색상→`traces_by_label.*.color` ·
선 두께→`.width`+`style.line_width` · XY축 스케일→`axes.*.{type,dtick,min,max,auto}` · 축 제목 위치→`axes.*.title_standoff`.

**제외**: `visible`(데이터 선택이지 포맷 아님), `legend_raw`/`inset_raw`/`sample.text_raw`(파일별 텍스트).

**매칭 = label 기준** (TKey 아님 — 파일마다 occurrence 다름).
- label 이 N>1 회 등장(`Dark#1`,`Dark#2`) → **전부 같은 항목 적용** (현행 동작과 동일).
- 프리셋에 없는 트레이스 → `DEFAULT_TRACE_COLORS[label]` → `FALLBACK_CYCLE[i%len]`. **절대 무스타일로 두지 않음.** 경고 없음(정상 경로).
- 프리셋에만 있는 label → 무시. **프리셋 dict 는 apply 로 변형되지 않음** → 다음 파일에서 살아있음. 안내 1줄.
- `load()` 는 **절대 raise 안 함**: schema 불일치/버전 상위 → 경고 후 best-effort. 하위 → `_MIGRATIONS` 체인.
  누락키 → `constants.DEFAULTS` 로 조용히 채움. 미지의 키 → 버리고 경고 1회. 타입/범위 위반 → coerce 후 clamp(6~50, width 0.5).

## 4. 드래그 컴포넌트 (D4)

### 4.1 결정: **`st.components.v2.component`** (v1 `declare_component` 아님)
SPEC D4 의 전제(“st.plotly_chart 는 relayout 을 안 돌려줌”)는 **맞음**. 하지만 결론(“postMessage 직접 구현”)은 **V3 로 불필요해짐**.
v1 은 **iframe 이라 차트에 물리적으로 접근 불가** → figure 를 컴포넌트 안에서 다시 그려야 하고 plotly.js 4.63MB 동봉 + pyarrow 필요. v2 는 이 문제가 통째로 사라짐.

### 4.2 결정: **기존 `st.plotly_chart` 를 오버레이** (컴포넌트 안에서 figure 를 그리지 않음)
- `st.plotly_chart` 온전히 유지 → 모드바, PNG scale:3, `width="content"` 960×768 그대로.
- **파이썬이 figure 의 유일한 진실.** 컴포넌트는 “어디에 놓았는지”만 보고함 = **두 float 를 위한 순수 입력 장치.**
- 컴포넌트는 파이썬이 이미 아는 geometry 로 투명 히트박스만 그림. Plotly 내부 SVG 파싱 안 함.
  유일한 결합: `document.querySelector('.stPlotlyChart .js-plotly-plot')` + `getBoundingClientRect()`.

### 4.3 좌표 매핑: **인셋 ref 를 `paper` → `x domain`/`y domain` 으로 변경**
**V8** 로 `margin=0` 이면 paper = 페이지 전체 → paper(0.97,0.97) 은 축 밖 페이지 구석. B1 의 Left/Top 건드릴 때마다 어긋남. `x domain` 은 플롯 영역 기준 = Origin 이 하는 것 = 예시 이미지 그대로.
`add_inset_legend` 시그니처/본문 형태 유지, ref 와 호출 인자만 변경:
```python
dom = domains(geom); _, fig_h = px_size(geom)
plot_h_px = (dom["y1"] - dom["y0"]) * fig_h     # margin 박스가 아니라 domain 박스 기준
insets.add_inset_legend(fig, inset, plot_h_px)
```
컴포넌트 수식 (FIG_W/FIG_H 불필요 — 약분됨):
```js
const r = gd.getBoundingClientRect();
const vx = r.left + (d.x0 + x_dom*(d.x1-d.x0)) * r.width;
const vy = r.top  + (1 - (d.y0 + y_dom*(d.y1-d.y0))) * r.height;
const dx_dom =  dx / (r.width  * (d.x1-d.x0));
const dy_dom = -dy / (r.height * (d.y1-d.y0));
```
두 항이 **같은 측정 rect 의 비율**이라 CSS transform/zoom/DPR(1.25) 에 불변 → §5.5 스케일링과 안전하게 공존. `[-0.15,1.15]` clamp, 4dp 반올림.

### 4.4 멱등성 (V5 — 실측된 필수 규칙)
1. **안정 id 로 재사용**: `let layer = parentElement.querySelector('#pd-drag-layer') ?? create()`, 그 다음 `layer.innerHTML=''`. 맹목적 append 금지.
2. **property 핸들러만** (`el.onmousedown=`, `window.onmousemove=`). **bare `addEventListener` 금지**(중첩됨). 불가피하면 `AbortController` 를 layer 노드에 저장 후 `default()` 최상단에서 abort.
3. **`document.body` 에 append 금지** (unmount 후 생존). `parentElement` 안에 만들고 `position:fixed`.
4. unmount 용 cleanup 은 그래도 반환.

### 4.5 rerun 루프 방지 — 정확한 불변식
> **`setStateValue` 는 오직 `mouseup` 핸들러 한 곳에서만 호출. `default()` 는 절대 값을 내보내지 않는다.**
1. 제스처 전용 방출 → `data→default()→setStateValue→rerun→data` 사이클에 되돌아오는 간선이 없음.
2. 라이브 프리뷰는 `layer.style.transform` 만 (파이썬 왕복 0, 60fps).
3. 데드존: `dx²+dy² > 4` 아니면 방출 안 함 (단순 클릭은 rerun 유발 안 함).
4. 동등 래치: 4dp 반올림 후 파이썬이 보낸 값과 같으면 skip.
드래그는 `bump_rev()` 호출 **안 함**.

### 4.7 폴백 (이게 진짜 안전장치)
> **WP2 가 수동 UI 를 먼저 만든다. WP8(드래그)은 마지막이고 그 UI 를 *교체*할 뿐.
> WP8 시작 전에 앱은 이미 출하 가능해야 한다.**
수동 UI: 3×3 앵커 `st.segmented_control` (9개 정위치, 실사용 90% 커버) + `st.number_input` X/Y 미세조정.
**같은** `settings["insets"][which]["x"/"y"]` 에 씀 → 프리셋/figure/export 가 어느 쪽이든 동일.
자동 폴백 조건: `st.components.v2` import 실패 / 마운트 후 2회 연속 `None` / `.js-plotly-plot` 못 찾음.

## 5. 레이아웃 (G1/G6 — 최우선 가치)

```
[logo] Photodetector I-V Viewer            [ ＋ 파일 추가 ▾ ]   ~64px  G2
( 파일1 ) ( 파일2 ) ( 파일3 )                            [✕]   ~40px  F2
┌── st.columns([5,11], gap="medium", vertical_alignment="top") ──┐
│ [트레이스][축][서식][인셋][포맷]  │      그래프 960×768         │
│  st.container(height=<viewport>, │      CSS 로 축소 표시       │
│    key="pd_edit_panel")          │  (내보내기는 정확히 10×8in) │
└──────────────────────────────────┴─────────────────────────────┘
```

**좌측 = `st.tabs`.** 이유: expander 스택은 높이가 **열린 섹션의 합** → 무한정 커져 G1 이 금지한 스크롤 강제.
**탭은 높이가 `max(섹션)`** → 그룹 수에 O(1). **V13** 으로 **탭 전환 rerun 0회** (파이썬 왕복/그래프 재그리기/깜빡임 없음).
Origin 자체가 탭형 Plot Details 라 메타포도 익숙 ("안 그러면 오리진 쓰지").

| 탭 | 내용 |
|---|---|
| 트레이스 | 트레이스 on/off (**D5** — 레전드 밖), 색, dash, 레전드 텍스트 |
| 축 | X/Y 스케일·범위, major `dtick`, minor `dtick` (**A4/A6**), 제목 텍스트+standoff (**B2**) |
| 서식 | 폰트(**C1**), 크기 number_input 스테퍼(**C2/C3**), 선 두께 0.5 (**C4**), 배경/그래프 geometry(**B1**) |
| 인셋 | rows/텍스트(**D2/D3**) + §4.7 위치 폴백 |
| 포맷 | 프리셋 저장/불러오기/전체적용 (**E1/E2**) |

**파일 배너 = `st.segmented_control`** (`st.tabs` 아님). **V13** 이 여기선 역효과 — 모든 파일의 패널 body 를 매 run 실행하게 되어 위젯키 폭발. `segmented_control` 은 활성 파일만 렌더. 파일 전환은 어차피 rerun 필요하므로 손해 없음.

**G2+G3 한 수로 해결**: `st.file_uploader` 를 `st.popover("＋ 파일 추가")` 안에 넣고 `st.columns([6,1])` 로 우측 정렬.
→ G2 충족 + **G3(여백 클릭 시 파일창) 자체가 소멸** (드롭존이 화면에 없음).
**C5**: 탭으로 분리 + §5.5 높이 바인딩으로 해결. ⚠️ 스파이크에서 **C5 재현됨**: 639px 뷰포트에 `st.container(height=768)` 이면 컨테이너 하단 129px 이 영구히 화면 밖.
→ **패널 높이는 반드시 측정된 뷰포트에 바인딩. 768 하드코딩 금지.**
**G5**: `app.py:304`, `app.py:312` 의 `<code>[]</code>` → `<code>[ ]</code>`.

### 5.5 뷰포트 바인딩 (rerun 0회)
**V2** (`st.html(..., unsafe_allow_javascript=True)`) 사용 — 단방향, 값 불필요 → 컴포넌트도 rerun 도 없음.
`theme.py` 에서 1회 설치: `[data-testid="stMain"]` 에 `ResizeObserver` → CSS 변수 기록.
```js
const avail = m.clientHeight - 120;
root.style.setProperty('--pd-panel-h', avail+'px');
root.style.setProperty('--pd-graph-scale', Math.min(1, avail/768, stageW/960).toFixed(4));
```
```css
.st-key-pd_edit_panel { height: var(--pd-panel-h, 520px) !important; }
.st-key-pd_graph_stage > div { transform: scale(var(--pd-graph-scale,1)); transform-origin: top left; }
.st-key-pd_graph_stage { height: calc(768px * var(--pd-graph-scale,1)); }
```
⚠️ **WP5 필수 테스트**: `transform: scale` 이 plotly hover 히트테스트를 어긋나게 할 수 있음.
scale≈0.68 에서 데이터 점 hover → 툴팁이 커서에 붙는지 확인. **실패 시** `build_figure(fid, px_scale=s)` 로 figure 자체를 축소 렌더(폰트 비례 축소), 내보내기는 `px_scale=1.0` 별도 생성. (그래서 시그니처에 `px_scale` 이 있음.)

## 6. 작업 순서

```
WP0 (직렬, 블로킹) → {WP1..WP7 병렬} → WP9 (직렬) → WP8 (마지막)
```
| WP | 배타적 소유 | 의존 |
|---|---|---|
| **WP0** | `app.py`, `constants.py`, `state.py`, `parsing.py`, `markup.py`, 전 스텁 시그니처 | — |
| WP1 | `figure.py` | WP0 |
| WP2 | `insets.py`, `ui/panel_inset.py` | WP0 |
| WP3 | `ui/panel_traces.py`, `ui/panel_axes.py`, `ui/panel_style.py` | WP0 |
| WP4 | `presets.py`, `ui/panel_presets.py` | WP0 |
| WP5 | `ui/layout.py`, `theme.py`, `.streamlit/config.toml`, `static/` | WP0 |
| WP6 | `components/rich_toolbar/*`, `ui/toolbar.py` | WP0 |
| WP7 | `ui/summary.py` | WP0 |
| WP9 | `app.py` 최종 배선, 매뉴얼 | 전부 |
| WP8 | `components/inset_drag/*` | WP1,2,5,9 |

**충돌 방지**: `constants.py`/`state.py` 는 WP0 이후 read-only. `ui/layout.py` 는 WP5 단독 소유(패널은 `render(ctx)` 만 구현).
**모든 CSS 는 WP5/`theme.py` 단독** — 다른 WP 는 `st.markdown("<style>")` 호출 금지, 클래스 훅만 요청.
`figure.py`/`insets.py` 는 WP1/WP2 충돌 방지용으로 일부러 분리.

## 7. 겸사겸사 고칠 기존 버그

| 위치 | 문제 | 수정 | WP |
|---|---|---|---|
| `app.py:1156` | `include_plotlyjs="cdn"` → **오프라인에서 HTML 내보내기 깨짐** (실험실 PC) | `include_plotlyjs=True` (V15) | WP7 |
| `app.py:399-425` | `apply_ui_zoom` 의 `body.style.zoom`. **NBEDL `app.py:415-439` 에 이미 고친 버전 있음** — photodetector 에 옛 버전이 들어옴. 게다가 1.067배로 **확대**해서 V11 을 악화. | NBEDL 버전 포팅 + §5.5 높이 바인딩으로 구동 | WP5 |
| `liquid_bg.png` 8.9MB → 인라인 11.9MB | **Raman `app.py:140-156` 이 이미 해결**: 1600² JPEG 117KB + **정적 서빙**(`app/static/`, 인라인 페이로드 0). V17 상 첫 로드만 문제이나 첫 로드가 곧 체감 속도. | Raman 방식 그대로 재사용 | WP5 |
| `requirements.txt` | pyarrow 없음, 핀 없음 | `streamlit==1.59.2`, `plotly==6.9.0`, pyarrow 핀 | WP0 |
| `app.py:936-942` | zero-width-space 레전드 유니크화 — D1 로 레전드 제거되면 **죽은 코드** | 삭제 | WP1 |

## 8. SPEC 의 문제점과 권고 (사용자 확인 필요 표시된 것)

### 8.1 ⚠️ **B1 vs G1/G6 실측 충돌** — 가장 중요
**B1** 은 그래프를 10×8in = **768px** 로 고정. **V11** 상 가용 뷰포트 **639px**. **컨트롤 하나 놓기 전에 그래프만으로 이미 안 들어감.**
→ **권고: 표시 크기와 내보내기 크기를 분리.** figure 는 정확히 960×768 로 만들고(내보내기·PNG scale3·HTML 은 정확히 10×8in 유지), **표시만** `s=min(1, avail_h/768, avail_w/960)`≈0.68 로 CSS 축소.
전부 균일 축소라 WYSIWYG 유지, 내보내기 무손상, 스크롤 소멸. 드래그 수식은 §4.3 에서 이미 스케일 불변.
**사용자에게 명확히 알릴 것: 화면의 그래프는 10×8인치가 아니라 비례 축소된 미리보기다.** 1:1 을 고집하면 스크롤을 받아들여야 함. 639px 뷰포트에서 둘 다는 불가능.

### 8.2 A2 — 판정 필요
`Y_TITLE_ABS` 와 제목 연동 제거는 명확. 불명확: **Linear 에서 `절댓값 (|I|)` 체크박스는 남기나?**
→ **권고: 남긴다.** Log 는 `use_abs=True` 강제(현행), Linear 는 사용자 선택, Y 제목은 **항상** `"Current (A)"` 기본이며 자유 편집. A2 가 실제로 요구하는 *제목* 결합만 제거.

### 8.3 A5 를 Y축에 그대로 적용하면 실망함
A5 는 **X** 에 대해 옳음(예시의 곡선이 ±1.0 에서 프레임에 닿음).
**Y(log)** 에 그대로 적용하면 원시 데이터 극값(3.7E-12 → 6.2E-7)으로 잘려 **너덜너덜한 비-decade 경계**. **예시 이미지는 Y 가 1E-11…1E-5 로 깔끔히 decade 스냅.**
→ **권고: X auto = 데이터 min/max 정확히, 패딩 0. Y(log) auto = decade 경계로 바깥쪽 스냅** (`floor/ceil(log10)`). Y linear auto = 정확히 min/max.

### 8.4 G4 툴바는 상상과 다를 것 — WP6 전 알릴 것
G4 는 “오리진식 WYSIWYG 툴바” + “`apply_markup` 은 내부 표현 유지”를 동시에 요구 → 긴장 관계.
진짜 WYSIWYG 은 **DOM→마크업 직렬화기**(중첩 span, 부분 선택, deprecated `execCommand`)가 필요하고 거기서 버그가 나며 검증된 파서의 입력을 오염시킬 위험.
→ **권고: `<input>` 을 감싼 v2 컴포넌트. 버튼이 `selectionStart/End` 로 선택 영역을 감쌈.**
`선택 → **B**` ⇒ `**선택**` · `→ x²` ⇒ `^{선택}` · `→ 색` ⇒ `{#FF0000|선택}`. blur/Enter 에 커밋.
**렌더 미리보기 칩**(`st.html(apply_markup(raw))`) 을 옆에 붙여 결과를 즉시 보여줌.
G4 가 묘사한 상호작용("텍스트 선택 후 적용")을 그대로 제공하고 파서도 안 건드림.
**편차: 입력칸은 렌더된 텍스트가 아니라 마크업 소스를 보여줌.** 여기만 "오리진식" 과 다르게 느껴질 것.

### 8.5 E1 의 저장 범위가 "통일감" 에 비해 좁음
파일 A 에 Pretendard 32pt 를 걸고 프리셋을 B 에 적용하면 **폰트는 안 따라감** → B 는 Arial 30 으로 복귀. E2 목표에 비추면 버그로 읽힘.
→ **권고: E1 항목은 필수로 두고 `style`+`geom` 을 선택 블록으로 추가.** 저장 UI 에 `[✓] 폰트·크기도 함께 저장` / `[✓] 페이지·그래프 크기도 함께 저장`, 둘 다 기본 켜짐.

### 8.7 H1 (Responsivity/Detectivity) — 범위 밖, 설계 안 함
나중에 다룰 때 **식은 반드시 사용자 확인 후** 사용. 추론 금지. 지금 지불하는 유일한 호환 비용: `presets.py` 의 `version` + `_MIGRATIONS` 체인(추가만으로 대응 가능).

### 8.8 사소한 관찰
예시 이미지 레전드는 **740 nm** 인데 `SYMBOL_MAP` 은 `6 → 785nm`. 심볼맵은 SPEC 의 불가침 목록이고 레전드 텍스트는 트레이스별 편집 가능하므로 코드 변경 불필요. 다만 사용자가 `6` 을 740nm 로 여긴다면 상수 한 줄 확인 필요. **보고만 함.**
