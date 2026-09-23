"""표시용 후처리 — 분할 측정 이어붙이기(stitch) + 스무딩(smooth).

⚠️ **표시 전용이다.** 성능지표(R·D*)는 이 모듈을 거치지 않은 raw 로 계산한다
   (summary.py). 고정 바이어스 I-T 측정의 정의(I_ph = I_light(V) - I_dark(V))와
   방법을 일치시키기 위함이며, dark_offset 과 같은 원칙이다.

왜 필요한가
  - 암전류는 0→-1V / 0→+1V 로 나눠 재는 일이 잦은데, 두 스윕의 영점이 서로 달라
    0V 에서 단차가 생긴다. 그래프에서만 한쪽을 평행이동해 이어 붙인다.
  - 광전류가 분해능 바닥에 가까우면 톱니 노이즈가 남는다. 창 기반 평활로 다듬는다.

SPEC.md 의 "Dark 병합 안 함" 결정을 덮어쓰지 않도록 **기본값은 전부 꺼짐**이고,
사용자가 [서식]▸[보정] 에서 켤 때만 적용된다.
"""

from __future__ import annotations

import numpy as np

# UI 표기용. 키는 settings 에 저장되는 값.
SMOOTH_METHODS = {
    "none": "없음",
    "movavg": "이동 평균",
    "savgol": "Savitzky-Golay",
}
TARGETS = {"all": "전체", "light": "광 트레이스만"}

# 접합부를 어떻게 이을지.
#
# ⚠️ shift·blend 는 조각 하나를 통째로 옮기므로 **그 조각의 0 교차점(골짜기)도 같이
#    밀린다.** 실측: 14s_1 Dark 골짜기가 +0.65V → +0.99V 로 이동하고 깊이도 29배
#    얕아졌다. 암전류 골짜기를 0V 에 두려면 zero 를 쓸 것.
STITCH_MODES = {
    "zero": "영점 정렬 (0V를 0으로)",
    "shift": "평행이동 (전체)",
    "taper": "테이퍼 (접합부만)",
    "blend": "블렌드 (기울기까지)",
}

WINDOW_MIN, WINDOW_MAX = 3, 51
POLY_MIN, POLY_MAX = 1, 5
SPAN_MIN, SPAN_MAX = 0.005, 1.0


def cfg(settings) -> dict:
    """settings["postproc"] 를 결측/이상값 없이 읽는다."""
    p = settings.get("postproc") or {}
    smooth = p.get("smooth", "none")
    if smooth not in SMOOTH_METHODS:
        smooth = "none"
    targets = p.get("targets", "all")
    if targets not in TARGETS:
        targets = "all"
    try:
        window = int(p.get("window", 7))
    except (TypeError, ValueError):
        window = 7
    try:
        poly = int(p.get("poly", 2))
    except (TypeError, ValueError):
        poly = 2
    mode = p.get("stitch_mode", "zero")
    if mode not in STITCH_MODES:
        mode = "zero"
    try:
        span = float(p.get("stitch_span", 0.5))
    except (TypeError, ValueError):
        span = 0.5
    return {
        "stitch": bool(p.get("stitch", False)),
        "stitch_mode": mode,
        "stitch_span": min(max(span, SPAN_MIN), SPAN_MAX),
        "smooth": smooth,
        "window": min(max(window, WINDOW_MIN), WINDOW_MAX),
        "poly": min(max(poly, POLY_MIN), POLY_MAX),
        "targets": targets,
    }


def enabled(settings) -> bool:
    c = cfg(settings)
    return c["stitch"] or c["smooth"] != "none"


def describe(settings) -> str:
    """현재 후처리 설정 한 줄 요약 (UI 캡션 · 엑셀 Info 시트 공용)."""
    c = cfg(settings)
    parts = []
    if c["stitch"]:
        tag = STITCH_MODES[c["stitch_mode"]]
        if c["stitch_mode"] != "shift":
            tag += f"(±{c['stitch_span']:g}V)"
        parts.append(f"이어붙이기·{tag}")
    if c["smooth"] != "none":
        extra = f"·{c['poly']}차" if c["smooth"] == "savgol" else ""
        parts.append(f"{SMOOTH_METHODS[c['smooth']]}(창 {c['window']}{extra}, "
                     f"{TARGETS[c['targets']]})")
    return " · ".join(parts) if parts else "없음"


