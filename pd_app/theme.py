"""전역 테마: CSS + 정적 에셋 + 뷰포트 바인딩. 소유: WP5.

**모든 CSS 는 이 파일 단독 소유** (PLAN §6). 다른 WP 는 `st.markdown("<style>")` 를
호출하지 말고 클래스 훅만 요청할 것.

여기서 해결하는 것:

- **정적 에셋** (PLAN §7, Raman `app.py:140-156` 방식 그대로): 4096² PNG 8.9MB 를
  base64 로 인라인하면 CSS 페이로드가 11.87MB. 1600² JPEG(117KB)로 줄이고
  `static/` 정적 서빙으로 옮겨 **인라인 페이로드 0B** + 브라우저 캐시.
  V17(minCachedMessageSize=10000) 상 인라인 CSS 는 매 rerun 이 아니라 **첫 로드**만
  문제였다 — 즉 이건 첫 로드 개선이다. 다만 첫 로드가 곧 사용자가 느끼는 속도다.
- **zoom 버그** (PLAN §7): 옛 `apply_ui_zoom` 은 `doc.body.style.zoom` 을 건드려
  Streamlit 의 100vh 레이아웃과 충돌했고, 게다가 1.067배로 **확대**해 V11 을 악화시켰다.
  NBEDL `app.py:429-465` 의 style-rule 방식을 포팅하되 **MAX 를 1.0 으로 클램프**한다
  (§5.5 높이 바인딩이 zoom 을 나눠 보정하므로 두 기능이 한 계산에 묶여 있다).
- **뷰포트 바인딩** (PLAN §5.5): V2 `st.html(..., unsafe_allow_javascript=True)` —
  단방향이라 컴포넌트도 rerun 도 없다. `ResizeObserver` 가 CSS 변수만 쓴다.
  ⚠️ V2 는 인라인 `on*` 속성을 제거하므로 핸들러는 스크립트 안에서 붙인다.
  ⚠️ 패널 높이는 반드시 **측정된** 뷰포트에 바인딩 — 768 하드코딩 금지 (C5 재현됨).

`install()` 은 **멱등하게 구성**되어 있다 (drawer/zoom/observer 모두 remove-then-recreate
또는 플래그 가드). app.py(WP9)와 layout 양쪽에서 불려도 안전하다.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from pd_app.constants import ACCENT, ORIGIN_COLORS

# 트레이스 색상 팔레트: 위치(nth-child)→색 매핑을 constants.ORIGIN_COLORS 순서로 생성한다.
# (값에 CSS 중괄호가 들어가므로 _CSS f-string 에는 이 문자열을 필드로 통째 삽입한다.)
_PALETTE_SWATCH_RULES = "".join(
    f'[class*="st-key-pd_palette_"] [data-testid="stElementContainer"]'
    f":nth-child({i}) button {{ background:{hx} !important; }}\n"
    for i, hx in enumerate(ORIGIN_COLORS.values(), start=1)
)

APP_DIR = Path(__file__).resolve().parent.parent

# Streamlit 정적 서빙 경로 (앱 루트 기준 상대 URL). base64 인라인 금지.
_STATIC = "app/static"
_BG_URL = f"{_STATIC}/liquid_bg.jpg"
_LOGO_URL = f"{_STATIC}/logo.png"

# 에셋이 없으면 배경 없이 그라데이션으로 우아하게 폴백한다.
_HAS_BG = (APP_DIR / "static" / "liquid_bg.jpg").exists()
_HAS_LOGO = (APP_DIR / "static" / "logo.png").exists()

_BG_LAYER = (
    f"linear-gradient(rgba(255,255,255,0.72), rgba(255,255,255,0.82)), url('{_BG_URL}')"
    if _HAS_BG else
    "linear-gradient(135deg, #fdf0ec 0%, #f7f7fb 100%)"
)


def logo_url() -> str | None:
    """헤더 로고 URL. 에셋이 없으면 None (레이아웃이 로고를 생략한다)."""
    return _LOGO_URL if _HAS_LOGO else None


# ===========================================================================
# CSS
# ===========================================================================
_CSS = f"""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');

html, body, [class*="css"], .stApp, button, input, textarea, select {{
    font-family: 'Myriad Pro', 'Pretendard', 'Nanum Gothic', -apple-system, sans-serif !important;
}}

.stApp {{
    background: {_BG_LAYER};
    background-size: cover;
    background-attachment: fixed;
    background-position: center;
    color: #1c1c1e;
}}

