"""프리셋(그래프 포맷) 저장·불러오기·적용. 소유: WP4.

프리셋 스키마와 적용 규칙은 PLAN §3 참조.
- 매칭은 TKey 가 아니라 **label 기준** (파일마다 occurrence 가 다름).
- `visible` / `legend_raw` / `inset_raw` / `sample.text_raw` 는 제외 (파일별 텍스트·선택).
- `load()` 는 절대 raise 하지 않는다. 버전 하위는 `_MIGRATIONS` 체인, 상위/불일치는
  경고 후 best-effort, 누락키는 `constants.DEFAULTS` 로 조용히 채움.
- `apply_to()` 는 반드시 `state.bump_rev()` 를 호출 (PLAN §2.3 함정2).

메시지 규약: 반환 문자열 중 `INFO_PREFIX` 로 시작하는 것은 경고가 아니라 안내다
(패널이 st.info 로, 나머지는 st.warning 으로 라우팅한다).
"""

from __future__ import annotations

import copy
import json
import math
import re
from datetime import datetime, timezone

from pd_app import constants, state

SCHEMA_VERSION = 1
SCHEMA_ID = "photodetector-app/format"
INFO_PREFIX = "[정보] "

_D = constants.DEFAULTS

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# 인셋 위치는 PLAN §4.3 의 드래그 clamp 와 같은 범위를 쓴다 (드래그↔프리셋 왕복에서 값이
# 조용히 바뀌지 않도록).
_POS_MIN, _POS_MAX = -0.15, 1.15
_WIDTH_MIN, _WIDTH_MAX = 0.5, 20.0
_STANDOFF_MAX = 200

_AXIS_KEYS = ("type", "auto", "min", "max", "dtick", "minor_dtick", "title_standoff")
_TRACE_KEYS = ("color", "dash", "width")
_LEGEND_KEYS = ("x", "y", "xanchor", "yanchor", "width", "border", "border_color",
                "bg_color", "bg_opacity", "font", "font_size")
_SAMPLE_KEYS = ("x", "y", "xanchor", "yanchor", "font_size")
_STYLE_KEYS = ("font_family", "title_font_size", "tick_font_size", "line_width")
_GEOM_KEYS = tuple(_D["geom"].keys())
_TOP_KEYS = ("schema", "version", "name", "created_at", "traces_by_label",
             "axes", "insets", "style", "geom")

_XANCHORS = ("left", "center", "right")
_YANCHORS = ("top", "middle", "bottom")
_AXIS_TYPES = ("linear", "log")
_DASHES = tuple(constants.DASH_OPTIONS.values())

# {n: fn} — 버전 n 프리셋을 n+1 로 올린다 (dict -> dict). 지금은 비어 있다.
# H1 처럼 나중에 스키마가 늘면 여기에 **추가만** 하면 된다 (PLAN §8.7).
_MIGRATIONS: dict = {}


# ---------------- 코어서(coercer) ----------------
# 전부 (value, ok) 를 반환한다. ok=False 면 호출자가 그 필드에 경고를 1회 붙인다.

def _c_bool(v, dflt):
    if isinstance(v, bool):
        return v, True
    if isinstance(v, (int, float)) and v in (0, 1):
        return bool(v), False
    if isinstance(v, str) and v.strip().lower() in ("true", "false"):
        return v.strip().lower() == "true", False
    return dflt, False


def _c_float(v, dflt, lo=None, hi=None, step=None, allow_none=False):
    if v is None:
        return (None, True) if allow_none else (dflt, False)
    if isinstance(v, bool):
        return dflt, False
    ok = True
    if isinstance(v, (int, float)):
        x = float(v)
    elif isinstance(v, str):
        try:
            x = float(v.strip())
        except ValueError:
            return dflt, False
        ok = False  # 타입 위반 -> coerce 했으니 경고
    else:
        return dflt, False
    if not math.isfinite(x):
        return dflt, False
    if step:
        q = round(x / step) * step
        if abs(q - x) > 1e-9:
            ok = False
        x = q
    if lo is not None and x < lo:
        x, ok = float(lo), False
    if hi is not None and x > hi:
        x, ok = float(hi), False
    return x, ok


