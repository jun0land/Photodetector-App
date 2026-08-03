# 광센서 I-V Curve Studio

> 본 문서의 모든 수치는 저장소에서 실제 명령을 실행해 확인한 값이며, 각 항목에 사용한 명령을 병기했다.
> 확인되지 않은 항목은 임의로 채우지 않고 **확인 불가**로 남겼다.

- **기간**: 2026-07-19 ~ 2026-07-25 (개발 7일, 총 40커밋) / 2026-08-03 본 분석 수행
  - `git log --reverse --format="%h|%ci|%s" | head -3` → 최초 `f837729` 2026-07-19 16:11:44 +0900
  - `git log -1 --format="%h|%ci|%s"` → 최종 `8d4f443` 2026-07-25 01:13:01 +0900
  - `git rev-list --count HEAD` → **40**
- **상태**: 배포·운영 중. 작업 트리 클린(추적 대상 소스 기준), 최신 커밋까지 반영 완료
  - `git status --short` → 변경분은 `__pycache__/*.pyc` 뿐
- **배포 URL**: https://photodetector-studio.streamlit.app
  - 근거: `example/logs-...2026-07-22T07_04_31.045Z.txt:2` → `Logs for photodetector-studio.streamlit.app/` (Streamlit Community Cloud 실 배포 로그)
- **문제 정의 (수작업 병목)**: Keithley 4200(KITE) 산출 `.xls`는 트레이스가 `Data`/`Append1..N` 시트로 흩어져 있고, 측정 조건(Range I)은 별도 `Settings` 시트에 블록 단위로 적힌다. 이를 Origin에 옮겨 파장별로 색·축·인셋을 매번 수작업 지정하고, Responsivity/Detectivity를 스프레드시트로 따로 계산하는 과정이 반복 비용이었다. 요구사항 문서에 그 동기가 명시돼 있다 — `SPEC.md:71` **"G6. 사용자 피로도 최소화가 최우선. '안 그러면 오리진 쓰지.'"**
- **사용한 AI 도구·모델·인터페이스**:
  - 도구: **Claude Code** (VSCode 확장 인터페이스에서 구동)
  - 버전: `2.1.216` / `2.1.218` / `2.1.220` (세션 로그 `version` 필드 집계)
  - 모델: `claude-opus-4-8` 215건, `claude-sonnet-5` 39건, `claude-opus-5` 28건 (어시스턴트 메시지 기준)
  - 전역 설정 `~/.claude/settings.json` → `{"model":"claude-sonnet-5","autoUpdatesChannel":"latest","theme":"dark"}`

---

### 동기

측정 → 분석 → 발표자료가 각각 다른 도구에 흩어져 있었다. 장비(Keithley 4200 + Mightex LED)가 뱉는 엑셀은 사람이 읽기 위한 포맷이 아니라 장비 로그 포맷이고, 논문·발표용 그래프는 Origin 규격(10×8인치, mirror tick, 로그 Y축, 인셋 범례)을 따라야 했다. 두 규격 사이의 변환을 매번 손으로 하는 대신, **"파일을 올리면 논문용 그래프와 성능지표가 바로 나오는"** 웹 도구를 만드는 것이 목표였다.

설계 원칙은 요구사항 문서에 성능이 아니라 **피로도** 기준으로 못박혀 있다:
- `SPEC.md:64` — "스크롤이 생기는 순간 정보량이 제한되고 불편해서 안 쓰게 된다."
- `SPEC.md:21` — "4면 박스 mirror ticks, ticks inside, 그리드 없음, 흰 배경 유지 (논문용 — 절대 투명화 금지)."
- `SPEC.md:76` — Responsivity/Detectivity에 대해 **"식은 사용자 확인 필수. 임의로 식을 쓰지 말고 반드시 먼저 확인받을 것."** → 물리 계산식은 AI가 추정하지 않고 사용자 확인을 거치도록 프로세스에 명시.

### 워크플로우

**1) 스펙-플랜 분리형 문서 주도 개발**
저장소 루트에 두 개의 기준 문서를 두고 AI가 이를 참조하도록 했다.
- `SPEC.md` (93줄) — 요구사항의 기준. A(그래프 정확성)/B(크기·배치)/C(폰트·선)/D(인셋)/E(프리셋)/F(멀티파일)/G(UI·UX)/H(보류) 8개 섹션에 ID를 부여(A1, D5, G6…). 하단에 **"유지해야 하는 기존 결정 (건드리지 말 것)"**과 **"알려진 리스크"**를 별도 관리.
- `PLAN.md` (321줄) — 구현의 기준. 첫 줄에 충돌 시 우선순위를 규정: *"`SPEC.md`가 요구사항의 기준, 이 문서가 구현의 기준. 충돌 시 SPEC이 우선."*

**2) 환경 사실을 "추측 금지, 스파이크로 검증" 원칙으로 고정**
`PLAN.md §0`은 **"검증된 환경 사실 (추측 아님 — 실제 스파이크/소스 확인)"** 표로 V1~V17을 관리하며, 각 항목에 근거(소스 경로 / 실측 / AppTest)를 병기한다. 예:

| ID | 사실 | 근거 |
|---|---|---|
| V4 | `setStateValue`/`setTriggerValue`는 항상 `{fromUi:true}` → 항상 rerun. 조용한 set은 없음 | `BidiComponent.*.js` |
| V5 | `default(component)`는 `data` 바뀔 때마다 재실행 → **오버레이 3개 중첩 누수 실측** | 실측 |
| V8 | `margin=0`이면 `xref="paper"`는 축 영역이 아니라 **페이지 전체**에 매핑 | 실측 |
| V11 | **10×8in 그래프는 뷰포트에 안 들어감.** `stMain` clientHeight=639, 그래프 768 필요 | 실측 |
| V13 | `st.tabs`는 모든 탭 body를 매 run 실행 → 탭 전환 rerun 0회 | AppTest |

**3) 모놀리스 → 모듈 분해 시 "축자 이동 + AST 동일성 게이트"**
초기 단일 `app.py` 1184줄(`pd_app/_legacy_reference.py.txt`로 원문 보존)을 패키지로 쪼갤 때, 검증이 끝난 파싱·마크업 로직은 **리팩터링 금지·복붙 이동**으로 제한하고 기계적 게이트를 걸었다.
> `PLAN.md` — *"검증 게이트 = 보호 대상 9개 함수의 **AST 덤프 동일성 체크 통과** (코드 리뷰 아님)."*
> 보호 대상: `parse_file, _load_sheets, _parse_settings, _settings_frame, _sheet_sort_key, _is_data_sheet, _parse_seq, _parse_token, apply_markup`

**4) 재발 방지를 소스 주석으로 고정**
반복해 물린 프레임워크 함정을 코드 주석에 규칙으로 남겨, 이후 세션의 AI가 같은 실수를 반복하지 않도록 했다.
> `pd_app/state.py:40-47` — *"fid: 파일 전환 시 값 누출 방지(함정1). rev: 키가 이미 있으면 Streamlit이 value=를 무시(함정2) → 프리셋을 적용해도 UI가 안 바뀐다."*
> `pd_app/presets.py:573` — *"이 패키지에서 가장 중요한 한 줄."* (`state.bump_rev()` 호출 의무)

**5) 버그 수정은 "AppTest 재현 → 수정 → 재검증" 순서**
본 세션에서 배너 전환 버그를 잡을 때, 추측 대신 `streamlit.testing.v1.AppTest`로 헤드리스 재현부터 만들었다. 재현 결과 `파일 B 추가 → active=A로 복귀`를 확인한 뒤 원인(위젯 키 잔존)을 특정하고, 수정 후 동일 하네스로 `active=B` 복귀를 확인했다.