/* 컨테이너 투명화 */
[data-testid="stHeader"], [data-testid="stToolbar"] {{ background: transparent !important; }}
[data-testid="stAppViewContainer"], .main .block-container {{ background: transparent !important; }}

/* 밀도: 기본 상단 여백(~6rem)이 과해서 한 화면 정보량을 깎는다.
   G1(스크롤 최소화)이 최우선이므로 세로 여백을 특히 줄인다. */
.main .block-container, [data-testid="stAppViewContainer"] .block-container {{
    padding-top: 4rem !important;
    padding-bottom: 0.6rem !important;
    padding-left: 1.6rem !important;
    padding-right: 1.6rem !important;
    max-width: 100% !important;
}}

/* Glassmorphism */
[data-testid="stForm"],
[data-testid="stExpander"],
[data-testid="stPopoverBody"],
.pd-title-glass {{
    background: rgba(255,255,255,0.15);
    backdrop-filter: blur(48px) saturate(150%);
    -webkit-backdrop-filter: blur(48px) saturate(150%);
    border: 1px solid rgba(255,255,255,0.35);
    border-radius: 20px;
    box-shadow: 0 12px 32px rgba(0,0,0,0.05);
    padding: 20px 22px;
}}

/* 세로 간격 압축 (G1) */
[data-testid="stAppViewContainer"] [data-testid="stVerticalBlock"] {{ gap: 0.5rem !important; }}

/* ---------------- 헤더 (~64px, G2) ---------------- */
.pd-title-glass {{
    display: flex; align-items: center; gap: 14px;
    flex-wrap: nowrap;
    border-left: 6px solid {ACCENT};
    padding: 10px 20px;
    margin: 0;
}}
.pd-title-glass img {{ height: 40px; width: auto; flex-shrink: 0; }}
.pd-title-glass h2 {{
    margin: 0; padding: 0; font-weight: 800; color: #1c1c1e;
    font-size: 1.45rem;
    letter-spacing: -0.5px; line-height: 1.15; white-space: nowrap;
    text-shadow: none;
}}
/* 업로드 popover 를 헤더 높이에 맞춰 우측 정렬 (G2) */
.st-key-pd_upload {{ display: flex; justify-content: flex-end; align-items: center; height: 100%; }}
.st-key-pd_upload [data-testid="stPopover"] button {{ white-space: nowrap; }}

/* 파일 업로더: 드롭존은 popover 안에만 존재한다.
   G3(여백 클릭 시 파일창)은 드롭존이 화면에 상주하지 않으므로 구조적으로 소멸. */
[data-testid="stFileUploader"] section {{
    background: rgba(255,255,255,0.25);
    border: 2px dashed {ACCENT};
    border-radius: 16px;
}}

/* ---------------- 파일 배너 (~40px, F2) ---------------- */
.st-key-pd_banner [data-testid="stSegmentedControl"] button {{
    border-radius: 12px !important;
    font-weight: 600;
}}

/* ---------------- 좌: 편집 패널 ----------------
   ⚠️ C5: 639px 뷰포트에 height:768px 컨테이너를 두면 하단 129px 이 영구히 화면 밖으로
   나가 마지막 컨트롤의 드롭다운을 열 수 없다. 높이는 **측정된** 뷰포트에 바인딩한다.
   --pd-panel-h 는 §5.5 의 ResizeObserver 가 쓴다. 520px 는 JS 이전의 안전한 폴백일 뿐. */
.st-key-pd_edit_panel {{
    height: var(--pd-panel-h, 520px) !important;
    background: rgba(255,255,255,0.18);
    backdrop-filter: blur(48px) saturate(150%);
    -webkit-backdrop-filter: blur(48px) saturate(150%);
    border: 1px solid rgba(255,255,255,0.35);
    border-radius: 20px;
    box-shadow: 0 12px 32px rgba(0,0,0,0.05);
    padding: 10px 14px 14px;
}}
.st-key-pd_edit_panel [data-testid="stTabs"] [data-baseweb="tab-list"] {{
    gap: 2px;
    background: transparent;
}}
.st-key-pd_edit_panel [data-baseweb="tab"] {{
    padding: 6px 10px !important;
    font-weight: 700;
}}
.st-key-pd_edit_panel [aria-selected="true"] {{ color: {ACCENT} !important; }}

