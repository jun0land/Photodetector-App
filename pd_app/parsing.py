"""Keithley 측정 파일 파싱 (원본 app.py 656-867 축자 이동, 로직 변경 금지).

보호 대상: parse_file, _load_sheets, _parse_settings, _settings_frame,
_sheet_sort_key, _is_data_sheet.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import warnings

import numpy as np
import pandas as pd
import streamlit as st

from pd_app.constants import SEP_TOKEN, SYMBOL_MAP


def _sheet_sort_key(name):
    """'Data' 먼저, 그 다음 Append 뒤 숫자 기준 정렬 (Append10 > Append9)."""
    n = str(name).strip()
    if n.lower() == "data":
        return (0, 0)
    m = re.match(r"^append\s*(\d+)$", n, flags=re.IGNORECASE)
    if m:
        return (1, int(m.group(1)))
    return (2, 0)


def _is_data_sheet(df):
    if not isinstance(df, pd.DataFrame):
        return False
    cols = {str(c).strip() for c in df.columns}
    return "AnodeV" in cols and "AnodeI" in cols


@contextlib.contextmanager
def _quiet():
    """구형 .xls 는 xlrd 가 OLE2 경고를 stdout 으로 뱉는다 -> 사용자에게 노출하지 않음."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


def _read_excel(file_bytes, engine=None, **kwargs):
    if engine:
        kwargs["engine"] = engine
    with _quiet():
        return pd.read_excel(io.BytesIO(file_bytes), **kwargs)


def _load_sheets(file_bytes):
    """구형 Keithley .xls 대응: 기본 -> xlrd -> openpyxl -> read_html -> tab 구분 순으로 시도.

    반환: (sheets_dict, engine)  - engine 은 Settings 재읽기에 그대로 사용.
    """
    errors = []
    for engine in (None, "xlrd", "openpyxl"):
        try:
            sheets = _read_excel(file_bytes, engine, sheet_name=None)
            if isinstance(sheets, dict) and sheets:
                return sheets, engine
        except Exception as e:  # noqa: BLE001
            errors.append(f"read_excel(engine={engine}): {e}")

    try:
        with _quiet():
            tables = pd.read_html(io.BytesIO(file_bytes))
        out = {}
        idx = 0
        for t in tables:
            if _is_data_sheet(t):
                out["Data" if idx == 0 else f"Append{idx}"] = t
                idx += 1
        if out:
            return out, None
        errors.append("read_html: AnodeV/AnodeI 컬럼을 가진 표를 찾지 못함")
    except Exception as e:  # noqa: BLE001
        errors.append(f"read_html: {e}")

    try:
        with _quiet():
            df = pd.read_csv(io.BytesIO(file_bytes), sep="\t")
        if _is_data_sheet(df):
            return {"Data": df}, None
        errors.append("read_csv(tab): AnodeV/AnodeI 컬럼 없음")
    except Exception as e:  # noqa: BLE001
        errors.append(f"read_csv(tab): {e}")

    raise ValueError("파일을 읽을 수 없습니다.\n" + "\n".join(errors))


def _settings_frame(file_bytes, sheets, engine):
    """Settings 는 첫 행이 구분선이라 header=0 이면 소실된다 -> header=None 으로 다시 읽음."""
    key = next((k for k in sheets if str(k).strip().lower() == "settings"), None)
    if key is None:
        return None
    try:
        return _read_excel(file_bytes, engine, sheet_name=key, header=None)
    except Exception:  # noqa: BLE001
        return sheets[key]  # 헤더가 소비된 상태 -> _parse_settings 가 복원 시도


# ---------------- 이 앱이 내보낸 엑셀 다시 읽기 ----------------
# Keithley 원본이 아니라 [내보내기] 로 만든 .xlsx 를 다시 올렸을 때를 처리한다.
# Raw 시트(원본 전류)를 데이터로 쓰고, Info 시트의 설정 JSON 으로 보정값까지 복원한다.
_EXPORT_SETTINGS_KEY = "Settings (JSON)"   # summary._SETTINGS_KEY 의 접두사


