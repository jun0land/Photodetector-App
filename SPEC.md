# Photodetector I-V Viewer — 요구사항 스펙 (2026-07-17 확정)

레퍼런스: `C:\Users\mintj\바탕 화면\오리진 그래프 예시.png` (1560x1244 ≈ 1.254 ≈ 10:8)
디자인 레퍼런스: `NBEDL Exp Assistant/app.py`, `Raman Mapping/app.py` (liquid glass, ACCENT #ed542b)

---

## A. 그래프 정확성 (Origin 예시와 일치시킬 것)

A1. **Y축 기본 스케일 = Log.** Linear 는 선택 옵션.
A2. **Log 여도 Y축 제목에 절댓값 기호를 넣지 말 것.** 항상 `Current (A)`.
    - 내부적으로는 |I| 를 그린다(0 교차점의 하강 스파이크가 예시에 그대로 보임). 라벨만 절댓값 표기 안 함.
    - 기존 `Y_TITLE_ABS = "|Current| (A)"` 및 use_abs 연동 로직 제거.
A3. **Y축 눈금 표기는 항상 `1E-11` 형식.** (`exponentformat="E"`. 현재 `"power"` → 10⁻¹¹ 위첨자라 틀림)
A4. **Log 스케일은 tick 스타일이 다르다.** Major tick 개수 / Minor tick 개수를 각각 조절하는 UI 구현.
    - Plotly: major `dtick`, minor `minor=dict(dtick=..., ticks="inside", ticklen=...)`.
    - Log 축 minor 는 `dtick="D1"`/`"D2"` 계열 사용.
A5. **축 범위가 -1~1 이면 곡선이 좌우 테두리에 맞닿아야 한다.** 현재 뜨는 원인은 Plotly autorange 의 자동 패딩.
    - Auto 일 때도 데이터 min/max 로 range 를 명시해 패딩 제거.
A6. **축 scale step(major 간격) 조절 가능.** 예시 X축은 step 0.5 (-1.0, -0.5, 0.0, 0.5, 1.0).
A7. 4면 박스 mirror ticks, ticks inside, 그리드 없음, 흰 배경 유지 (논문용 — 절대 투명화 금지).

## B. 크기·배치 (Origin 방식)

B1. **그래프 높이 슬라이더 방식 폐기.** Origin 처럼 2단계로 지정:
    1. **Background**: width / height (단위 **inch**). 기본값 **width 10, height 8**.
    2. **Graph**: Left / Top / Width / Height (단위 **% of Page(=background)**).
       기본값 **Left 17.9, Top 11.58, Width 68.2, Height 71.77**.
    - 구현: figure width/height = inch * 96 dpi. `xaxis.domain=[L, L+W]`,
      `yaxis.domain=[1-(T+H), 1-T]` (Top 은 위에서부터). margin 0.
B2. **축 제목 위치도 바꿀 수 있어야 한다.** (X/Y 각각 offset 조절)

## C. 폰트·선

C1. 폰트 목록에 **Pretendard, Myriad Pro** 추가.
C2. **모든 폰트 기본 크기 = 30.** 최소/최대 **6~50 으로 전 항목 통일.**
C3. **폰트 크기는 슬라이더(드래그) 금지.** 숫자 입력 + 스테퍼(꺽쇠) 방식 (`st.number_input`).
C4. **선 두께는 0.5 간격** 조절.
C5. 맨 아래 인셋의 폰트 선택 시 **스크롤이 안 내려가 선택 불가** — 레이아웃 수정으로 해결.

## D. 인셋 / 레전드

D1. **인셋이 있으므로 Plotly 레전드는 불필요 → 제거.**
D2. **인셋은 선택이 아니라 필수.** (항상 표시)
D3. **샘플 이름 인셋 추가** (예시의 `Quasi-2D x3`).
D4. **인셋 위치는 마우스 드래그로 조절.** → **커스텀 컴포넌트로 진짜 드래그 (사용자 확정)**
    - 드래그 결과가 파이썬으로 돌아와 프리셋에 저장되어야 함.
    - `st.plotly_chart` 는 relayout 을 파이썬에 돌려주지 않으므로 불가 → postMessage 프로토콜 직접 구현.
D5. **그래프 선택(트레이스 on/off) 기능을 레전드에 두지 말고 다른 곳(좌측 편집 패널)에 구현.**

## E. 프리셋(그래프 포맷) 저장

E1. 저장 항목: **인셋 위치, 각 파장별 색상, 선 두께, XY축 스케일, 축 제목 위치.**
E2. **한 파일에서 저장한 프리셋을 다른 파일에 바로 적용 가능해야 한다.** (통일감)

## F. 멀티 파일

F1. **여러 파일을 올려두고 옮겨다니며 비교.** 새 파일 추가 가능.
F2. 파일 추가 시 **상단에 파일명 배너/탭**이 생겨 왔다갔다 전환.

## G. UI / UX (최우선 가치)

G1. **좌측 편집 패널 + 우측 그래프** 배치. 현재는 위아래로 길고 그래프가 화면을 너무 차지함.
    - **스크롤 최소화.** "스크롤이 생기는 순간 정보량이 제한되고 불편해서 안 쓰게 된다."
G2. **업로드 버튼은 제목 칸에 우측 정렬**로.
G3. **파일이 이미 업로드된 상태에서 업로드 영역의 여백을 누르면 파일 창이 뜨는 버그 수정.**
G4. **서식 입력 = 오리진식 상단 툴바 (사용자 확정).**
    - 텍스트 선택 후 글자 색상 / 위첨자 / 아래첨자 / 볼드 / 이탤릭 적용.
    - 기존 마크업 파서(`apply_markup`)는 내부 표현으로 그대로 유지.
G5. 매뉴얼의 `대괄호 []` → **`대괄호 [ ]`** (가운데 띄어쓰기; 붙어 있으면 네모 상자처럼 보임).
G6. **사용자 피로도 최소화가 최우선.** "안 그러면 오리진 쓰지."

## H. 나중에 (지금 구현하지 말 것)

H1. 데이터 요약에 파장별 **Responsivity, Detectivity** 저장·내보내기.
    - **식은 사용자 확인 필수.** 임의로 식을 쓰지 말고 반드시 먼저 확인받을 것.

---

## 유지해야 하는 기존 결정 (건드리지 말 것)

- Dark 트레이스 **병합(stitching) 안 함**. 데이터 시트 1:1 트레이스. (사용자 확정)
- 파싱 로직: `parse_file`, `_load_sheets`, `_parse_settings`, `_settings_frame`,
  `_sheet_sort_key`, `_is_data_sheet` — 동작 검증 완료. 로직 변경 금지.
- 마크업 파서: `_parse_seq` / `_parse_token` / `apply_markup` — 유지.
- 파일명 `[]` 심볼 매핑: d=Dark, 8=940nm, 7=850nm, 6=785nm, 5=625nm, 4=530nm, 3=470nm, 2=405nm, 1=365nm.
- Range I 불일치 경고 유지.
- 그래프는 **흰 배경 + mirror ticks 논문용** — glass 로 만들지 말 것.

## 알려진 리스크

- `st.components.v1.html` 는 streamlit 이 "removed after 2026-06-01" 경고 중 (오늘 2026-07-17, 이미 경과).
  1.59.2 에선 동작하나 업그레이드 시 깨질 수 있음. 매뉴얼·배율·드래그 컴포넌트가 모두 여기 의존.