def _c_int(v, dflt, lo=None, hi=None, allow_none=False):
    if v is None:
        return (None, True) if allow_none else (dflt, False)
    f, _ = _c_float(v, None)
    if f is None:
        return dflt, False
    n = int(round(f))
    ok = isinstance(v, int) and not isinstance(v, bool)
    if lo is not None and n < lo:
        n, ok = int(lo), False
    if hi is not None and n > hi:
        n, ok = int(hi), False
    return n, ok


def _c_choice(v, dflt, options):
    if isinstance(v, str) and v in options:
        return v, True
    if isinstance(v, str):
        low = v.strip().lower()
        for o in options:
            if o.lower() == low:
                return o, False
    return dflt, False


def _c_color(v, dflt):
    if isinstance(v, str) and _HEX_RE.match(v.strip()):
        h = v.strip()
        if len(h) == 4:  # #RGB -> #RRGGBB
            return "#" + "".join(c * 2 for c in h[1:]), False
        return h, True
    return dflt, False


def _c_dtick(v, dflt):
    """dtick / minor_dtick: None · 숫자 · "D1"/"D2" 같은 log 전용 문자열 모두 유효 (V9)."""
    if v is None:
        return None, True
    if isinstance(v, bool):
        return dflt, False
    if isinstance(v, (int, float)):
        return (float(v), True) if math.isfinite(float(v)) else (dflt, False)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None, False
        try:
            return float(s), False
        except ValueError:
            return s, True  # "D1" 등
    return dflt, False


def _c_font(v, dflt, allow_none=False):
    """font: None = style.font_family 상속 (constants.DEFAULTS 주석).

    목록에 없는 폰트는 기본값으로 되돌린다 — 패널의 selectbox 가 index 를 찾지 못한다.
    """
    if v is None and allow_none:
        return None, True
    if isinstance(v, str) and v in constants.FONT_FAMILIES:
        return v, True
    if isinstance(v, str):
        for f in constants.FONT_FAMILIES:
            if f.lower() == v.strip().lower():
                return f, False
    return dflt, False


def _fs(v, dflt):
    """폰트 크기 — SPEC C2 상 전 항목 6~50 통일."""
    return _c_int(v, dflt, lo=constants.FONT_SIZE_MIN, hi=constants.FONT_SIZE_MAX)


def _lw(v, dflt):
    """선 두께 — SPEC C4 상 0.5 간격."""
    return _c_float(v, dflt, lo=_WIDTH_MIN, hi=_WIDTH_MAX, step=constants.LINE_WIDTH_STEP)


# ---------------- 검증 ----------------

class _V:
    """필드 경고를 필드당 1회로 모으고, 미지의 키는 통째로 1회만 경고한다."""

    def __init__(self):
        self.warnings = []
        self.unknown = []
        self._seen = set()

    def bad(self, path, value):
        if path in self._seen:
            return
        self._seen.add(path)
        self.warnings.append(f"`{path}` 값이 올바르지 않아 보정했습니다 (받은 값: {value!r}).")

    def get(self, src, key, path, coercer, dflt, *args, **kw):
        """src 에 key 가 없으면 조용히 기본값 (PLAN §3: 누락키는 경고 없음)."""
        if not isinstance(src, dict) or key not in src:
            return dflt
        val, ok = coercer(src[key], dflt, *args, **kw)
        if not ok:
            self.bad(path, src[key])
        return val

    def unknown_keys(self, src, allowed, prefix):
        if not isinstance(src, dict):
            return
        for k in src:
            if k not in allowed:
                self.unknown.append(f"{prefix}{k}")

    def finish(self):
        uniq = sorted(set(self.unknown))
        if uniq:
            names = ", ".join(f"`{u}`" for u in uniq[:12])
            more = "" if len(uniq) <= 12 else f" 외 {len(uniq) - 12}개"
            self.warnings.append(f"모르는 항목 {len(uniq)}개를 무시했습니다: {names}{more}.")
        return self.warnings