# ---------------- 스무딩 ----------------
def _savgol_coeffs(window: int, poly: int) -> np.ndarray:
    """Savitzky-Golay 평활 계수. 창 중앙에서의 다항 최소제곱 적합값 = pinv 의 첫 행."""
    half = window // 2
    x = np.arange(-half, half + 1, dtype=float)
    A = np.vander(x, poly + 1, increasing=True)
    return np.linalg.pinv(A)[0]


def _smooth(y: np.ndarray, method: str, window: int, poly: int) -> np.ndarray:
    """측정 순서(행 순서)를 따라 평활. 길이는 그대로 유지한다.

    가장자리는 **홀수 반사**(`reflect_type="odd"`, pad = 2·y_end − y)로 채운다.
    I-V 곡선은 끝으로 갈수록 가파르게 오르는데, 값을 그대로 거울반사하는 일반
    reflect 는 경계에서 곡선이 되돌아 내려가는 가짜 꺾임을 만든다. 홀수 반사는
    기울기를 이어주므로 끝점이 끌려 내려가지 않는다.
      실측(합성 노이즈, 참값 대비 RMS): 원본 2.3e-9 / reflect 1.4e-8(악화)
      / reflect-odd 1.3e-9(개선). 끝 10점만 보면 6.4e-8 → 2.0e-9.
    """
    n = len(y)
    if method == "none" or n < 3:
        return y
    w = int(window) | 1                 # 창은 항상 홀수
    if w > n:
        w = n if n % 2 else n - 1
    if w < 3:
        return y
    half = w // 2
    if method == "movavg":
        c = np.full(w, 1.0 / w)
    else:
        c = _savgol_coeffs(w, min(max(int(poly), 1), w - 1))
    # 유한값만 평활 대상. NaN 이 섞이면 창 전체가 NaN 으로 번진다.
    finite = np.isfinite(y)
    if not finite.all():
        y = np.where(finite, y, np.interp(np.arange(n), np.flatnonzero(finite),
                                          y[finite]) if finite.any() else 0.0)
    pad = np.pad(y, half, mode="reflect", reflect_type="odd")
    # c 는 대칭이지만 상관(correlation) 이 맞으므로 뒤집어 넣는다.
    return np.convolve(pad, c[::-1], mode="valid")


# ---------------- 이어붙이기 ----------------
def _value_near(v: np.ndarray, i: np.ndarray, x: float) -> float:
    """x 에서의 값. 범위 밖이면 가장 가까운 끝점 값 (외삽하지 않는다)."""
    o = np.argsort(v)
    vs, iv = v[o], i[o]
    if x <= vs[0]:
        return float(iv[0])
    if x >= vs[-1]:
        return float(iv[-1])
    return float(np.interp(x, vs, iv))


def _junction(v1: np.ndarray, v2: np.ndarray) -> float:
    """두 조각이 만나는 전압. 겹치면 겹침 구간의 중점, 떨어져 있으면 끝점 사이 중점."""
    lo, hi = max(v1.min(), v2.min()), min(v1.max(), v2.max())
    if lo <= hi:
        return 0.5 * (lo + hi)
    if v1.max() < v2.min():
        return 0.5 * (v1.max() + v2.min())
    return 0.5 * (v2.max() + v1.min())


def _taper_w(dist: np.ndarray, span: float) -> np.ndarray:
    """접합부에서 1, span 만큼 떨어지면 0 이 되는 부드러운 가중치 (양끝 기울기 0)."""
    d = np.clip(np.abs(dist) / max(span, 1e-12), 0.0, 1.0)
    return 0.5 * (1.0 + np.cos(np.pi * d))