**6) 세션 기록 (로컬 탐색 결과)**
- 경로: `C:\Users\mintj\.claude\projects\c--Users-mintj-photodetector-app\`
- 세션 파일 **1개** — `bbb67044-...jsonl`, **1,708,767 bytes**, 레코드 **649건**
- 커버 구간: `2026-07-22T06:48:21Z` ~ `2026-08-03T03:03:30Z`
- 도구 호출 **143회**: PowerShell 32 / Edit 30 / Read 27 / Bash 26 / Grep 11 / Write 11 / TodoWrite 5 / ToolSearch 1
- ⚠️ **개발 초기(2026-07-19 ~ 07-22 오전) 구간의 세션 기록은 로컬에 없음** — 남아 있는 세션이 07-22 15:48(KST)부터 시작. 해당 구간의 대화 원본은 **확인 불가**(커밋 41건 중 초기 13건에 해당).
- `~/.claude.json`의 이 프로젝트 항목에 `history` 엔트리 **0건**, `mcpServers` **0개**.

**7) 커스텀 확장 설정 유무**

| 항목 | 결과 | 확인 명령 |
|---|---|---|
| `CLAUDE.md` | **없음** | `ls -la CLAUDE.md` |
| `.claude/` 디렉터리 | **있음** — `settings.local.json` 1개뿐 | `ls -laR .claude` |
| 커스텀 슬래시 커맨드 | **없음** (`.claude/commands/` 부재) | `ls -laR .claude` |
| 커스텀 스킬 | **없음** (`.claude/skills/` 부재) | `ls -laR .claude` |
| 훅(hooks) | **없음** (settings에 `hooks` 키 없음) | `cat .claude/settings.local.json` |
| MCP 서버 | **없음** (`mcpServers: {}`, `enabledMcpjsonServers: []`) | `~/.claude.json` 파싱 |
| 플러그인 | 마켓플레이스 등록만 존재, 프로젝트 적용 없음 | `ls -la ~/.claude/plugins` |

`.claude/settings.local.json` 전문 — 로컬 파이썬 실행 권한 2건만 허용:
```json
{ "permissions": { "allow": [
  "Bash(./.venv/Scripts/python.exe -c ' *)",
  "PowerShell(& \"c:\\\\Users\\\\mintj\\\\photodetector-app\\\\.venv\\\\Scripts\\\\python.exe\" -c \"print\\(1\\)\")"
] } }
```
→ **커스텀 자동화 없이, 문서(SPEC/PLAN) + 코드 주석 규칙만으로 컨텍스트를 관리한 형태.**

---

### 핵심 알고리즘 (입력 → 파싱 → 특징점 추출 → 지표 계산 → 출력)

#### ① 입력 포맷

| 항목 | 규격 | 근거 |
|---|---|---|
| 확장자 | `.xls` / `.xlsx` | `pd_app/ui/layout.py` `type=["xls","xlsx"]` |
| 데이터 시트 | `AnodeV`, `AnodeI` 컬럼을 가진 시트만 데이터로 인정 | `parsing.py:32-36` `_is_data_sheet` |
| 시트 정렬 | `Data` 먼저, 이후 `Append<N>` 숫자 오름차순 (Append10 > Append9) | `parsing.py:21-29` `_sheet_sort_key` |
| 조건 시트 | `Settings` 시트를 `header=None`으로 **재독** (첫 행이 구분선이라 header=0이면 소실) | `parsing.py:96-104` |
| 파일명 | `(샘플명) [측정순서].xls` | `parsing.py:226-231` |

**파일명 규약**: 소괄호 = 샘플명(인셋 자동 주입), 대괄호 = 파장 코드열. 괄호 밖 텍스트(날짜·메모)는 무시.
```python
m_sample = re.search(r"\(([^)]*)\)", str(file_name))   # (샘플명)
m        = re.search(r"\[([^\]]+)\]", str(file_name))  # [측정순서]
```
심볼 매핑 (`constants.py:8-18` `SYMBOL_MAP`): `d`=Dark, `8`=940nm, `7`=850nm, `6`=740nm, `5`=625nm, `4`=530nm, `3`=470nm, `2`=405nm, `1`=365nm.
**대괄호 글자 수 ≠ 데이터 시트 수**이면 매핑을 포기하고 `Trace N` 라벨로 폴백하며 경고를 남긴다(조용한 오매핑 방지).

#### ② 파서 구조 — 5단 폴백

구형 Keithley `.xls`가 표준 엑셀이 아닌 경우가 있어 다단 폴백을 둔다 (`parsing.py:55-93` `_load_sheets`):
```
read_excel(engine=None) → read_excel(xlrd) → read_excel(openpyxl) → read_html → read_csv(sep="\t")
```
전 단계 실패 시 누적 에러를 합쳐 예외. 또한 구형 `.xls`의 xlrd OLE2 경고가 stdout으로 새는 것을 `_quiet()` 컨텍스트로 차단해 사용자에게 노출하지 않는다(`parsing.py:39-45`).

**Range I 추출 (`_parse_settings`, `parsing.py:107-`)**: `Settings` 시트를 위에서 훑으며 `Initial Run` → `Data`, `Append N` → `AppendN`으로 현재 블록을 추적하고, 블록 안의 `Range I` 행 값을 수집한다.
> 이 파서에는 본 세션에서 수정한 실제 결함이 있었다. Keithley 산출물은 **SMU1/SMU2의 컬럼 위치가 블록마다 뒤바뀐다.** 예제 파일 실측 — `Append 1~7`은 SMU2가 col2, `Initial Run`은 SMU2가 col1. 기존 코드가 col1만 읽어 7개 블록이 전부 `N/A`로 떨어지고 "Range I 불일치" 오경고가 떴다.
> **수정**: 고정 컬럼이나 SMU 번호가 아니라, 블록마다 `Forcing Function` 행에서 `Voltage Sweep` 문자열이 있는 컬럼을 찾아 **그 컬럼의 Range I를 읽도록** 변경. 폴백으로 값 컬럼 전수 스캔을 남김.
> **검증**: 8개 블록 전부 `100uA` 정상 인식. sweep 컬럼이 `Data`=col1 / `Append*`=col2로 서로 다름에도 모두 SMU2·AnodeV를 정확히 선택.

**다중 파일 일괄 업로드**: `st.file_uploader(accept_multiple_files=True)` → `_ingest()`가 파일별로 **SHA-1 해시 중복 제거** 후 등록(`layout.py`), 파싱 결과는 `@st.cache_data`로 캐싱(`parsing.py:184`). 파일은 `fid`(uuid4 8자리)로 식별하며 **파일명을 키로 쓰지 않는다** — `state.py:74` *"fid는 파일명이 아니다 — 파일명은 충돌하고 바뀐다"*. 화면은 상단 배너에서 한 파일씩 전환하는 방식이고, 내보내기만 전 파일을 일괄 처리한다.

#### ③ 특징점 추출 로직

구현된 특징점 추출은 **두 가지**다. 피크 검출·임계값 탐색·미분 기반 추출은 구현되어 있지 않다.

**(a) 동작전압 지점의 전류 — 선형보간** (`summary.py:74-87` `_current_at`)
```python
good = np.isfinite(v) & np.isfinite(i)      # NaN/inf 제거
order = np.argsort(v); v, i = v[order], i[order]   # V 오름차순 정렬
if v_op < v[0] or v_op > v[-1]: return None        # 외삽 금지 → N/A
return float(np.interp(v_op, v, i))
```
기준: 사용자가 지정한 두 동작전압 `V_op1`(기본 −1.0V), `V_op2`(기본 +1.0V). **측정 범위를 벗어나면 외삽하지 않고 `None`을 반환해 지표를 N/A 처리** — 없는 데이터를 만들어내지 않는다.

**(b) Dark 0V 영점 오프셋** (`parsing.py:160-181` `_apply_dark_zero_offset_correction`)
```python
min_v_idx = (df["AnodeV"].abs()).idxmin()          # 0V에 가장 가까운 행
if abs(df.loc[min_v_idx, "AnodeV"]) < 0.05:        # 0.05V 이내일 때만 오프셋 인정
    i_offset = float(df.loc[min_v_idx, "AnodeI"])