def _sheet_raw(file_bytes, sheets, engine, name):
    """시트를 header=None 으로 다시 읽는다 (헤더 2줄이 데이터가 아니라 이름·단위라서)."""
    key = next((k for k in sheets if str(k).strip().lower() == name.lower()), None)
    if key is None:
        return None
    try:
        return _read_excel(file_bytes, engine, sheet_name=key, header=None)
    except Exception:  # noqa: BLE001
        return None


def _export_info(df):
    """Info 시트를 {키: 값} 으로. 설정 JSON 은 파싱해 'settings' 로 따로 담는다."""
    out, settings = {}, None
    if not isinstance(df, pd.DataFrame) or df.empty or df.shape[1] < 2:
        return out, settings
    for i in range(len(df)):
        k = df.iloc[i, 0]
        v = df.iloc[i, 1]
        if k is None or (isinstance(k, float) and pd.isna(k)):
            continue
        k = str(k).strip()
        if k.startswith(_EXPORT_SETTINGS_KEY):
            try:
                settings = json.loads(str(v))
            except Exception:  # noqa: BLE001
                settings = None
            continue
        out[k] = v
    return out, settings


def _export_traces(df):
    """Raw/Processed 시트 → [(이름, V, I)].

    1행=Long Name, 2행=Units. 단위가 'V' 인 열이 X 이고, 그 뒤의 'A' 열들이 그 X 를
    공유하는 Y 다. 구형(트레이스마다 V,A 반복)·신형(X 공유) 배치가 모두 이 규칙으로
    읽힌다 — 열 이름 형식에 기대지 않아 포맷이 바뀌어도 덜 깨진다.
    """
    if not isinstance(df, pd.DataFrame) or len(df) < 3 or df.shape[1] < 2:
        return []
    names = [("" if pd.isna(x) else str(x).strip()) for x in df.iloc[0]]
    units = [("" if pd.isna(x) else str(x).strip().upper()) for x in df.iloc[1]]
    body = df.iloc[2:].reset_index(drop=True)

    out, cur_v = [], None
    for c in range(df.shape[1]):
        col = pd.to_numeric(body[c], errors="coerce").to_numpy(dtype=float)
        if units[c] == "V":
            cur_v = col
        elif units[c] == "A" and cur_v is not None:
            nm = names[c]
            for suffix in (" |I|", " I"):      # 신형 '940 nm |I|' / 구형 '940 nm I'
                if nm.endswith(suffix):
                    nm = nm[: -len(suffix)]
                    break
            m = np.isfinite(cur_v) & np.isfinite(col)
            if int(m.sum()) >= 2:
                out.append((nm.strip(), cur_v[m], col[m]))
    return out


def _parse_exported(file_bytes, sheets, engine):
    """내보낸 엑셀이면 파싱 결과를, 아니면 None 을 돌려준다.

    전류는 **Raw 시트**(무보정·부호 유지)를 쓴다. Processed/Plot 은 보정이 이미 들어간
    값이라 다시 올리면 보정이 두 번 걸린다.
    """
    raw = _sheet_raw(file_bytes, sheets, engine, "Raw")
    items = _export_traces(raw)
    if not items:
        return None

    info_map, restored = _export_info(_sheet_raw(file_bytes, sheets, engine, "Info"))
    range_i = (restored or {}).get("range_i") or {}

    traces, warns = [], []
    seen = {}
    for nm, v, i in items:
        label = nm.split(" #")[0].strip() or nm       # 'Dark #2' → 'Dark'
        seen[label] = seen.get(label, 0) + 1
        traces.append({
            "label": label,
            "df": pd.DataFrame({"AnodeV": v, "AnodeI": i}),
            "range_i": str(range_i.get(nm, info_map.get(nm, "N/A")) or "N/A"),
            "sheets": ["Raw"],
        })
    for t in traces:
        seen[t["label"]] = seen.get(t["label"], 0)
    warns.append("이 앱이 내보낸 엑셀을 다시 읽었습니다 — 전류는 보정 전 `Raw` 시트를 "
                 "사용합니다." + (" 저장된 보정 설정도 복원했습니다."
                                  if restored else " (설정 정보가 없어 기본값으로 엽니다.)"))

    seen2 = {}
    for t in traces:
        seen2[t["label"]] = seen2.get(t["label"], 0) + 1
        suffix = "" if seen2[t["label"]] == 1 else f" #{seen2[t['label']]}"
        t["legend"] = f"{t['label']} ({t['range_i']}){suffix}"

    sample = str(info_map.get("Sample") or "").strip()
    return {"traces": traces, "warnings": warns,
            "data_names": [nm for nm, _, _ in items],
            "sample": sample, "i_offset": _dark_zero_offset(traces),
            "restored": restored}


