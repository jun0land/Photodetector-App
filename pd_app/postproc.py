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

WINDOW_MIN, WINDOW_MAX = 3, 51
POLY_MIN, POLY_MAX = 1, 5


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
    return {
        "stitch": bool(p.get("stitch", False)),
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
        parts.append("이어붙이기")
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


def _align(out, ref_k: int, k: int) -> None:
    """조각 k 를 이미 자리잡은 ref_k 에 맞춰 평행이동. 기울기는 건드리지 않는다."""
    vr, ir = out[ref_k]
    v, i = out[k]
    x = _junction(vr, v)
    out[k][1] = i + (_value_near(vr, ir, x) - _value_near(v, i, x))


def _stitch_group(out, ks: list[int]) -> None:
    """같은 라벨의 조각들을 전압 순으로 사슬처럼 이어 붙인다.

    기준(움직이지 않는 조각)은 **측정 순서상 첫 조각**이다. 거기서 좌우로 뻗어나가며
    이미 자리잡은 이웃에 맞춘다 — 조각이 3개 이상이어도 누적 단차가 생기지 않는다.
    """
    center = {k: 0.5 * (out[k][0].min() + out[k][0].max()) for k in ks}
    order = sorted(ks, key=lambda k: center[k])
    a = order.index(min(ks))
    for p in range(a + 1, len(order)):
        _align(out, order[p - 1], order[p])
    for p in range(a - 1, -1, -1):
        _align(out, order[p + 1], order[p])


# ---------------- 진입점 ----------------
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
        for ks in by_label.values():
            if len(ks) >= 2:
                _stitch_group(out, ks)

    return [(v, i) for v, i in out]