...
t["df"]["AnodeI"] = t["df"]["AnodeI"] - i_offset   # Dark·Photo 전 트레이스에서 일괄 차감
```
기준: **Dark 트레이스**에서 |V|가 최소인 점을 찾고, 그 점이 0V로부터 **0.05V 이내**일 때만 계통 오프셋으로 인정. 인정되면 그 값을 Dark뿐 아니라 **모든 트레이스**의 전류에서 차감한다.

**Dark 기준 전류** (`summary.py:90-97` `_dark_current_at`): 라벨이 `Dark`인 트레이스를 **전부 concat**한 뒤 보간하고 절댓값을 취한다. 측정 장비가 Dark를 음/양 방향 2회로 나눠 측정하기 때문(측정 시스템 `pd_iv_station.py:1061-1062` `Dark 0→−1V` / `Dark 0→+1V`)이며, 이 앱은 이를 자동 병합해 하나의 Dark 기준으로 삼는다.

#### ④ 지표 계산 — 구현된 전체 목록

`_Q_ELECTRON = 1.602e-19` (`summary.py:19`). 면적 환산 `area_cm2 = area × (1e-2 if mm² else 1.0)`, 조도 환산 `E_e[W/cm²] = E_e[mW/cm²] × 1e-3`.

| 지표 | 계산식 (코드 원문) | 단위 | 위치 | 비고 |
|---|---|---|---|---|
| 광전류 I_ph | `i_ph = abs(i_light) - i_dark_abs` | A | `summary.py:152,159` | 보간 전류의 절댓값 차 |
| **Responsivity R** | `R = i_ph / (ee_w * area_cm2)` | A/W | `summary.py:153,160` | `V_op1`, `V_op2` **두 전압에서 각각** 산출 |
| **Detectivity D\*** | `D = R * math.sqrt(area_cm2) / math.sqrt(2.0 * _Q_ELECTRON * i_dark_abs)` | Jones | `summary.py:155,162` | 산탄잡음 한정(shot-noise-limited) 가정 |
| 암전류 I_dark | `abs(np.interp(v_op, v, i))` (Dark 트레이스 concat 후) | A | `summary.py:90-97` | D\* 분모 및 표시용 |
| 데이터 요약 | Points(행수), V min, V max, Range I, Sheets, Legend | — | `summary.py:35-52` | 파일별 트레이스 목록 |

**가드 조건**: `ee > 0` 이고 `area_cm2 > 0` 일 때만 R 계산, `i_dark_abs > 0` 일 때만 D\* 계산. 하나라도 불충족이면 해당 셀은 `N/A`(`_fmt`, `summary.py:175-176`). 전체 계산은 `try/except`로 감싸 한 파일의 이상값이 앱 전체를 죽이지 않게 했다(`summary.py:170-171`).

**미구현(코드에 없음)**: on/off ratio, 응답속도(rise/fall time), suppression ratio, EQE, NEP, LDR.
확인 명령: `grep -rniE "on.?off|rise.?time|response.?time|suppression|EQE|NEP|LDR" --include="*.py" pd_app/` → 지표 구현 히트 **0건**.

#### ⑤ 노이즈 처리·피팅·로그 스케일

| 항목 | 구현 내용 | 근거 |
|---|---|---|
| 스무딩 | **없음** | `grep -nE "savgol\|smooth\|rolling\|median"` → 히트 0 |
| 곡선 피팅 | **없음** | `grep -n "polyfit\|curve_fit"` → 히트 0 |
| scipy/sklearn | **미사용** (의존성 자체 없음) | `requirements.txt` 7줄 전량 확인 |
| 보간 | `np.interp` **선형보간 1종**, 범위 밖 외삽 금지 | `summary.py:87` |
| 노이즈 대응 | ① Dark 0V 오프셋 일괄 차감 ② `isfinite` 마스크로 NaN/inf 제거 ③ `pd.to_numeric(errors="coerce").dropna()` | `parsing.py:160-181`, `summary.py:79`, `parsing.py:215` |
| 로그 Y축 | 기본 스케일 = **log**. log일 때 `use_abs`를 강제 True → `\|I\|` 플롯 | `figure.py:150-151`, `SPEC.md:10-13` |
| log 0값 처리 | `y <= 0` 개수를 세어 `fig._pd_zero_count`에 부착, UI가 *"로그 스케일이라 0 이하인 점 N개는 표시에서 제외되었습니다"* 캡션 표시 | `figure.py:162-163`, `layout.py` |
| log 축 범위 | 양수만 필터 후 `[floor(log10(min)), ceil(log10(max))]` — decade 경계로 정렬 | `figure.py:113-122` |
| 기본 Y범위 | **1E-11 ~ 1E-5 고정** (auto=False) | `constants.py:112` |
| 눈금 | Major `dtick=1`(1 decade), Minor `"D1"`(8분할) 고정 | `constants.py:113` |

기본 Y범위를 auto가 아닌 **고정값**으로 둔 이유가 상수 주석에 남아 있다 — `constants.py:110-111`: *"0 교차점 때문에 auto는 노이즈 바닥(~1E-16)까지 따라가 9 decades가 되므로 예시 이미지와 어긋난다."* 자동화가 오히려 결과를 나쁘게 만드는 지점을 식별해 의도적으로 수동 고정한 사례.

#### ⑥ 계산 정합성 검증 코드·테스트

- **저장소에 커밋된 테스트 파일: 없음.** (`git ls-files | grep -iE "test|conftest"` → 0건, pytest 미의존)
- 대신 두 층의 방어가 코드에 내장돼 있다:
  1. **프리셋 로더의 전수 검증기** (`presets.py`, 613줄) — `_c_bool/_c_float/_c_int/_c_choice/_c_color/_c_dtick/_c_font` 코어서(coercer)가 모든 필드를 타입·범위·스텝 단위로 강제하고, 위반 시 필드당 1회 경고를 모아 반환. 설계 계약이 명시적이다: *"`load()`는 절대 raise 하지 않는다"* — 잘린 JSON·JPEG 바이트·null 무엇이 와도 사용 가능한 dict를 돌려준다(`presets.py:414-418`).
  2. **파싱 불일치 경고** — 대괄호 길이 ≠ 시트 수, Settings 블록명 매칭 실패, Range I 트레이스 간 불일치를 각각 사용자에게 경고(`parsing.py:219-235`, `summary.py:23-32`).
- **검증 하네스는 개발 중 임시로 사용**: 본 세션에서 `streamlit.testing.v1.AppTest` 기반 재현 스크립트를 작성해 프리셋 일괄 적용·배너 전환·파일명 파싱·인셋 자동주입·조도 기본값을 헤드리스로 확인했으나, **스크래치패드에만 두고 저장소에는 커밋하지 않았다.** → 회귀 방지 자산으로 남지 않은 것은 아래 "실패 기록" 참조.

#### ⑦ 그래프 출력 설정과 발표자료용 export 경로

| 항목 | 값 | 근거 |
|---|---|---|
| 논리 크기 | **10 × 8 inch** (기본) | `constants.py:103` `page_w_in:10.0, page_h_in:8.0` |
| 픽셀 환산 | `inch × 96 dpi` → **960 × 768 px** | `figure.py:22,29-32` `FIG_DPI=96` |
| 플롯 영역 | Left 17.9% / Top 11.58% / Width 68.2% / Height 71.77% (Origin 규격), `margin=0` | `constants.py:103-104`, `figure.py:35-51` |
| 축 스타일 | 4면 mirror, `ticks="inside"`, 그리드 없음, 축선 1.5px, major tick 6 / minor 3 | `figure.py:24-26,186-194` |
| 지수 표기 | `exponentformat="E"` → `1E-11` 형식 | `figure.py:192`, `SPEC.md:14` |
| 폰트 | 기본 **Myriad Pro**, 제목·눈금 **30pt**, 범위 6~50 | `constants.py:116,70-71` |
| 네이티브 범례 | **`showlegend=False`** — Plotly 범례 대신 커스텀 인셋 사용 | `figure.py:233`, `SPEC.md:43` |
| 인셋 정렬 | 측정 순서와 무관하게 Dark→940→850→740→625→530→470→405→365 고정 | `insets.py:12-23` `INSET_ORDER_PRIORITY` |
| 화면 미리보기 | CSS 축소만 담당(0.30~1.00 배율). **figure 자체는 축소하지 않음** | `figure.py:3-5`, `layout.py` |

**export 경로 (서버가 아닌 브라우저에서 렌더)**: kaleido 등 서버 사이드 이미지 엔진을 두지 않고, figure를 JSON으로 직렬화해 HTML 컴포넌트에 심은 뒤 `Plotly.downloadImage`로 클라이언트에서 굽는다.
- **PNG** — 완전 투명 배경(`paper_bgcolor/plot_bgcolor = rgba(0,0,0,0)`), 내보내기 시 인셋 배경 불투명도 0·테두리 off로 강제 (`summary.py` `_fig_json(transparent=True)`)
- **JPG** — 흰 배경 고정 (`paper_bgcolor="white"`)
- **해상도** — `width:960, height:768, scale:3` → **2880 × 2304 px** (10×8인치 유지 시 **288 dpi**, UI 표기 "300dpi 상당")
- **일괄 내보내기** — 파일 2개 이상일 때 우측 패널에 세로 배치로 노출. 성능지표 통합 CSV 1개 + PNG 일괄 + JPG 일괄. 이미지는 ZIP이 아니라 `for` 루프에서 파일당 700ms 간격으로 순차 다운로드하며 버튼에 `내보내는 중… (n/N)` 진행 표시.

---

### 연계 구조

#### 상류 — 측정 시스템 (`C:\Users\mintj\Kiethly_4200`, `pd_iv_station.py` 91,646 bytes)

Keithley 4200(KITE) + Mightex BioLED 드라이버를 제어하는 별도 자동화 스테이션이 **이 앱이 읽는 포맷을 직접 생성**한다. 두 저장소가 규약으로 맞물려 있음이 소스에서 확인된다.

| 매칭 항목 | 측정 시스템(생성) | 분석 앱(소비) |
|---|---|---|
| 파일명 | `f"({safe_filename(display_name)})[{bracket}].xlsx"` — `pd_iv_station.py:551` | `re.search(r"\(([^)]*)\)")` + `re.search(r"\[([^\]]+)\]")` — `parsing.py:226-231` |
| 시트명 | `"Data" if i == 0 else f"Append{i}"` — `:532` | `_sheet_sort_key` (Data 우선, Append 숫자순) — `parsing.py:21-29` |
| 컬럼 | `ws.append(["AnodeV","AnodeI","Status"])` — `:537` | `AnodeV`/`AnodeI`만 선택, `Status`는 무시 — `parsing.py:215` |
| 조건 블록 | `"Initial Run" if i == 0 else f"Append {i}"` + `["Range I", ...]` — `:543-546` | 동일 토큰으로 블록 추적 — `parsing.py` `_parse_settings` |
| 파장 코드 | `LABEL_TO_SYMBOL = {"Dark":"d","940 nm":"8","850 nm":"7",...}` — `:67-69` | `SYMBOL_MAP` 동일 매핑 — `constants.py:8-18` |
| Dark 2회 측정 | `Dark 0→−1V` / `Dark 0→+1V` 버튼 — `:1061-1062` | Dark 트레이스 concat 후 보간 — `summary.py:90-97` |

측정 시스템 소스에 **분석 앱을 명시적으로 참조한 주석**이 있어 의존 방향이 분명하다:
- `pd_iv_station.py:60` — *"pd_app/constants.py의 SYMBOL_MAP과 반드시 동일해야 함 (엑셀 브래킷 코드용)."*
- `pd_iv_station.py:535-536` — *"pd_app는 AnodeV/AnodeI 두 컬럼만 이름으로 골라 읽으므로 Status 열이 추가로 있어도 무시될 뿐 호환에 영향 없음(재검증 완료)."*
- `pd_iv_station.py:53-54` — *"실제 KITE 산출물(예: example/15s_1 [dd876543].xls Settings 시트)의 'Range I' 값이 '100uA'처럼 숫자·단위 사이에 공백이 없다 — 그 표기를 그대로 따른다."*

즉 **측정 자동화 → 분석·시각화**가 파일 규약 하나로 무결하게 연결된 파이프라인이며, 이 앱의 파서는 실제 장비 산출물(`example/15s_1 [dd876543].xls`, 195,072 bytes, 시트 10개)을 기준으로 역설계·검증되었다.

#### 하류 — 최적화 시스템으로의 출력 스키마

일괄 내보내기 CSV(`_bulk_report_csv` → `_write_report`, `summary.py:254-300`)의 정확한 스키마. 파일당 1블록이 반복되며, 일괄 모드에서는 데이터 요약을 빼고 **성능지표만** 기록한다.

```
# Photodetector I-V Studio — bulk report (N files)