def _parse_settings(df):
    """Settings 프레임에서 블록별 'Range I' 추출."""
    result = {}
    order = []
    if not isinstance(df, pd.DataFrame) or df.shape[1] < 1 or df.empty:
        return result, order

    rows = []
    cols = list(df.columns)
    if not all(isinstance(c, (int, np.integer)) or str(c).startswith("Unnamed") for c in cols):
        rows.append([str(c) for c in cols])
    for i in range(len(df)):
        rows.append([df.iloc[i, j] for j in range(df.shape[1])])

    current = None
    sweep_col = None  # 현재 블록에서 Voltage Sweep 을 수행하는 SMU 의 컬럼 인덱스
    for row in rows:
        cells = []
        for v in row:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                cells.append("")
            else:
                cells.append(str(v).strip())
        if not cells:
            continue
        joined = " ".join(cells)
        if "=====" in joined or SEP_TOKEN in joined:
            continue
        name = cells[0]
        if not name:
            continue

        if re.match(r"^initial\s*run$", name, flags=re.IGNORECASE):
            current = "Data"
            sweep_col = None
            if current not in order:
                order.append(current)
            result.setdefault(current, "N/A")
            continue
        m = re.match(r"^append\s*(\d+)$", name, flags=re.IGNORECASE)
        if m:
            current = f"Append{int(m.group(1))}"
            sweep_col = None
            if current not in order:
                order.append(current)
            result.setdefault(current, "N/A")
            continue

        # SMU1/SMU2 중 Voltage Sweep(측정 대상)을 수행하는 컬럼을 기억해 둔다.
        if re.match(r"^forcing\s*function$", name, flags=re.IGNORECASE) and current:
            sweep_col = next(
                (i for i in range(1, len(cells))
                 if re.search(r"sweep", cells[i], flags=re.IGNORECASE)),
                None,
            )
            continue

        if re.match(r"^range\s*i$", name, flags=re.IGNORECASE) and current:
            value = ""
            if sweep_col is not None and sweep_col < len(cells):
                value = cells[sweep_col]
            if not value:  # sweep 컬럼을 못 찾았거나 비었으면 값 컬럼 전체를 스캔
                value = next((c for c in cells[1:] if c), "")
            result[current] = value if value else "N/A"

    return result, order


def _dark_zero_offset(traces: list[dict]) -> float | None:
    """Dark 의 0V 부근 전류값 = **표시용** 영점 오프셋. 데이터는 건드리지 않는다.

    암전류를 광전류용 Range I(예: 100uA)로 함께 측정하면 암전류가 그 레인지의 분해능
    바닥에 깔려, 0V 에서 꺼지는 골짜기가 안 보이고 직선처럼 그려진다. 그래프에서만
    이 값을 빼서 골짜기를 복원한다(figure.py).

    성능지표(R·D*)는 이 보정 없이 **raw** 로 계산한다 — 고정 바이어스 I-T 측정에서
    쓰는 정의(I_ph = I_light(V) - I_dark(V))와 방법을 일치시키기 위함.
    """
    for t in traces:
        if t.get("label") == "Dark" and t.get("df") is not None and not t["df"].empty:
            df = t["df"]
            if "AnodeV" in df.columns and "AnodeI" in df.columns:
                min_v_idx = (df["AnodeV"].abs()).idxmin()
                # 0V 와 가까운 지점(0.05V 이내)일 때만 오프셋으로 인정
                if abs(df.loc[min_v_idx, "AnodeV"]) < 0.05:
                    off = float(df.loc[min_v_idx, "AnodeI"])
                    return off if off != 0.0 else None
    return None