def _align(out, ref_k: int, k: int, mode: str, span: float) -> float:
    """조각 k 를 이미 자리잡은 ref_k 에 맞춘다. 접합 전압을 반환.

    shift  조각 전체를 delta 만큼 평행이동 — 모양이 완전히 보존된다.
    taper  delta 를 접합부에서만 100%, span 밖에서 0 으로 감쇠 — 먼 쪽 끝값은 그대로.
    blend  일단 shift 와 같이 전체 이동 (기울기 잇기는 _blend_junction 이 뒤에 한다).
    """
    vr, ir = out[ref_k]
    v, i = out[k]
    x = _junction(vr, v)
    delta = _value_near(vr, ir, x) - _value_near(v, i, x)
    out[k][1] = i + (delta * _taper_w(v - x, span) if mode == "taper" else delta)
    return x


def _blend_junction(out, k1: int, k2: int, x: float, span: float) -> None:
    """접합부 ±span 을 양쪽 공통 직선 쪽으로 섞어 **기울기까지** 잇는다.

    ⚠️ 이 구간 값은 측정값이 아니라 합성값이다. 평행이동과 달리 원본 모양을 바꾼다.
    두 조각의 접합부 구간을 함께 직선으로 적합한 뒤, 접합부에서 1·span 에서 0 인
    가중치로 원본과 섞는다 — 접합부에서는 양쪽 모두 같은 직선이 되어 값·기울기가
    이어지고, span 바깥은 원본 그대로다.
    """
    v1, i1 = out[k1]
    v2, i2 = out[k2]
    m1 = np.abs(v1 - x) <= span
    m2 = np.abs(v2 - x) <= span
    if int(m1.sum()) < 2 or int(m2.sum()) < 2:
        return                       # 접합부 표본이 너무 적으면 건드리지 않는다
    vv = np.concatenate([v1[m1], v2[m2]])
    ii = np.concatenate([i1[m1], i2[m2]])
    good = np.isfinite(vv) & np.isfinite(ii)
    if int(good.sum()) < 2:
        return
    coef = np.polyfit(vv[good], ii[good], 1)
    for k, mask in ((k1, m1), (k2, m2)):
        v, i = out[k]
        i = i.copy()
        w = _taper_w(v[mask] - x, span)
        i[mask] = w * np.polyval(coef, v[mask]) + (1.0 - w) * i[mask]
        out[k][1] = i


def _zero_anchor(out, ks: list[int]) -> None:
    """각 조각에서 **자기 0V 값**을 빼 모두 0V 에서 0 이 되게 한다.

    0 바이어스에서 암전류는 0 이어야 하고 측정된 값은 조각마다 다른 계측 오프셋이다.
    조각별로 자기 오프셋을 빼면 단차가 사라지면서 **골짜기가 양쪽 모두 정확히 0V 에
    선다** — 한쪽을 통째로 옮기는 shift 와 달리 0 교차점이 밀리지 않는다.

    ⚠️ 암전류 전용이다. 광 트레이스에 쓰면 0V 광전류(광기전 성분)까지 지워진다.
    조각들이 0V 를 품지 않으면 전체 구간 중점을 기준으로 삼는다.
    """
    lo = min(float(out[k][0].min()) for k in ks)
    hi = max(float(out[k][0].max()) for k in ks)
    x = 0.0 if lo <= 0.0 <= hi else 0.5 * (lo + hi)
    for k in ks:
        v, i = out[k]
        out[k][1] = i - _value_near(v, i, x)


def _stitch_group(out, ks: list[int], mode: str, span: float) -> None:
    """같은 라벨의 조각들을 전압 순으로 사슬처럼 이어 붙인다.

    기준(움직이지 않는 조각)은 **측정 순서상 첫 조각**이다. 거기서 좌우로 뻗어나가며
    이미 자리잡은 이웃에 맞춘다 — 조각이 3개 이상이어도 누적 단차가 생기지 않는다.
    """
    center = {k: 0.5 * (out[k][0].min() + out[k][0].max()) for k in ks}
    order = sorted(ks, key=lambda k: center[k])
    a = order.index(min(ks))

    pairs = [(order[p - 1], order[p]) for p in range(a + 1, len(order))]
    pairs += [(order[p + 1], order[p]) for p in range(a - 1, -1, -1)]

    juncs = [(ref, k, _align(out, ref, k, mode, span)) for ref, k in pairs]
    if mode == "blend":
        for ref, k, x in juncs:
            _blend_junction(out, ref, k, x, span)