/* ---------------- 우: 그래프 스테이지 ----------------
   ⚠️ CSS transform: scale() 방식은 폐기했다. transform 컨테이너 안에서 plotly.js 가
   자기 크기를 **축소된 rect** 로 오측정(344×460)해 X축 눈금 라벨을 세로로 회전·겹치게
   렌더했다 (streamlit 1.59.2 / plotly 6.9.0, responsive:False·width=content 로도 못 막음).
   대신 figure 를 **px_scale 로 네이티브 축소**해서 빌드한다 (layout `_graph_stage`) —
   plotly 가 s*960 × s*768 를 정상 레이아웃하므로 라벨이 수평으로 나온다. 여기엔
   transform 도 height/width calc 도 없다. 측정 ResizeObserver 루프(busy 원인)도 제거됨.
   export/PNG/HTML 은 항상 px_scale=1.0 별도 figure → 정확히 960×768=10×8in. */
/* SPEC A7: 그래프는 논문용 — 흰 배경 고정. 절대 glass·투명화 금지. */
.st-key-pd_graph_stage [data-testid="stVerticalBlockBorderWrapper"],
.st-key-pd_graph_stage [data-testid="stPlotlyChart"] {{
    background: transparent;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
    box-shadow: none !important;
    border: none !important;
}}
.st-key-pd_graph_stage .js-plotly-plot {{
    background: #FFFFFF;
    border-radius: 8px;
    box-shadow: 0 12px 32px rgba(0,0,0,0.10);
}}

/* ---------------- 입력/버튼 ---------------- */
[data-baseweb="select"] > div, .stNumberInput input, .stTextInput input {{
    background: rgba(255,255,255,0.35) !important;
    border-radius: 10px !important;
}}
.stButton > button, .stDownloadButton > button {{
    background: rgba(255,255,255,0.35);
    border: 1px solid rgba(255,255,255,0.5);
    border-radius: 12px; font-weight: 600; color: #1c1c1e;
    transition: all 0.18s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
    transform: translateY(-2px);
    border-color: {ACCENT}; color: {ACCENT};
    box-shadow: 0 6px 18px rgba(237,84,43,0.18);
}}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
    background: linear-gradient(135deg, {ACCENT}, #f68b21);
    color: white; border: none;
}}
.stButton > button[kind="primary"]:hover {{ color: white; opacity: 0.94; }}

/* 마크업 안내문: 작고 흐린 회색으로 조용하게 */
.mk-help {{
    display: block; font-size: 0.78rem; color: #8a8a8f;
    line-height: 1.5; margin: 2px 0 8px;
}}
.mk-help code {{
    background: rgba(237,84,43,0.08); color: #a85a42;
    padding: 0 3px; border-radius: 4px;
}}

/* ── 트레이스 색상 선택: 현재 색 스와치 → 클릭 시 24색 팔레트 popover ── */
/* 현재 색 트리거 스와치: 30px 정사각형. 배경색(=현재 색)은 panel_traces 가 per-trace 주입 */
[class*="st-key-pd_sw_"] [data-testid="stPopover"] button {{
    width: 30px !important; height: 30px !important; min-height: 30px !important;
    padding: 0 !important; border-radius: 6px !important;
    border: 1px solid rgba(0,0,0,0.35) !important;
    color: transparent !important;
}}
/* 팔레트 그리드: 6열 × 4행(+Custom), 각 칸 30px 정사각형.
   st.container(key) 의 st-key 가 BorderWrapper 에 붙어 자손 stVerticalBlock 을 grid 로
   만드는 경우와, st-key 가 stVerticalBlock 자체에 붙는 경우 둘 다 커버한다. */
[class*="st-key-pd_palette_"] [data-testid="stVerticalBlock"],
[class*="st-key-pd_palette_"][data-testid="stVerticalBlock"] {{
    display: grid !important;
    grid-template-columns: repeat(6, 30px) !important;
    gap: 6px !important;
    justify-content: start !important;
}}
/* grid item(버튼 컨테이너)이 100% 폭을 강제해 1열로 무너지지 않게 30px 로 고정 */
[class*="st-key-pd_palette_"] [data-testid="stElementContainer"] {{
    width: 30px !important; min-width: 30px !important;
}}
[class*="st-key-pd_palette_"] [data-testid="stElementContainer"] button {{
    width: 30px !important; height: 30px !important; min-height: 30px !important;
    padding: 0 !important; border-radius: 6px !important;
    border: 1px solid rgba(0,0,0,0.25) !important;
    color: transparent !important;   /* 색칸 빈 라벨 숨김 */
    transform: none !important;       /* 공통 버튼 hover 의 들썩임 제거 */
}}
{_PALETTE_SWATCH_RULES}
/* 25번째 칸 = Custom: 회색 배경 + 가운데 흰 "C" */
[class*="st-key-pd_palette_"] [data-testid="stElementContainer"]:nth-child(25) button {{
    background: #808080 !important;
    color: #FFFFFF !important; font-weight: 800;
}}
/* Custom 선택 시 나타나는 color_picker 스와치 — 30px 정사각형 + 좌측 정렬 */
[data-testid="stColorPickerBlock"] {{
    width: 30px !important;
    height: 30px !important;
    min-width: 30px !important;
    min-height: 30px !important;
    aspect-ratio: 1 / 1 !important;
    border-radius: 6px !important;
}}
[data-testid="stColorPicker"] {{
    display: flex;
    align-items: center;
    justify-content: flex-start;
}}
/* 👇 추가: 컬러 피커 내부 컨테이너의 불필요한 높이/여백 제거 */
[data-testid="stColorPicker"] > div {{
    min-height: 30px !important;
    padding: 0 !important;
}}