def _sub(src, key):
    v = src.get(key) if isinstance(src, dict) else None
    return v if isinstance(v, dict) else {}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _validate(raw, v):
    """어떤 입력이든 완전한 프리셋 dict 로 만든다. 절대 raise 하지 않는다."""
    if not isinstance(raw, dict):
        raw = {}

    v.unknown_keys(raw, _TOP_KEYS, "")

    name = raw.get("name")
    name = name.strip() if isinstance(name, str) and name.strip() else "이름 없는 프리셋"
    created = raw.get("created_at")
    if not isinstance(created, str) or not created.strip():
        created = _now()

    out = {
        "schema": SCHEMA_ID,
        "version": SCHEMA_VERSION,
        "name": name,
        "created_at": created,
        "traces_by_label": {},
        "axes": {},
        "insets": {},
    }

    # --- traces_by_label ---
    tbl = _sub(raw, "traces_by_label")
    for label, entry in tbl.items():
        if not isinstance(label, str):
            v.unknown.append(f"traces_by_label.{label!r}")
            continue
        dflt_color = constants.DEFAULT_TRACE_COLORS.get(label, constants.FALLBACK_CYCLE[0])
        if not isinstance(entry, dict):
            v.bad(f"traces_by_label.{label}", entry)
            entry = {}
        v.unknown_keys(entry, _TRACE_KEYS, f"traces_by_label.{label}.")
        out["traces_by_label"][label] = {
            "color": v.get(entry, "color", f"traces_by_label.{label}.color", _c_color, dflt_color),
            "dash": v.get(entry, "dash", f"traces_by_label.{label}.dash", _c_choice, "solid", _DASHES),
            "width": v.get(entry, "width", f"traces_by_label.{label}.width", _lw,
                           _D["style"]["line_width"]),
        }

    # --- axes ---
    axes = _sub(raw, "axes")
    v.unknown_keys(axes, ("x", "y"), "axes.")
    for ax in ("x", "y"):
        src = _sub(axes, ax)
        d = _D["axes"][ax]
        v.unknown_keys(src, _AXIS_KEYS, f"axes.{ax}.")
        out["axes"][ax] = {
            "type": v.get(src, "type", f"axes.{ax}.type", _c_choice, d["type"], _AXIS_TYPES),
            "auto": v.get(src, "auto", f"axes.{ax}.auto", _c_bool, d["auto"]),
            "min": v.get(src, "min", f"axes.{ax}.min", _c_float, d["min"], None, None, None, True),
            "max": v.get(src, "max", f"axes.{ax}.max", _c_float, d["max"], None, None, None, True),
            "dtick": v.get(src, "dtick", f"axes.{ax}.dtick", _c_dtick, d["dtick"]),
            "minor_dtick": v.get(src, "minor_dtick", f"axes.{ax}.minor_dtick", _c_dtick,
                                 d["minor_dtick"]),
            "title_standoff": v.get(src, "title_standoff", f"axes.{ax}.title_standoff", _c_int,
                                    d["title_standoff"], 0, _STANDOFF_MAX, True),
        }

    # --- insets ---
    ins = _sub(raw, "insets")
    v.unknown_keys(ins, ("legend", "sample"), "insets.")

    lg, dlg = _sub(ins, "legend"), _D["insets"]["legend"]
    v.unknown_keys(lg, _LEGEND_KEYS, "insets.legend.")
    out["insets"]["legend"] = {
        "x": v.get(lg, "x", "insets.legend.x", _c_float, dlg["x"], _POS_MIN, _POS_MAX),
        "y": v.get(lg, "y", "insets.legend.y", _c_float, dlg["y"], _POS_MIN, _POS_MAX),
        "xanchor": v.get(lg, "xanchor", "insets.legend.xanchor", _c_choice, dlg["xanchor"],
                         _XANCHORS),
        "yanchor": v.get(lg, "yanchor", "insets.legend.yanchor", _c_choice, dlg["yanchor"],
                         _YANCHORS),
        "width": v.get(lg, "width", "insets.legend.width", _c_float, dlg["width"], 0.05, 1.0),
        "border": v.get(lg, "border", "insets.legend.border", _c_bool, dlg["border"]),
        "border_color": v.get(lg, "border_color", "insets.legend.border_color", _c_color,
                              dlg["border_color"]),
        "bg_color": v.get(lg, "bg_color", "insets.legend.bg_color", _c_color, dlg["bg_color"]),
        "bg_opacity": v.get(lg, "bg_opacity", "insets.legend.bg_opacity", _c_float,
                            dlg["bg_opacity"], 0.0, 1.0),
        "font": v.get(lg, "font", "insets.legend.font", _c_font, dlg["font"], True),
        "font_size": v.get(lg, "font_size", "insets.legend.font_size", _fs, dlg["font_size"]),
    }

    sm, dsm = _sub(ins, "sample"), _D["insets"]["sample"]
    v.unknown_keys(sm, _SAMPLE_KEYS, "insets.sample.")
    # text_raw 는 의도적으로 제외 — 샘플 이름은 정의상 샘플별 텍스트 (PLAN §3).
    out["insets"]["sample"] = {
        "x": v.get(sm, "x", "insets.sample.x", _c_float, dsm["x"], _POS_MIN, _POS_MAX),
        "y": v.get(sm, "y", "insets.sample.y", _c_float, dsm["y"], _POS_MIN, _POS_MAX),
        "xanchor": v.get(sm, "xanchor", "insets.sample.xanchor", _c_choice, dsm["xanchor"],
                         _XANCHORS),
        "yanchor": v.get(sm, "yanchor", "insets.sample.yanchor", _c_choice, dsm["yanchor"],
                         _YANCHORS),
        "font_size": v.get(sm, "font_size", "insets.sample.font_size", _fs, dsm["font_size"]),
    }

    # --- style / geom (PLAN §8.5: 선택 블록. 저장 안 했으면 키 자체가 없다) ---
    if isinstance(raw.get("style"), dict):
        stl, dst = raw["style"], _D["style"]
        v.unknown_keys(stl, _STYLE_KEYS, "style.")
        out["style"] = {
            "font_family": v.get(stl, "font_family", "style.font_family", _c_font,
                                 dst["font_family"]),
            "title_font_size": v.get(stl, "title_font_size", "style.title_font_size", _fs,
                                     dst["title_font_size"]),
            "tick_font_size": v.get(stl, "tick_font_size", "style.tick_font_size", _fs,
                                    dst["tick_font_size"]),
            "line_width": v.get(stl, "line_width", "style.line_width", _lw, dst["line_width"]),
        }
    elif "style" in raw and raw["style"] is not None:
        v.bad("style", raw["style"])

    if isinstance(raw.get("geom"), dict):
        gm, dgm = raw["geom"], _D["geom"]
        v.unknown_keys(gm, _GEOM_KEYS, "geom.")
        out["geom"] = {
            "page_w_in": v.get(gm, "page_w_in", "geom.page_w_in", _c_float,
                               dgm["page_w_in"], 1.0, 40.0),
            "page_h_in": v.get(gm, "page_h_in", "geom.page_h_in", _c_float,
                               dgm["page_h_in"], 1.0, 40.0),
            "graph_left_pct": v.get(gm, "graph_left_pct", "geom.graph_left_pct", _c_float,
                                    dgm["graph_left_pct"], 0.0, 100.0),
            "graph_top_pct": v.get(gm, "graph_top_pct", "geom.graph_top_pct", _c_float,
                                   dgm["graph_top_pct"], 0.0, 100.0),
            "graph_width_pct": v.get(gm, "graph_width_pct", "geom.graph_width_pct", _c_float,
                                     dgm["graph_width_pct"], 1.0, 100.0),
            "graph_height_pct": v.get(gm, "graph_height_pct", "geom.graph_height_pct", _c_float,
                                      dgm["graph_height_pct"], 1.0, 100.0),
        }
    elif "geom" in raw and raw["geom"] is not None:
        v.bad("geom", raw["geom"])

    return out