@st.cache_data(show_spinner=False)
def parse_file(file_bytes, file_name):
    """파일 바이트 -> 트레이스 목록. UploadedFile 대신 bytes 로 캐싱."""
    sheets, engine = _load_sheets(file_bytes)
    warns = []

    data_names = [n for n, d in sheets.items() if _is_data_sheet(d)]
    data_names.sort(key=_sheet_sort_key)
    if not data_names:
        # Keithley 원본이 아니면 이 앱이 내보낸 엑셀일 수 있다 (Raw/Info 시트).
        exported = _parse_exported(file_bytes, sheets, engine)
        if exported is not None:
            return exported
        raise ValueError("AnodeV / AnodeI 컬럼을 가진 데이터 시트를 찾지 못했습니다.")

    frames = {}
    for n in data_names:
        d = sheets[n].copy()
        d.columns = [str(c).strip() for c in d.columns]
        d = d[["AnodeV", "AnodeI"]].apply(pd.to_numeric, errors="coerce").dropna()
        frames[n] = d

    range_map, _ = _parse_settings(_settings_frame(file_bytes, sheets, engine))
    if range_map and not any(n in range_map for n in data_names):
        warns.append(
            "Settings 블록 이름을 데이터 시트와 매칭하지 못했습니다. "
            "Range I 를 N/A 로 표시합니다."
        )
        range_map = {}

    # 파일명 서식: (샘플명) [측정순서]. 소괄호/대괄호 밖 텍스트는 무시한다.
    m_sample = re.search(r"\(([^)]*)\)", str(file_name))
    sample = m_sample.group(1).strip() if m_sample else ""

    m = re.search(r"\[([^\]]+)\]", str(file_name))
    bracket = m.group(1).strip() if m else ""
    if not bracket:
        warns.append("파일명에서 [] 안의 매핑 문자열을 찾지 못했습니다. 일반 라벨(Trace N)을 사용합니다.")
    elif len(bracket) != len(data_names):
        warns.append(
            f"[] 문자열 길이({len(bracket)})와 데이터 시트 수({len(data_names)})가 "
            "일치하지 않습니다. 일반 라벨(Trace N)을 사용합니다."
        )
        bracket = ""

    if bracket:
        labels = [SYMBOL_MAP.get(ch, f"Unknown({ch})") for ch in bracket]
    else:
        labels = [f"Trace {i + 1}" for i in range(len(data_names))]

    traces = []
    for i, n in enumerate(data_names):
        traces.append({
            "label": labels[i],
            "df": frames[n],
            "range_i": range_map.get(n, "N/A"),
            "sheets": [n],
        })

    seen = {}
    for t in traces:
        seen[t["label"]] = seen.get(t["label"], 0) + 1
        suffix = "" if seen[t["label"]] == 1 else f" #{seen[t['label']]}"
        t["legend"] = f"{t['label']} ({t['range_i']}){suffix}"

    # df 는 raw 그대로 둔다. 0V 오프셋은 값만 실어 보내고 그래프에서만 뺀다.
    # restored=None → Keithley 원본이라 복원할 설정이 없다는 뜻.
    return {"traces": traces, "warnings": warns, "data_names": data_names,
            "sample": sample, "i_offset": _dark_zero_offset(traces),
            "restored": None}