/* 트레이스 행 "표시" 체크박스: 숨은 마진 제거 및 강제 중앙 정렬 */
[data-testid="stCheckbox"] {{ 
    display: flex; align-items: center; 
    min-height: 38px !important; /* 옆에 있는 selectbox 높이(38px)에 완벽 동기화 */
    margin: 0 !important; padding: 0 !important;
}}
[data-testid="stCheckbox"] label {{ 
    display: flex !important; align-items: center !important; 
    min-height: 38px !important; margin: 0 !important; padding: 0 !important;
}}
/* 👇 핵심: 체크박스 네모 상자 위쪽에 Streamlit이 몰래 넣는 마진 제거 */
[data-testid="stCheckbox"] label > div:first-child {{
    margin-top: 0 !important;
}}

h1, h2, h3, h4, p, label, span {{ text-shadow: none; }}
</style>
"""


# ===========================================================================
# 매뉴얼 드로어 + zoom + 뷰포트 바인딩 (V2: 메인 문서에서 실행, iframe 아님)
# ===========================================================================
# 레거시는 components.html(iframe) 안에서 window.parent.document 를 더듬어야 했다.
# V2 의 st.html(unsafe_allow_javascript=True) 는 **메인 문서에서** 실행되므로
# parent 접근도 cross-origin try/catch 도 필요 없다.
# G5: `<code>[]</code>` -> `<code>[ ]</code>` (붙어 있으면 네모 상자처럼 보임).
_MANUAL_JS = r"""
<script>
(function () {
  var doc = document;
  var root = doc.getElementById('pd-manual-root');

  // rerun 마다 REMOVE 후 RE-CREATE. 지우기 전에 열림 상태를 읽어 복원한다.
  var wasOpen = false;
  if (root) wasOpen = root.classList.contains('open');
  if (typeof window.__pdManualOpen === 'boolean') wasOpen = window.__pdManualOpen;

  var oldStyle = doc.getElementById('pd-manual-style');
  if (oldStyle) oldStyle.remove();
  if (root) root.remove();

  var style = doc.createElement('style');
  style.id = 'pd-manual-style';
  style.textContent = `
    #pd-manual-root, #pd-manual-root * { box-sizing: border-box;
      font-family: 'Myriad Pro', 'Pretendard', 'Nanum Gothic', -apple-system, sans-serif; }
    #pd-manual-tab {
      position: fixed; top: 28%; right: 0; z-index: 2147483000;
      writing-mode: vertical-rl; text-orientation: mixed;
      background: linear-gradient(160deg, #ed542b, #f68b21);
      color: #fff; font-weight: 700; letter-spacing: 2px; font-size: 15px;
      padding: 20px 11px; border-radius: 14px 0 0 14px; cursor: pointer;
      box-shadow: -4px 4px 18px rgba(0,0,0,0.20); user-select: none;
      transition: padding-right .2s ease, box-shadow .2s ease; }
    #pd-manual-tab:hover {
      padding-right: 15px; box-shadow: -6px 6px 22px rgba(237,84,43,0.35); }
    #pd-manual-backdrop {
      position: fixed; inset: 0; z-index: 2147483100;
      background: rgba(20,20,28,0.34);
      backdrop-filter: blur(6px) saturate(120%);
      -webkit-backdrop-filter: blur(6px) saturate(120%);
      opacity: 0; pointer-events: none; transition: opacity .38s ease; }
    #pd-manual-panel {
      position: fixed; top: 0; bottom: 0; right: 0; z-index: 2147483200;
      width: min(470px, 92%);
      background: rgba(255,255,255,0.94);
      backdrop-filter: blur(26px) saturate(160%);
      -webkit-backdrop-filter: blur(26px) saturate(160%);
      border-left: 6px solid #ed542b;
      box-shadow: -14px 0 44px rgba(0,0,0,0.24);
      transform: translateX(105%);
      transition: transform .38s cubic-bezier(.22,.61,.36,1);
      overflow-y: auto; padding: 24px 26px 64px; color: #23252a; }
    #pd-manual-root.open #pd-manual-panel { transform: translateX(0); }
    #pd-manual-root.open #pd-manual-backdrop { opacity: 1; pointer-events: auto; }
    #pd-manual-close {
      position: absolute; top: 16px; right: 18px; width: 34px; height: 34px;
      border: none; border-radius: 50%; cursor: pointer; font-size: 17px;
      background: rgba(237,84,43,0.12); color: #ed542b; line-height: 1;
      transition: background .18s ease; }
    #pd-manual-close:hover { background: rgba(237,84,43,0.24); }
    #pd-manual-panel h3 { color: #ed542b; margin: 4px 40px 4px 0;
      font-size: 1.18rem; font-weight: 800; }
    #pd-manual-panel h4 { color: #ed542b; margin: 18px 0 5px;
      font-size: 1.0rem; font-weight: 700; }
    #pd-manual-panel p { margin: 4px 0; font-size: .9rem; line-height: 1.55; }
    #pd-manual-panel ul { margin: 5px 0 8px; padding-left: 18px; }
    #pd-manual-panel li { font-size: .88rem; line-height: 1.55; margin: 3px 0; }
    #pd-manual-panel .pd-sub { color: #6b6b70; font-size: .86rem; margin-bottom: 6px; }
    #pd-manual-panel b { color: #c8431f; font-weight: 700; }
    #pd-manual-panel code { background: rgba(237,84,43,0.10); color: #c53a17;
      padding: 1px 5px; border-radius: 5px; font-size: .85em; }
    #pd-manual-panel .pd-loc { font-weight: 600; color: #9a8f89; font-size: .86em; }
    #pd-manual-panel table.pd-sym { border-collapse: collapse; margin: 6px 0 4px;
      font-size: .85rem; }
    #pd-manual-panel table.pd-sym td { padding: 2px 10px 2px 0; }
    #pd-manual-panel table.pd-sym td:first-child { color: #c53a17;
      font-weight: 700; font-family: monospace; }
    #pd-manual-panel .pd-note {
      background: rgba(255,244,235,0.85); border-left: 4px solid #f68b21;
      border-radius: 8px; padding: 12px 14px 4px; margin-top: 20px; }
    #pd-manual-panel .pd-note b { color: #ed542b; }
    #pd-manual-panel .pd-note ul { margin: 8px 0 8px; padding-left: 18px; }
    #pd-manual-panel .pd-note li { font-size: .87rem; line-height: 1.5; margin-bottom: 5px; }
  `;
  doc.head.appendChild(style);

  root = doc.createElement('div');
  root.id = 'pd-manual-root';
  root.innerHTML = `
    <div id="pd-manual-tab">📖 사용 설명서</div>
    <div id="pd-manual-backdrop"></div>
    <div id="pd-manual-panel">
      <button id="pd-manual-close" aria-label="닫기">✕</button>
      <h3>📖 Photodetector I-V Studio · 사용 설명서</h3>
      <p class="pd-sub">Keithley 측정 파일을 올리면 논문·보고서용 Origin 풍 I-V 그래프를 바로 만들 수 있습니다.</p>

      <h4>STEP 1 · 파일 업로드 <span class="pd-loc">· 제목 오른쪽 「＋ 파일 추가」</span></h4>
      <p>Keithley 측정 <b>.xls / .xlsx</b> 파일을 올립니다. <code>AnodeV</code> · <code>AnodeI</code> 컬럼을 가진 시트만 데이터로 인식하고, <code>Data</code> → <code>Append1</code> → <code>Append2</code> … 순으로 정렬합니다. <b>여러 파일</b>을 올려두고 제목 아래 배너에서 오가며 비교할 수 있습니다.</p>

      <h4>STEP 2 · 파일명 규칙 ⭐</h4>
      <p>파일명은 <code>260716 [dd876543].xls</code> 형태여야 합니다. <b>대괄호 <code>[ ]</code> 안 문자열의 길이 = 데이터 시트 개수</b>이며, 각 글자가 정렬된 시트에 <b>순서대로 1:1</b>로 매핑됩니다.</p>
      <table class="pd-sym">
        <tr><td>d</td><td>Dark</td><td>&nbsp;&nbsp;</td><td>5</td><td>625nm</td></tr>
        <tr><td>8</td><td>940nm</td><td></td><td>4</td><td>530nm</td></tr>
        <tr><td>7</td><td>850nm</td><td></td><td>3</td><td>470nm</td></tr>
        <tr><td>6</td><td>785nm</td><td></td><td>2</td><td>405nm</td></tr>
        <tr><td></td><td></td><td></td><td>1</td><td>365nm</td></tr>
      </table>
      <p>길이가 안 맞거나 <code>[ ]</code>가 없으면 <b>일반 라벨(Trace 1, 2 …)</b>로 대체되고 경고가 뜹니다. Dark 를 여러 번 측정했다면 <code>dd</code> 처럼 반복해 적으면 되고, 같은 라벨은 <code>Dark #2</code> 로 자동 구분됩니다.</p>

      <h4>STEP 3 · 트레이스 꾸미기 <span class="pd-loc">· 좌측 「트레이스」 탭</span></h4>
      <ul>
        <li><b>표시</b> — 체크박스로 트레이스 on/off (레전드가 아니라 여기서 고릅니다)</li>
        <li><b>선 색상</b> — Origin 기본 팔레트에서 고르거나 <b>Custom</b> 으로 직접 지정. 파장별 기본색(365nm=보라 … Dark=검정)이 미리 들어가 있습니다.</li>
        <li><b>선 종류</b> — Solid / Dash / Dot / DashDot</li>
        <li><b>텍스트</b> — 레전드·인셋 텍스트 (아래 마크업 문법 사용 가능)</li>
      </ul>

      <h4>STEP 4 · 인라인 마크업 문법</h4>
      <ul>
        <li><code>^{2}</code> 위첨자 · <code>_{ph}</code> 아래첨자 <b>— 중괄호 필수</b> (<code>cm^{2}</code>, <code>H_{2}O</code>). 중괄호 없는 <code>^</code> <code>_</code> 는 그대로 표시됩니다.</li>
        <li><code>**굵게**</code> · <code>*기울임*</code></li>
        <li><code>{#FF0000|색}</code> — 원하는 색으로 부분 강조</li>
        <li>겹쳐쓰기 가능: <code>{#C00000|**J**_{ph}}</code></li>
        <li>기호 자체를 쓰려면 이스케이프: <code>\*</code> <code>\_</code> <code>\^</code> <code>\{</code></li>
      </ul>

      <h4>STEP 5 · 축 · 서식 <span class="pd-loc">· 좌측 「축」 · 「서식」 탭</span></h4>
      <ul>
        <li><b>축</b> — X/Y 스케일(Y 기본 Log)·범위, Major/Minor 눈금 간격, 축 제목과 그 위치</li>
        <li><b>서식</b> — 서체 · 글자 크기 · 선 두께, 그리고 <b>Background(inch)</b> 와 <b>Graph(%)</b> 로 Origin 처럼 2단계 크기 지정</li>
      </ul>
      <p><b>화면의 그래프는 비례 축소된 미리보기</b>입니다 — 화면 높이가 10인치에 못 미치므로 스크롤 대신 축소해서 전부 보여줍니다. <b>내보내기(PNG·HTML)는 항상 정확히 지정한 10×8인치</b>로 나갑니다.</p>

      <h4>STEP 6 · 인셋 <span class="pd-loc">· 좌측 「인셋」 탭</span></h4>
      <p>Plotly 기본 레전드 대신 <b>그래프 안에 직접 그리는 Origin 풍 레전드</b>입니다. 포함할 트레이스를 고르고 위치·너비·테두리·글자 크기를 조정하세요. 스와치 선의 색·두께·대시는 실제 트레이스 설정을 그대로 따릅니다. <b>샘플 이름 인셋</b>도 함께 넣을 수 있습니다.</p>

      <h4>STEP 7 · 프리셋 <span class="pd-loc">· 좌측 「포맷」 탭</span></h4>
      <p>인셋 위치 · 파장별 색상 · 선 두께 · 축 스케일 · 축 제목 위치를 저장해 <b>다른 파일에 그대로 적용</b>할 수 있습니다. 여러 파일의 통일감을 맞출 때 쓰세요.</p>

      <h4>STEP 8 · 내보내기</h4>
      <ul>
        <li><b>PNG</b> — 그래프 우측 상단 모드바의 <b>카메라 아이콘</b> (scale 3 고배율 저장)</li>
        <li><b>HTML</b> — 그래프 아래 <b>「HTML 다운로드」</b> 버튼 (인터랙티브 그대로)</li>
      </ul>

      <div class="pd-note">
        <b>⚠️ 주의사항 &amp; 팁</b>
        <ul>
          <li><b>Range I 불일치 경고</b> — 트레이스마다 측정 전류 레인지가 다르면 경고가 뜹니다. 레인지가 다르면 <b>노이즈 바닥과 분해능이 달라져</b> 곡선을 나란히 비교하기 어려우니, 값이 의도한 것인지 확인하세요.</li>
          <li><b>로그 스케일에서 0 인 점은 제외</b>됩니다 — 절댓값을 적용해도 <code>log(0)</code> 은 그릴 수 없어 해당 점 개수를 경고로 알려줍니다.</li>
          <li><b>Range I 가 N/A</b> 로 나오면 Settings 블록 이름을 데이터 시트와 매칭하지 못한 경우입니다. 장비가 블록을 역순으로 쓰기 때문에 <b>순서 기반 추측은 하지 않습니다</b>(조용히 틀린 값을 붙이는 것보다 N/A 가 안전).</li>
          <li>그래프 자체는 <b>흰 배경 · 4면 박스 · 눈금 안쪽</b>으로 고정됩니다 — 논문에 그대로 넣을 수 있는 출판용 스타일입니다.</li>
        </ul>
      </div>
    </div>`;
  doc.body.appendChild(root);

  function setOpen(o) {
    window.__pdManualOpen = o;
    if (o) root.classList.add('open'); else root.classList.remove('open');
  }
  setOpen(wasOpen);   // rerun 직후 열림 상태 복원

  // V2 는 인라인 on* 속성을 제거한다 -> 핸들러는 여기서 붙인다.
  root.querySelector('#pd-manual-tab').onclick = function () { setOpen(true); };
  root.querySelector('#pd-manual-close').onclick = function () { setOpen(false); };
  root.querySelector('#pd-manual-backdrop').onclick = function () { setOpen(false); };

  // Esc 닫기 — document 에 한 번만 부착 (rerun 중복 방지)
  if (!window.__pdManualEsc) {
    window.__pdManualEsc = true;
    doc.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && window.__pdManualOpen) {
        var r = doc.getElementById('pd-manual-root');
        if (r) { r.classList.remove('open'); window.__pdManualOpen = false; }
      }
    });
  }
})();
</script>
"""

# PLAN §5.5 뷰포트 바인딩 + §7 zoom 수정. 둘은 한 계산에 묶여 있다 —
# zoom 이 콘텐츠의 CSS px 좌표계를 바꾸므로 가용 높이를 z 로 나눠 환산해야 한다.
_BIND_JS = r"""
<script>
(function () {
  var root = document.documentElement;

  // ---- zoom (PLAN §7) ----
  // 옛 버전: doc.body.style.zoom = innerWidth/1440 (0.85~1.35).
  //   문제1 body 에 zoom -> Streamlit 의 100vh 레이아웃과 충돌 (zoom 은 vh 를 보정 안 함).
  //   문제2 1440 보다 넓은 창에서 1.067 배로 **확대** -> 가용 높이가 더 줄어 V11 악화.
  // NBEDL 은 문제1 을 style 규칙 + .block-container 로 이미 고쳤다. 문제2 는 여기서
  // MAX 를 1.0 으로 클램프해 고친다 — 축소는 허용(공간 확보), 확대는 금지.
  var DESIGN = 1440, ZMIN = 0.85, ZMAX = 1.0;
  var zs = document.getElementById('pd-zoom-style');
  if (!zs) { zs = document.createElement('style'); zs.id = 'pd-zoom-style'; document.head.appendChild(zs); }

  function applyZoom() {
    var z = Math.max(ZMIN, Math.min(ZMAX, window.innerWidth / DESIGN));
    document.body.style.zoom = '';    // 과거 body-zoom 방식 잔재 제거
    zs.textContent =
      '[data-testid="stMain"] .block-container { zoom: ' + z + '; }' +
      '#pd-manual-root { zoom: ' + z + '; }';
    return z;
  }

  function px(v, d) { var n = parseFloat(v); return isFinite(n) && n > 0 ? n : d; }

  // ---- 측정 -> CSS 변수 (단방향. 값을 파이썬에 돌려주지 않으므로 rerun 0회) ----
  function measure() {
    var m = document.querySelector('[data-testid="stMain"]');
    if (!m) return;
    var z = applyZoom();

    var cs = getComputedStyle(root);
    var figW = px(cs.getPropertyValue('--pd-fig-w'), 960);
    var figH = px(cs.getPropertyValue('--pd-fig-h'), 768);

    // 헤더+배너 높이를 상수로 두지 않고 **실측**한다 (창·zoom·파일 유무에 따라 변함).
    // stMain 은 zoom 밖, 본문은 zoom 안 -> viewport px 를 z 로 나눠 내부 CSS px 로 환산.
    var body = document.querySelector('.st-key-pd_body');
    var avail;
    if (body) {
      var mr = m.getBoundingClientRect(), br = body.getBoundingClientRect();
      avail = (mr.bottom - br.top) / z - 12;    // 12 = 하단 숨 쉴 틈
    } else {
      avail = m.clientHeight / z - 120;
    }
    avail = Math.max(240, avail);

    var stage = document.querySelector('.st-key-pd_graph_stage');
    var stageW = stage ? stage.clientWidth : avail * (figW / figH);

    var s = Math.min(1, avail / figH, stageW / figW);
    if (!(s > 0)) s = 1;

    root.style.setProperty('--pd-panel-h', avail.toFixed(0) + 'px');
    root.style.setProperty('--pd-graph-scale', s.toFixed(4));
  }

  measure();
  window.__pdMeasure = measure;

  // ResizeObserver: 창 크기·컬럼 폭이 바뀔 때마다 재측정. 관측 대상은 rerun 마다
  // DOM 이 교체되므로 매번 다시 붙인다 (옵저버 자체는 1개만 유지).
  if (window.__pdRO) { try { window.__pdRO.disconnect(); } catch (e) {} }
  var raf = 0;
  window.__pdRO = new ResizeObserver(function () {
    if (raf) return;                       // 측정->CSS변수->레이아웃 루프 방지
    raf = requestAnimationFrame(function () { raf = 0; measure(); });
  });
  ['[data-testid="stMain"]', '.st-key-pd_body', '.st-key-pd_graph_stage'].forEach(function (sel) {
    var el = document.querySelector(sel);
    if (el) window.__pdRO.observe(el);
  });

  if (!window.__pdResizeBound) {
    window.__pdResizeBound = true;
    window.addEventListener('resize', function () { measure(); });
  }
})();
</script>
"""


def fig_metrics(w_px: int, h_px: int) -> None:
    """figure 의 **고유** 픽셀 크기를 CSS 변수로 알린다. 매 run 호출 (layout 이 호출).

    B1 의 Background(inch) 를 바꾸면 고유 크기가 960×768 이 아니게 되므로 스케일 계산이
    이 값을 따라가야 한다. 하드코딩된 768 이 아니라 실제 figure 크기가 기준이다.
    """
    st.html(
        f"<style>:root {{ --pd-fig-w: {int(w_px)}px; --pd-fig-h: {int(h_px)}px; }}</style>"
    )


def panel_height(px: int) -> None:
    """좌측 편집 패널 높이를 그래프 높이에 맞춘다 (px_scale 렌더로 그래프 높이는
    파이썬이 이미 알고 있다). 측정 ResizeObserver 없이 CSS 변수만 한 줄 주입한다 —
    단방향이라 rerun 도 busy 루프도 없다.
    """
    st.html(f"<style>:root {{ --pd-panel-h: {int(px)}px; }}</style>")


def install() -> None:
    """전역 CSS + 정적 에셋 + 매뉴얼 드로어 설치.

    ⚠️ 뷰포트 측정 ResizeObserver/zoom(_BIND_JS)은 폐기했다: 그것이 페이지를 busy
    상태로 만들었고(스크린샷 주입 5s 타임아웃), transform 스케일 방식과 한 몸이었다.
    이제 그래프 축소는 figure px_scale 이 담당하고 패널 높이는 panel_height() 가
    단방향으로 준다 — 관측 루프가 없다.

    멱등하게 구성되어 있어 (drawer 는 remove-then-recreate) 한 run 에 두 번 불려도 안전.
    """
    st.markdown(_CSS, unsafe_allow_html=True)
    # V2: st.html(unsafe_allow_javascript=True) 는 **메인 문서에서** 실행된다.
    # components.html(iframe) + window.parent 더듬기가 통째로 필요 없어진다.
    st.html(_MANUAL_JS, unsafe_allow_javascript=True)