# file,<파일명 stem>
# V_op1 (V),<float>
# V_op2 (V),<float>
# Area,<float>,<cm2|mm2>
# Irradiance unit,mW/cm2

# Performance metrics
Wavelength,E_e (mW/cm2),R_<v1>V (A/W),D*_<v1>V (Jones),R_<v2>V (A/W),D*_<v2>V (Jones)
940 nm,1.0,<float>,<float>,<float>,<float>
...
```

| 컬럼명 | 단위 | 형식 | 비고 |
|---|---|---|---|
| `Wavelength` | — | 문자열 | `Dark` 제외, 파장 라벨(`940 nm` 등) |
| `E_e (mW/cm2)` | mW/cm² | float | 기본값 **1.0** (전 파장 고정) |
| `R_<v1>V (A/W)` | A/W | float 또는 공란 | `<v1>`은 V_op1을 `%g` 포맷(예: `R_-1V (A/W)`) |
| `D*_<v1>V (Jones)` | Jones | float 또는 공란 | 컬럼명이 **동작전압에 따라 동적 생성**됨 |
| `R_<v2>V (A/W)` | A/W | float 또는 공란 | `<v2>` 기본 `1` → `R_1V (A/W)` |
| `D*_<v2>V (Jones)` | Jones | float 또는 공란 | |

- 인코딩 **UTF-8 BOM**(`utf-8-sig`) — 엑셀 한글 깨짐 방지
- 계산 불가 셀은 빈 값(파이썬 `None` → CSV 공란). 화면 표시는 `N/A`, 파일은 공란으로 구분
- ⚠️ **주의: 컬럼명이 고정이 아니다.** V_op를 바꾸면 헤더 문자열이 함께 바뀌므로, 하류 시스템이 컬럼명을 하드코딩하면 깨진다. 접두사(`R_`, `D*_`) 매칭 권장.

**최적화 시스템 자체와의 연계는 확인 불가.** 로컬에 존재하는 인접 프로젝트를 확인한 결과 `c:/Users/mintj/equip_system`은 Django 기반 **장비 예약 시스템**(`reservations` 앱, `db.sqlite3`)으로 파라미터 최적화기가 아니며, 이 CSV를 소비하는 코드는 발견되지 않았다. 현재 연계는 **파일 기반 단방향 export**까지만 구현되어 있다.

---

### 설계 트레이드오프와 실패 기록

**1) 서버 렌더링 포기 → 클라이언트 렌더링 (의도적 트레이드오프)**
kaleido로 서버에서 이미지를 구우면 ZIP 하나로 묶어 내보낼 수 있지만, 무겁고 Streamlit Cloud에서 불안정하다고 판단해 채택하지 않았다. 대가로 **일괄 내보내기가 파일 수만큼 개별 다운로드**가 되고, 브라우저의 다중 다운로드 허용 팝업이 뜬다. 이 제약을 숨기지 않고 UI 캡션과 매뉴얼에 명시하는 쪽을 택했다.

**2) 완전 자동(auto range) 포기 → 의도적 수동 고정**
Y축 auto range가 0 교차점의 노이즈 바닥(~1E-16)까지 따라가 9 decades로 늘어나 논문 그림과 어긋났다. **자동화가 결과를 악화시키는 지점**이라 판단해 1E-11~1E-5 고정을 기본값으로 삼았다(`constants.py:110-112`).

**3) 리팩터링 금지 구역 설정**
검증이 끝난 파싱·마크업 함수 9개는 모듈 분해 시 **로직 변경을 금지**하고 AST 동일성으로 게이트했다. AI에게 넓은 재량을 주면 검증된 로직까지 "개선"하려 드는 문제를, 코드 리뷰가 아니라 기계적 검사로 차단한 사례.

**4) 실패 기록 — 파서가 SMU 컬럼 뒤바뀜을 처리하지 못함**
`Range I 불일치 경고 — 100uA, N/A` 오경고. 원인은 Keithley가 블록마다 SMU1/SMU2 컬럼 순서를 바꿔 쓰는데 파서가 2번째 컬럼만 고정 참조한 것. **첫 수정안(값 있는 컬럼 전수 스캔)은 증상은 없앴지만 근거가 약했고**, 사용자 지적으로 "Voltage Sweep을 수행하는 SMU 기준"이라는 물리적으로 옳은 기준으로 재수정했다. 예제 파일에서 `Data`=col1 / `Append*`=col2로 실제 위치가 다름을 확인해 검증.

**5) 실패 기록 — Streamlit 위젯 키 생명주기 (같은 함정 3회 재발)**
Streamlit은 위젯 키가 이미 존재하면 `value=`/`default=`를 무시한다. 이 함정이 세 곳에서 각각 다른 증상으로 나타났다.
- 프리셋 적용 → 모델은 바뀌는데 UI가 안 바뀜 → `bump_rev()`로 키 epoch 증가 (`presets.py:569-583`)
- 인셋 3×3 위치 버튼 → number_input이 방금 쓴 값을 되돌림 → 해당 키만 직접 재주입 (`panel_inset.py:69-73`)
- **파일 추가 → 새 파일로 자동 전환 안 됨** (본 세션에서 발견·수정). 파일 **제거** 경로에는 이미 키 삭제 처리가 있었으나 **추가** 경로에만 누락돼 있었다. AppTest로 `파일 B 추가 → active=A 복귀`를 재현한 뒤 `_ingest`에 키 삭제를 추가하고 재검증(`active=B` 확인).

**6) 실패 기록 — 중복 기능을 뒤늦게 발견**
트레이스 패널의 "텍스트" 입력칸이 `legend_raw`를 편집했으나, `showlegend=False`라 **그래프에 표시되지 않는 값**이었다. 실제로 보이는 인셋 텍스트는 별도 필드(`inset_raw`)가 담당. 사용자가 "이거 왜 있냐"고 물어 확인한 뒤 제거했다. 초기 요구(D1: Plotly 레전드 제거)와 잔존 UI가 정합하지 않은 채 남아 있던 사례.

**7) 남은 부채**
- **자동화된 회귀 테스트가 저장소에 없다.** AppTest 하네스를 매번 임시로 작성해 검증하고 버렸다. 같은 클래스의 위젯 키 버그가 3회 재발한 점을 고려하면, 이 하네스를 커밋했어야 했다.
- `st.components.v1.html` 의존. Streamlit이 "removed after 2026-06-01" 경고 중이며 배포 로그에도 매 렌더 출력된다. 매뉴얼·배율·드래그·이미지 내보내기가 전부 여기 의존해 업그레이드 시 광범위하게 깨질 수 있다(`SPEC.md:92-93`에 리스크로 기록됨).
- 커밋 메시지 품질 편차. 40개 중 `asd`, `ㅁ`, `a`, `g`, `q2` 등 내용을 알 수 없는 메시지가 다수.

---

### 정량 결과

| 항목 | 수치 | 확인 명령 |
|---|---|---|
| 개발 기간 | **7일** (2026-07-19 → 07-25) | `git log --reverse/-1 --format="%ci"` |
| 총 커밋 | **40** | `git rev-list --count HEAD` |
| 누적 변경 라인 | **+7,518 / −1,217 (순증 6,301)** | `git log --pretty=tformat: --numstat \| awk` |
| Python 소스 | **4,207줄** (22개 파일) | `git ls-files '*.py' \| xargs wc -l` |
| JS 소스 | **266줄** (커스텀 컴포넌트) | `git ls-files '*.js' \| xargs wc -l` |
| 설계 문서 | **414줄** (PLAN 321 + SPEC 93) | `wc -l PLAN.md SPEC.md` |
| 원본 모놀리스 | **1,184줄** → 패키지 22파일로 분해 | `wc -l pd_app/_legacy_reference.py.txt` |
| 런타임 의존성 | **7개** (streamlit, plotly, pandas, numpy, xlrd, openpyxl, pyarrow) | `cat requirements.txt` |
| 일별 커밋 분포 | 07-19: 1 / 07-20: 5 / **07-21: 21** / 07-22: 11 / 07-23: 1 / 07-25: 1 | `git log --format="%ci" \| cut -c1-10 \| sort \| uniq -c` |
| 세션 도구 호출 | **143회** (기록이 남은 구간) | 세션 jsonl 파싱 |
| 세션 레코드 | **649건 / 1.71 MB** | 위와 동일 |
| 커밋된 테스트 | **0개** | `git ls-files \| grep -iE "test\|conftest"` |

**수작업 대비 시간 절감량: 확인 불가.** 도입 전 Origin 수작업 소요 시간을 측정한 기록이 저장소·문서에 없어, 정량 비교를 제시할 근거가 없다. 대신 다음은 코드로 확인된다 — 파일 1개 업로드 시 **최대 8개 트레이스**의 라벨·색·인셋 순서가 자동 지정되고(`SYMBOL_MAP` 9종, `INSET_ORDER_PRIORITY` 9종), **파장별 R·D\*가 2개 동작전압에서 동시 산출**되며, 다중 파일은 **버튼 1회로 통합 CSV + 전 파일 PNG/JPG**가 나온다.

### 객관적 증거

- **배포**: `photodetector-studio.streamlit.app` — 실 배포 로그 파일이 저장소에 포함(`example/logs-jun0land-photodetector-app-main-app.py-2026-07-22T07_04_31.045Z.txt`, 208줄). 로그상 `🚀 Starting up repository: 'photodetector-app', branch: 'main'`, 의존성 46패키지 설치, `🔄 Updated app!` 재배포 4회 기록.
- **실제 장비 산출물 기반 검증**: `example/15s_1 [dd876543].xls` (195,072 bytes). 실측 구조 — 시트 10개(`Data`, `Calc`, `Settings`, `Append1~7`), Settings 344행×3열, 데이터 시트 201~401 포인트.
- **설계 문서**: `SPEC.md`(요구사항 8섹션 + 불변 결정 + 리스크), `PLAN.md`(검증 사실 V1~V17 표, 모듈 분할, 공개 시그니처 고정).
- **파이프라인 연계**: 상류 측정 시스템 `Kiethly_4200/pd_iv_station.py`가 이 앱의 `SYMBOL_MAP`·컬럼·시트·파일명 규약을 명시적으로 참조하며 호환 산출물을 생성(코드 주석에 상호 참조 3건).
- **AI 협업 기록**: 세션 로그 `~/.claude/projects/c--Users-mintj-photodetector-app/bbb67044-....jsonl` (1.71MB, 649레코드, 2026-07-22 ~ 08-03). 모델별 어시스턴트 메시지 — opus-4-8 215 / sonnet-5 39 / opus-5 28.
- **미확인 항목 명시**: 개발 초기(07-19 ~ 07-22 오전) 세션 기록 부재, 커스텀 커맨드·스킬·훅·MCP 전부 없음, 커밋된 자동 테스트 없음, 최적화 시스템 연계 미구현, 수작업 대비 시간 절감 측정치 없음.
