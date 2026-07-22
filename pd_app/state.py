"""세션 스키마 / 접근자 / 위젯키. PLAN §2 의 구현.

WP0 이후 READ-ONLY. 패널은 여기 있는 공개 함수만 쓴다.
"""

import copy
import hashlib
import uuid
from datetime import datetime, timezone

import streamlit as st

from pd_app import constants
from pd_app.parsing import parse_file


def boot():
    """세션 초기화. 멱등 — 매 rerun 마다 호출해도 안전하다."""
    if "pd" in st.session_state:
        return
    st.session_state["pd"] = {
        "version": 1,
        "files": {},          # {fid: {"fid","name","sha","bytes","added_at","settings"}}
        "order": [],          # [fid...] 배너 표시 순서
        "active": None,
        "rev": 0,             # 위젯키 epoch
        "presets": {},        # {name: preset}
        "current_format": copy.deepcopy(constants.DEFAULTS),  # 새 파일이 상속
    }


def S():
    """세션 루트 dict. boot() 이 아직이면 방어적으로 부른다 (멱등하므로 무해)."""
    boot()
    return st.session_state["pd"]


# ---------------- 위젯키 ----------------
def wkey(group, name, *, fid=None):
    """위젯키 생성. rev 와 fid 둘 다 load-bearing 이다 (PLAN §2.3).

    - fid: 파일 전환 시 값 누출 방지(함정1). 키가 같으면 다른 파일 값이 새어 들어온다.
    - rev: 키가 이미 있으면 Streamlit 이 value= 를 무시(함정2) -> 프리셋을 적용해도
      UI 가 안 바뀐다. bump_rev() 로 epoch 을 올려 전 키를 새것으로 만든다.
    """
    return f"w:{S()['rev']}:{fid or '__global__'}:{group}:{name}"


def bump_rev():
    """위젯키 epoch 증가. 호출 시점은 프리셋 적용 / 전체 적용 / 기본값 리셋 뿐.
    파일 전환·드래그에서는 절대 호출하지 않는다 (PLAN §2.3).
    """
    S()["rev"] += 1


def tkey_of(trace, occurrence):
    """트레이스 키. 같은 label 이 여러 번 나오므로 등장 순번으로 구분한다."""
    return f"{trace['label']}#{occurrence}"


# ---------------- 파일 ----------------
def add_file(name, data):
    """파일 추가 -> fid 반환. 같은 sha1 이면 기존 fid 를 그대로 돌려준다(중복 제거)."""
    s = S()
    sha = hashlib.sha1(data).hexdigest()
    for f in s["files"].values():
        if f["sha"] == sha:
            return f["fid"]

    # 파싱 실패는 호출자가 표시한다. 상태는 파싱 성공 후에만 건드려서
    # 반쯤 추가된 파일이 남지 않게 한다. (parse_file 은 @st.cache_data 라 재호출이 싸다)
    parsed = parse_file(data, name)

    # fid 는 파일명이 아니다 — 파일명은 충돌하고 바뀐다
    fid = uuid.uuid4().hex[:8]

    settings = copy.deepcopy(s["current_format"])
    # 상속받은 traces 는 다른 파일의 TKey 라 새지 않게 처음부터 다시 만든다.
    settings["traces"] = {}
    seen = {}
    for i, t in enumerate(parsed["traces"]):
        label = t["label"]
        seen[label] = seen.get(label, 0) + 1
        tk = tkey_of(t, seen[label])
        # 절대 무스타일로 두지 않는다: 파장 기본색 -> 없으면 폴백 사이클
        color = constants.DEFAULT_TRACE_COLORS.get(
            label, constants.FALLBACK_CYCLE[i % len(constants.FALLBACK_CYCLE)]
        )
        settings["traces"][tk] = {
            "label": label,
            "visible": True,
            "color": color,
            "dash": "solid",
            "width": settings["style"]["line_width"],
            "legend_raw": t["legend"],
            "inset_raw": t["label"],
            # 같은 파장(Dark 등)이 여러 번 측정되면 첫 등장만 인셋에 포함하고 중복은 해제한다.
            "include_in_inset": seen[label] == 1,
        }

    # 성능 지표(측정 조건)는 per-file. 파장별 광조도(E_e)를 이 파일의 파장 라벨로
    # 초기화한다 (Dark 제외, 빈 값 = None). current_format 이 metrics 를 상속하지만
    # irradiance 는 파일마다 파장이 다르므로 여기서 새로 만든다.
    settings.setdefault("metrics", copy.deepcopy(constants.DEFAULTS["metrics"]))
    settings["metrics"]["irradiance"] = {
        tr["label"]: None
        for tr in settings["traces"].values() if tr["label"] != "Dark"
    }

    s["files"][fid] = {
        "fid": fid,
        "name": name,
        "sha": sha,
        "bytes": data,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "settings": settings,
    }
    s["order"].append(fid)
    # 업로드 직후엔 그 파일을 보고 싶은 게 보통이므로 항상 활성으로 전환한다
    s["active"] = fid
    return fid


def remove_file(fid):
    """파일 제거. 모르는 fid 면 아무것도 안 한다."""
    s = S()
    if fid not in s["files"]:
        return
    idx = s["order"].index(fid) if fid in s["order"] else None
    del s["files"][fid]
    if idx is not None:
        s["order"].pop(idx)

    if s["active"] != fid:
        return  # 활성 파일이 아니었으면 건드리지 않는다
    if not s["order"]:
        s["active"] = None
    else:
        # 새 order 의 같은 인덱스 = 다음 파일, 없으면 이전 파일
        j = min(idx if idx is not None else 0, len(s["order"]) - 1)
        s["active"] = s["order"][j]


def active_fid():
    """활성 파일 fid (없으면 None)."""
    return S()["active"]


def set_active(fid):
    """활성 파일 전환. 모르는 fid 는 무시."""
    s = S()
    if fid in s["files"]:
        s["active"] = fid


def file_settings(fid):
    """해당 파일의 settings. 모르는/None fid 면 None (KeyError 아님).

    살아있는 dict 를 그대로 돌려준다 — 패널이 제자리에서 변경한다.
    모델이 유일한 진실 (PLAN §2.3).
    """
    s = S()
    if fid is None or fid not in s["files"]:
        return None
    return s["files"][fid]["settings"]