# ---------------- 공개 API ----------------

def extract(fid, name, *, include_style=True, include_geom=True) -> dict:
    """현재 파일 설정에서 프리셋 dict 를 뽑아낸다.

    PLAN §8.5: E1 항목(파장별 색·선 두께·XY 스케일·축 제목 위치·인셋 위치)은 **필수**,
    `style`/`geom` 은 **선택 블록** (저장 UI 의 체크박스 두 개가 여기에 매핑, 둘 다 기본 켜짐).
    """
    settings = state.file_settings(fid)
    if settings is None:
        raise ValueError(f"알 수 없는 fid: {fid!r}")

    label_first = {}
    for tr in settings["traces"].values():
        # 같은 label 은 어차피 같은 항목으로 적용되므로 첫 등장을 대표로 삼는다.
        label_first.setdefault(tr["label"], tr)

    preset = {
        "schema": SCHEMA_ID,
        "version": SCHEMA_VERSION,
        "name": str(name),
        "created_at": _now(),
        # visible 은 제외 — 데이터 선택이지 포맷이 아니다. 다른 파일의 850nm 를 조용히
        # 숨기는 건 고약한 동작이 된다 (PLAN §3).
        "traces_by_label": {
            label: {"color": tr["color"], "dash": tr["dash"], "width": float(tr["width"])}
            for label, tr in label_first.items()
        },
        "axes": {ax: {k: settings["axes"][ax][k] for k in _AXIS_KEYS} for ax in ("x", "y")},
        "insets": {
            # legend_raw / inset_raw / sample.text_raw 는 파일별 텍스트라 제외.
            "legend": {k: settings["insets"]["legend"][k] for k in _LEGEND_KEYS},
            "sample": {k: settings["insets"]["sample"][k] for k in _SAMPLE_KEYS},
        },
    }
    if include_style:
        preset["style"] = {k: settings["style"][k] for k in _STYLE_KEYS}
    if include_geom:
        preset["geom"] = {k: settings["geom"][k] for k in _GEOM_KEYS}
    return copy.deepcopy(preset)


