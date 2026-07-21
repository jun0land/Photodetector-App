"""앱 전역 상수. 데이터 전용 — 동작은 hex_to_rgba 하나뿐.

WP0 이후 READ-ONLY. 여기를 고치면 모든 WP 가 영향을 받는다.
"""

ACCENT = "#ed542b"

SYMBOL_MAP = {
    "d": "Dark",
    "8": "940 nm",
    "7": "850 nm",
    "6": "740 nm",
    "5": "625 nm",
    "4": "530 nm",
    "3": "470 nm",
    "2": "405 nm",
    "1": "365 nm",
}

# Origin 기본 팔레트 (사용자 제공 OriginLab 정확값, 24색 순서 그대로)
ORIGIN_COLORS = {
    "Black": "#000000",
    "Red": "#FF0000",
    "Green": "#00FF00",
    "Blue": "#0000FF",
    "Cyan": "#00FFFF",
    "Magenta": "#FF00FF",
    "Yellow": "#FFFF00",
    "Dark Yellow": "#808000",
    "Navy": "#000080",
    "Purple": "#800080",
    "Wine": "#800000",
    "Olive": "#008000",
    "Dark Cyan": "#008080",
    "Royal": "#0000A0",
    "Orange": "#FF8000",
    "Violet": "#8000FF",
    "Pink": "#FF0080",
    "White": "#FFFFFF",
    "LT Gray": "#C0C0C0",
    "Gray": "#808080",
    "LT Yellow": "#FFFF80",
    "LT Cyan": "#80FFFF",
    "LT Magenta": "#FF80FF",
    "Dark Gray": "#404040",
}

# 파장별 기본 색 (실제 광원 색에 가깝게)
DEFAULT_TRACE_COLORS = {
    "Dark": "#000000",
    "365 nm": "#800080",
    "405 nm": "#800080",
    "470 nm": "#0000FF",
    "530 nm": "#008000",   # Origin Olive (녹색 파장 — 사용자 확인)
    "625 nm": "#FF0000",
    "740 nm": "#FF0080",
    "850 nm": "#8000FF",   # Purple (ORIGIN_COLORS 에 있어 드롭다운에 Custom 아닌 Purple 로 표시)
    "940 nm": "#0000A0",
}

FALLBACK_CYCLE = ["#000000", "#FF0000", "#0000FF", "#00A000", "#FF00FF",
                  "#FF8000", "#008080", "#8000FF", "#808000", "#4169E1"]

# SPEC C1: Pretendard / Myriad Pro 는 앱 자체 디자인 폰트라 목록 맨 앞
FONT_FAMILIES = ["Myriad Pro", "Pretendard", "Arial", "Times New Roman",
                 "Calibri", "Helvetica", "Courier New"]
DASH_OPTIONS = {"Solid": "solid", "Dash": "dash", "Dot": "dot", "DashDot": "dashdot"}

# SPEC C2/C4: 폰트 크기 범위는 전 항목 6~50 통일, 선 두께는 0.5 간격
FONT_SIZE_MIN = 6
FONT_SIZE_MAX = 50
LINE_WIDTH_STEP = 0.5

# 인셋 레전드 기하 (가로는 paper 비율, 세로는 px -> paper 로 환산)
INSET_PAD_X = 0.014      # 박스 좌우 안쪽 여백 (paper x)
INSET_SWATCH_W = 0.05    # 선 스와치 길이 (paper x)
INSET_GAP = 0.014        # 스와치 <-> 텍스트 간격 (paper x)
INSET_PAD_PX = 7         # 박스 위/아래 안쪽 여백 (px)

# 파싱: Settings 블록 구분자 (parsing.py 가 이 상수를 import 한다)
SEP_TOKEN = "=================================="


def hex_to_rgba(hex_color, alpha):
    """#RRGGBB + 투명도 -> rgba() 문자열 (텍스트는 선명하게 두고 배경만 투명하게)."""
    h = str(hex_color).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        r, g, b = 255, 255, 255
    return f"rgba({r},{g},{b},{alpha:g})"


# ---------------- 기본 FileSettings ----------------
# 새 파일이 상속하는 표준형. 소비자는 반드시 copy.deepcopy 후 사용할 것
# (평범한 dict 이므로 그대로 쓰면 전역 상태가 오염된다).
DEFAULTS = {
    # {TKey: {label, visible, color, dash, width, legend_raw, inset_raw, include_in_inset}}
    # 파일마다 TKey 가 다르므로 add_file 이 파싱 결과로 처음부터 다시 채운다.
    "traces": {},
    "geom": {"page_w_in": 10.0, "page_h_in": 8.0, "graph_left_pct": 17.9,
             "graph_top_pct": 11.58, "graph_width_pct": 68.2, "graph_height_pct": 71.77},
    "axes": {
        # SPEC A1: Y 기본은 Log, X 는 linear. Linear Y 는 사용자 선택 사항.
        "x": {"type": "linear", "auto": True, "min": None, "max": None,
              "dtick": 0.5, "minor_dtick": None,
              "title_raw": "Voltage (V)", "title_standoff": None},
        # SPEC(사용자 확정): Y 기본범위는 1E-11~1E-5 고정. 0 교차점 때문에 auto 는
        # 노이즈 바닥(~1E-16)까지 따라가 9 decades 가 되므로 예시 이미지와 어긋난다.
        "y": {"type": "log", "auto": False, "min": 1e-11, "max": 1e-5,
              "dtick": 1, "minor_dtick": "D1",   # 로그 Major 1 decade · Minor 8개(D1) 고정
              "title_raw": "Current (A)", "title_standoff": None},
    },
    "style": {"font_family": "Myriad Pro", "title_font_size": 30, "tick_font_size": 30,
              "line_width": 2.0, "show_markers": False, "show_grid": False},
    "insets": {
        # PLAN §4.3: 인셋 ref 가 paper -> "x domain"/"y domain" 으로 바뀌어
        # 0.97/0.97 은 이제 페이지가 아니라 플롯 영역의 우상단을 뜻한다 (Origin 예시와 동일).
        "legend": {"x": 0.97, "y": 0.97, "xanchor": "right", "yanchor": "top",
                   "width": 0.30,
                   "border": False, "border_color": "#000000", "bg_color": "#FFFFFF",
                   "bg_opacity": 1.0,
                   # font: None = style.font_family 상속
                   "font": None, "font_size": 30},
        "sample": {"x": 0.04, "y": 0.06, "xanchor": "left", "yanchor": "bottom",
                   "text_raw": "", "font_size": 30},
    },
    "use_abs": True,
    # 성능 지표(Responsivity/Detectivity) 입력. **측정 조건이라 per-file** 이고
    # 프리셋에는 절대 들어가지 않는다 (presets.extract/apply 가 이 키를 다루지 않음).
    # irradiance 는 add_file 이 파일의 파장 라벨로 채운다 (Dark 제외, 빈 값 = None).
    "metrics": {"v_op": -1.0, "area": 1.0, "area_unit": "cm2",
                "irr_unit": "mW/cm2", "irradiance": {}},
}