# ---------------- 진입점 ----------------
def taper_slope_ratio(parsed, span: float) -> float | None:
    """테이퍼가 접합부에 **더하는** 기울기가 데이터 자체 기울기의 몇 배인지.

    이 값이 1 근처면 테이퍼 구간이 급하게 꺾여 어색해 보인다 (실측: span 0.05V 에서
    124~132%). 0.2 이하로 내려가도록 span 을 넓히면 자연스러워진다. UI 가 이 값을
    보여줘 사용자가 span 을 감으로 찍지 않게 한다.
    """
    by: dict[str, list[int]] = {}
    for k, t in enumerate(parsed["traces"]):
        by.setdefault(t["label"], []).append(k)
    worst = None
    for ks in by.values():
        if len(ks) < 2:
            continue
        arrs = [(parsed["traces"][k]["df"]["AnodeV"].to_numpy(dtype=float),
                 parsed["traces"][k]["df"]["AnodeI"].to_numpy(dtype=float)) for k in ks]
        order = sorted(range(len(ks)), key=lambda j: 0.5 * (arrs[j][0].min() + arrs[j][0].max()))
        for a, b in zip(order, order[1:]):
            (v1, i1), (v2, i2) = arrs[a], arrs[b]
            x = _junction(v1, v2)
            delta = abs(_value_near(v1, i1, x) - _value_near(v2, i2, x))
            o = np.argsort(v2)
            vs, iv = v2[o], i2[o]
            n = min(8, len(vs))
            if n < 2:
                continue
            own = abs(float(np.polyfit(vs[:n], iv[:n], 1)[0]))
            if own > 0:
                r = (delta / max(span, 1e-12)) / own
                worst = r if worst is None else max(worst, r)
    return worst


def process(parsed, settings) -> list[tuple[np.ndarray, np.ndarray]]:
    """parsed["traces"] 와 **같은 순서·길이**로 후처리된 (V, I) 배열을 돌려준다.

    부호는 유지한다 (abs·오프셋 차감은 표시 단계인 figure._series_xy 가 한다).
    후처리가 모두 꺼져 있으면 원본 값 그대로다.
    """
    c = cfg(settings)
    traces = parsed["traces"]
    out = []
    for t in traces:
        df = t["df"]
        out.append([df["AnodeV"].to_numpy(dtype=float),
                    df["AnodeI"].to_numpy(dtype=float)])

    # 스무딩을 먼저 한다 — 이어붙이기의 접합부 기준값을 노이즈가 아닌 평활값에서
    # 잡기 위함. (평행이동은 선형이라 순서를 바꿔도 결과 자체는 같다.)
    if c["smooth"] != "none":
        for k, t in enumerate(traces):
            if c["targets"] == "light" and t["label"] == "Dark":
                continue
            out[k][1] = _smooth(out[k][1], c["smooth"], c["window"], c["poly"])

    if c["stitch"]:
        by_label: dict[str, list[int]] = {}
        for k, t in enumerate(traces):
            by_label.setdefault(t["label"], []).append(k)
        for label, ks in by_label.items():
            if len(ks) < 2:
                continue
            if c["stitch_mode"] == "zero":
                # 영점 정렬은 암전류에만 물리적 근거가 있다. 광 트레이스가 쪼개져
                # 있으면 0V 광전류를 지우지 않도록 평행이동으로 대체한다.
                if label == "Dark":
                    _zero_anchor(out, ks)
                else:
                    _stitch_group(out, ks, "shift", c["stitch_span"])
            else:
                _stitch_group(out, ks, c["stitch_mode"], c["stitch_span"])

    return [(v, i) for v, i in out]