def to_bytes(preset) -> bytes:
    """프리셋 dict 를 다운로드용 JSON 바이트로 직렬화."""
    return json.dumps(preset, ensure_ascii=False, indent=2).encode("utf-8")


def load(raw) -> tuple[dict, list[str]]:
    """업로드 바이트를 프리셋으로 파싱. **절대 raise 하지 않는다.**

    잘린 JSON · JPEG 바이트 · 잘못된 타입 · null — 무엇이 와도 쓸 수 있는 dict 를 돌려준다.
    """
    warnings = []
    data = None

    try:
        if hasattr(raw, "read"):  # UploadedFile / 파일 객체
            raw = raw.read()
        if isinstance(raw, dict):
            data = raw
        else:
            text = None
            if isinstance(raw, (bytes, bytearray, memoryview)):
                text = bytes(raw).decode("utf-8", errors="replace")
            elif isinstance(raw, str):
                text = raw
            else:
                warnings.append("프리셋 파일을 읽을 수 없어 기본값으로 채웠습니다.")
            if text is not None:
                try:
                    data = json.loads(text)
                except (ValueError, TypeError):
                    warnings.append("JSON 을 해석할 수 없습니다 (파일이 손상되었거나 프리셋 "
                                    "파일이 아닙니다). 기본값으로 채웠습니다.")
    except Exception as e:  # noqa: BLE001 — load 는 어떤 경우에도 raise 하지 않는다
        warnings.append(f"프리셋을 읽는 중 문제가 발생해 기본값으로 채웠습니다 ({type(e).__name__}).")
        data = None

    if data is not None and not isinstance(data, dict):
        warnings.append("프리셋 최상위가 JSON 객체가 아닙니다. 기본값으로 채웠습니다.")
        data = None
    if data is None:
        data = {}

    try:
        if data:
            schema = data.get("schema")
            if schema != SCHEMA_ID:
                warnings.append(f"`schema` 가 `{SCHEMA_ID}` 가 아닙니다 (받은 값: {schema!r}). "
                                "이 앱의 프리셋이 아닐 수 있어 아는 항목만 최대한 반영합니다.")

        ver, ver_ok = _c_int(data.get("version", SCHEMA_VERSION), SCHEMA_VERSION, lo=0)
        if not ver_ok:
            warnings.append(f"`version` 이 올바르지 않아 {SCHEMA_VERSION} 로 가정합니다 "
                            f"(받은 값: {data.get('version')!r}).")
        if ver > SCHEMA_VERSION:
            warnings.append(f"프리셋 버전 {ver} 이 이 앱이 아는 버전({SCHEMA_VERSION})보다 "
                            "높습니다. 아는 항목만 반영합니다 (더 새 버전의 앱에서 만든 "
                            "파일일 수 있습니다).")
        elif ver < SCHEMA_VERSION:
            data = copy.deepcopy(data)
            while ver < SCHEMA_VERSION:
                fn = _MIGRATIONS.get(ver)
                if fn is None:
                    warnings.append(f"버전 {ver} → {ver + 1} 변환 규칙이 없어 그대로 "
                                    "최대한 반영합니다.")
                    break
                try:
                    data = fn(data)
                except Exception as e:  # noqa: BLE001
                    warnings.append(f"버전 {ver} → {ver + 1} 변환에 실패했습니다 "
                                    f"({type(e).__name__}). 남은 항목만 반영합니다.")
                    break
                ver += 1
            if not isinstance(data, dict):
                data = {}

        v = _V()
        preset = _validate(data, v)
        warnings.extend(v.finish())
        return preset, warnings
    except Exception as e:  # noqa: BLE001 — 최후의 그물. 여기 오면 안 되지만 raise 는 절대 금지.
        warnings.append(f"프리셋을 해석하지 못해 기본값을 사용합니다 ({type(e).__name__}).")
        return _validate({}, _V()), warnings


