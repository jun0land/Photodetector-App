"""Keithley 측정 파일 파싱 (원본 app.py 656-867 축자 이동, 로직 변경 금지).

보호 대상: parse_file, _load_sheets, _parse_settings, _settings_frame,
_sheet_sort_key, _is_data_sheet.
"""

from __future__ import annotations

import contextlib
import io
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
        value = cells[1] if len(cells) > 1 else ""
        if not name:
            continue

        if re.match(r"^initial\s*run$", name, flags=re.IGNORECASE):
            current = "Data"
            if current not in order:
                order.append(current)
            result.setdefault(current, "N/A")
            continue
        m = re.match(r"^append\s*(\d+)$", name, flags=re.IGNORECASE)
        if m:
            current = f"Append{int(m.group(1))}"
            if current not in order:
                order.append(current)
            result.setdefault(current, "N/A")
            continue

        if re.match(r"^range\s*i$", name, flags=re.IGNORECASE) and current:
            result[current] = value if value else "N/A"

    return result, order


# 💡 [신규 추가] Dark 0V 영점 오프셋(I_offset) 보정 함수
def _apply_dark_zero_offset_correction(traces: list[dict]) -> None:
    """Dark Current의 0V 지점 오프셋(I_offset)을 추출하여 모든 트레이스(Dark + Photo)에서 일괄 차감합니다."""
    i_offset = None

    # 1. Dark 트레이스에서 V = 0V 에 가장 가까운 지점의 전류값(I_offset) 검색
    for t in traces:
        if t.get("label") == "Dark" and t.get("df") is not None and not t["df"].empty:
            df = t["df"]
            if "AnodeV" in df.columns and "AnodeI" in df.columns:
                # 0V에 가장 가까운 행 검색
                min_v_idx = (df["AnodeV"].abs()).idxmin()
                # 0V와 가까운 지점(예: 0.05V 이내)인 경우 오프셋으로 인정
                if abs(df.loc[min_v_idx, "AnodeV"]) < 0.05:
                    i_offset = float(df.loc[min_v_idx, "AnodeI"])
                    break

    # 2. Dark 0V 오프셋이 발견된 경우, 모든 트레이스(Dark & Photo)의 AnodeI 데이터에서 일괄 차감
    if i_offset is not None and i_offset != 0.0:
        for t in traces:
            if t.get("df") is not None and not t["df"].empty:
                if "AnodeI" in t["df"].columns:
                    t["df"]["AnodeI"] = t["df"]["AnodeI"] - i_offset


@st.cache_data(show_spinner=False)
def parse_file(file_bytes, file_name):
    """파일 바이트 -> 트레이스 목록. UploadedFile 대신 bytes 로 캐싱."""
    sheets, engine = _load_sheets(file_bytes)
    warns = []

    data_names = [n for n, d in sheets.items() if _is_data_sheet(d)]
    data_names.sort(key=_sheet_sort_key)
    if not data_names:
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

    # 💡 [핵심 추가] 파싱된 traces 데이터에 Dark 0V 영점 오프셋 자동 차감 보정 적용
    _apply_dark_zero_offset_correction(traces)

    return {"traces": traces, "warnings": warns, "data_names": data_names}