# ---------------- 적용 ----------------

def _apply_settings(settings, preset):
    """검증된 프리셋을 settings dict 에 제자리 적용. bump_rev 는 호출자가 한다.

    **preset 은 절대 변형하지 않는다** (PLAN §3: 다음 파일에서 살아 있어야 함).
    """
    msgs = []
    fallback = constants.FALLBACK_CYCLE
    tbl = preset.get("traces_by_label", {})
    line_width = preset.get("style", {}).get("line_width", settings["style"]["line_width"])

    used = set()
    for i, tr in enumerate(settings["traces"].values()):
        label = tr["label"]
        entry = tbl.get(label)
        if entry is not None:
            # label 이 N>1 회 등장하면(Dark#1, Dark#2) 전 occurrence 가 같은 항목을 받는다.
            # 현행 by-label 색상 동작과 동일 — 놀랄 만한 자동 구분은 하지 않는다 (PLAN §3).
            used.add(label)
            tr["color"] = entry["color"]
            tr["dash"] = entry["dash"]
            tr["width"] = entry["width"]
        else:
            # 프리셋에 없는 트레이스 = 새 파장. **정상 경로이므로 경고하지 않는다.**
            # 절대 무스타일로 두지 않는다: 파장 기본색 -> 없으면 폴백 사이클.
            tr["color"] = constants.DEFAULT_TRACE_COLORS.get(label, fallback[i % len(fallback)])
            tr["dash"] = "solid"
            tr["width"] = line_width

    missing = [lb for lb in tbl if lb not in used]
    if missing:
        msgs.append(INFO_PREFIX + "이 파일에 없는 파장은 건너뛰었습니다: "
                    + ", ".join(sorted(missing))
                    + " (프리셋에는 그대로 남아 있어 다른 파일에 적용됩니다).")

    for ax in ("x", "y"):
        src = preset.get("axes", {}).get(ax)
        if isinstance(src, dict):
            for k in _AXIS_KEYS:  # title_raw 는 파일별 텍스트라 건드리지 않는다
                if k in src:
                    settings["axes"][ax][k] = src[k]

    lg = preset.get("insets", {}).get("legend")
    if isinstance(lg, dict):
        for k in _LEGEND_KEYS:
            if k in lg:
                settings["insets"]["legend"][k] = lg[k]

    sm = preset.get("insets", {}).get("sample")
    if isinstance(sm, dict):
        # 기하 + font_size 만. text_raw 는 샘플 이름이므로 절대 덮어쓰지 않는다.
        for k in _SAMPLE_KEYS:
            if k in sm:
                settings["insets"]["sample"][k] = sm[k]

    if isinstance(preset.get("style"), dict):
        for k in _STYLE_KEYS:
            if k in preset["style"]:
                settings["style"][k] = preset["style"][k]

    if isinstance(preset.get("geom"), dict):
        for k in _GEOM_KEYS:
            if k in preset["geom"]:
                settings["geom"][k] = preset["geom"][k]

    return msgs


def _prepare(preset):
    """어디서 온 dict 든(직접 만든 것 포함) 적용 전에 검증한다. **원본은 건드리지 않는다.**"""
    v = _V()
    clean = _validate(copy.deepcopy(preset) if isinstance(preset, dict) else {}, v)
    return clean, v.finish()


def apply_to(fid, preset) -> list[str]:
    """프리셋을 한 파일에 적용하고 경고/안내 목록 반환.

    **반드시 `state.bump_rev()` 를 호출한다** (PLAN §2.3 함정2): 위젯키가 이미 있으면
    Streamlit 이 `value=` 를 무시하므로, 모델만 바뀌고 화면은 옛 값을 계속 그린다
    = 프리셋 적용이 아무 일도 안 한 것처럼 보인다. 이 패키지에서 가장 중요한 한 줄.
    """
    settings = state.file_settings(fid)
    if settings is None:
        return [f"적용할 파일을 찾지 못했습니다 (fid={fid!r})."]

    clean, msgs = _prepare(preset)
    msgs += _apply_settings(settings, clean)
    state.bump_rev()
    return msgs


def apply_to_all(preset) -> list[str]:
    """프리셋을 열려 있는 전 파일에 적용 (SPEC E2 '다른 파일에 바로 적용')."""
    s = state.S()
    if not s["order"]:
        return ["열려 있는 파일이 없습니다."]

    clean, msgs = _prepare(preset)
    for fid in list(s["order"]):
        settings = state.file_settings(fid)
        if settings is None:
            continue
        for m in _apply_settings(settings, clean):
            if m not in msgs:  # 파일마다 같은 안내가 반복되지 않게
                msgs.append(m)
    state.bump_rev()
    return msgs


def apply_to_current_format(preset) -> list[str]:
    """프리셋을 `current_format` 에 반영 → 이후 **새로 추가되는 파일이 상속** (PLAN §2.4).

    `add_file` 이 traces 를 파싱 결과로 처음부터 다시 만들므로 traces_by_label 은 여기서
    실효가 없다. style/geom/axes/insets 만 새 파일로 전달된다.
    """
    s = state.S()
    clean, msgs = _prepare(preset)
    _apply_settings(s["current_format"], clean)
    return msgs
