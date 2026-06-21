import math
import re
from dataclasses import dataclass, field
from typing import Optional


class SpecParseError(Exception):
    def __init__(self, field_name: str, raw_value: str, hint: str = ""):
        self.field_name = field_name
        self.raw_value = raw_value
        self.hint = hint
        msg = f"字段 '{field_name}' 无法解析规格 '{raw_value}'"
        if hint:
            msg += f"（{hint}）"
        super().__init__(msg)


@dataclass
class CheckResult:
    item: str
    passed: bool
    ratio: float
    demand: float
    capacity: float
    unit: str
    suggestion: str = ""


@dataclass
class MaterialParams:
    steel_tube_od_mm: float = 48.0
    steel_tube_wall_mm: float = 3.5
    steel_E_N_mm2: float = 206000.0
    steel_f_N_mm2: float = 205.0
    timber_E_N_mm2: float = 9000.0
    timber_f_N_mm2: float = 13.0
    plywood_E_N_mm2: float = 6000.0
    plywood_f_N_mm2: float = 15.0
    right_angle_clamp_kN: float = 8.0
    rotating_clamp_kN: float = 8.0
    concrete_density_kN_m3: float = 25.0


_TIMBER_SPLIT_RE = re.compile(r"[x×*X\u00d7]")
_STEEL_PREFIX_RE = re.compile(r"^(?P<n>[1-9]\d*)?\s*(?P<phi>[ΦφϕФф\u03a6\u03c6\u03d5\u0424\u0444]|phi|PHI|Phi|直径|D|d)\s*")
_STEEL_SPLIT_RE = re.compile(r"[x×*X\u00d7]")


def _parse_timber_section(spec: str):
    if spec is None:
        raise SpecParseError("木方规格", "", "填写如 50x80、50×80、50X80 等格式")
    s = str(spec).strip()
    if not s:
        raise SpecParseError("木方规格", spec, "填写如 50x80、50×80、50X80 等格式")
    parts = [p.strip() for p in _TIMBER_SPLIT_RE.split(s) if p.strip()]
    if len(parts) != 2:
        raise SpecParseError("木方规格", spec, "期望格式 50x80 或 50×80（宽×高）")
    try:
        w = float(parts[0])
        h = float(parts[1])
    except ValueError:
        raise SpecParseError("木方规格", spec, "尺寸必须是数值，如 50x80")
    if w <= 0 or h <= 0:
        raise SpecParseError("木方规格", spec, "尺寸必须大于 0")
    return w, h


def _parse_steel_tube_section(spec: str):
    if spec is None:
        raise SpecParseError("主楞规格", "", "填写如 2Φ48x3.5、Φ48X3.5、2phi48×3.5 等格式")
    s = str(spec).strip()
    if not s:
        raise SpecParseError("主楞规格", spec, "填写如 2Φ48x3.5、Φ48X3.5、2phi48×3.5 等格式")
    m = _STEEL_PREFIX_RE.match(s)
    if not m:
        raise SpecParseError("主楞规格", spec, "期望格式如 2Φ48x3.5（根数+Φ+外径×壁厚）")
    n_str = m.group("n")
    n = int(n_str) if n_str else 1
    remainder = s[m.end():].strip()
    parts = [p.strip() for p in _STEEL_SPLIT_RE.split(remainder) if p.strip()]
    if len(parts) != 2:
        raise SpecParseError("主楞规格", spec, "期望格式如 2Φ48x3.5（根数+Φ+外径×壁厚）")
    try:
        od = float(parts[0])
        wall = float(parts[1])
    except ValueError:
        raise SpecParseError("主楞规格", spec, "外径和壁厚必须是数值，如 48x3.5")
    if od <= 0 or wall <= 0 or wall >= od / 2:
        raise SpecParseError("主楞规格", spec, "外径和壁厚必须大于 0，且壁厚小于半外径")
    return n, od, wall


def _tube_section_props(od_mm, wall_mm):
    r_out = od_mm / 2.0
    r_in = r_out - wall_mm
    area = math.pi * (r_out ** 2 - r_in ** 2)
    inertia = math.pi / 4.0 * (r_out ** 4 - r_in ** 4)
    section_modulus = inertia / r_out
    radius_gyration = math.sqrt(inertia / area) if area > 0 else 0
    return area, inertia, section_modulus, radius_gyration


def _get_equivalent_area_load(comp: dict, mat: MaterialParams):
    if comp["类型"] == "梁":
        b_m = comp["梁截面宽_mm"] / 1000.0
        h_m = comp["梁截面高_mm"] / 1000.0
        q_concrete = mat.concrete_density_kN_m3 * b_m * h_m
        q_formwork = 0.5
        q_live = comp.get("施工活荷载_kN_m2", 2.5) * b_m
        q_pour = comp.get("倾倒混凝土荷载_kN_m2", 2.0) * b_m
        q_dead = q_concrete + q_formwork
        q_design_linear = 1.2 * q_dead + 1.4 * q_live + 1.4 * q_pour
        q_std_linear = q_dead + q_live + q_pour
        q_design = q_design_linear / b_m if b_m > 0 else 0
        q_std = q_std_linear / b_m if b_m > 0 else 0
    else:
        h = comp["混凝土厚度_mm"] / 1000.0
        q_concrete = mat.concrete_density_kN_m3 * h
        q_live = comp.get("施工活荷载_kN_m2", 2.5)
        q_pour = comp.get("倾倒混凝土荷载_kN_m2", 2.0)
        q_dead = q_concrete + 0.3 + 0.1
        q_design = 1.2 * q_dead + 1.4 * q_live + 1.4 * q_pour
        q_std = q_dead + q_live + q_pour
    return q_design, q_std


def _get_tributary_width_for_beam(comp: dict):
    return comp["梁截面宽_mm"] / 1000.0


def check_timber_bending(comp: dict, mat: MaterialParams) -> CheckResult:
    w_mm, h_mm = _parse_timber_section(comp["木方规格"])
    spacing_mm = comp["木方间距_mm"]
    b_section = h_mm
    h_section = w_mm
    I = b_section * h_section ** 3 / 12.0
    W = I / (h_section / 2.0)

    q_design, q_std = _get_equivalent_area_load(comp, mat)
    q_line_kN_m = q_design * (spacing_mm / 1000.0)
    q_line_N_mm = q_line_kN_m

    l_mm = comp["主楞间距_mm"]
    M_N_mm = q_line_N_mm * l_mm ** 2 / 8.0
    sigma = M_N_mm / W

    passed = sigma <= mat.timber_f_N_mm2
    ratio = sigma / mat.timber_f_N_mm2
    suggestion = ""
    if not passed:
        suggestion = "减小木方间距或增大木方截面规格（如改用50x100）"
    return CheckResult(
        item="木方抗弯强度",
        passed=passed,
        ratio=ratio,
        demand=round(sigma, 2),
        capacity=mat.timber_f_N_mm2,
        unit="N/mm²",
        suggestion=suggestion,
    )


def check_timber_deflection(comp: dict, mat: MaterialParams) -> CheckResult:
    w_mm, h_mm = _parse_timber_section(comp["木方规格"])
    spacing_mm = comp["木方间距_mm"]
    b_section = h_mm
    h_section = w_mm
    I = b_section * h_section ** 3 / 12.0

    q_design, q_std = _get_equivalent_area_load(comp, mat)
    q_line_kN_m = q_std * (spacing_mm / 1000.0)
    q_line_N_mm = q_line_kN_m

    l_mm = comp["主楞间距_mm"]
    deflection = 5.0 * q_line_N_mm * l_mm ** 4 / (384.0 * mat.timber_E_N_mm2 * I)
    limit = l_mm / 250.0

    passed = deflection <= limit
    ratio = deflection / limit if limit > 0 else 0
    suggestion = ""
    if not passed:
        suggestion = "减小木方间距或减小主楞间距（即缩短木方跨度）"
    return CheckResult(
        item="木方挠度",
        passed=passed,
        ratio=ratio,
        demand=round(deflection, 2),
        capacity=round(limit, 2),
        unit="mm",
        suggestion=suggestion,
    )


def check_main_steel_bending(comp: dict, mat: MaterialParams) -> CheckResult:
    n, od, wall = _parse_steel_tube_section(comp["主楞规格"])
    area1, I1, W1, _ = _tube_section_props(od, wall)
    W_total = n * W1

    q_design, q_std = _get_equivalent_area_load(comp, mat)

    if comp["类型"] == "梁":
        q_line_kN_m = q_design * _get_tributary_width_for_beam(comp)
    else:
        q_line_kN_m = q_design * (comp["立杆纵距_mm"] / 1000.0)

    q_line_N_mm = q_line_kN_m
    l_mm = comp["立杆横距_mm"] if comp["类型"] == "板" else comp["立杆纵距_mm"]

    M_N_mm = q_line_N_mm * l_mm ** 2 / 8.0
    sigma = M_N_mm / W_total

    passed = sigma <= mat.steel_f_N_mm2
    ratio = sigma / mat.steel_f_N_mm2
    suggestion = ""
    if not passed:
        suggestion = "调整主楞规格（如改用2Φ48x3.5双钢管）或减小立杆间距"
    return CheckResult(
        item="主楞强度",
        passed=passed,
        ratio=ratio,
        demand=round(sigma, 2),
        capacity=mat.steel_f_N_mm2,
        unit="N/mm²",
        suggestion=suggestion,
    )


def check_main_steel_deflection(comp: dict, mat: MaterialParams) -> CheckResult:
    n, od, wall = _parse_steel_tube_section(comp["主楞规格"])
    area1, I1, W1, _ = _tube_section_props(od, wall)
    I_total = n * I1

    q_design, q_std = _get_equivalent_area_load(comp, mat)

    if comp["类型"] == "梁":
        q_line_kN_m = q_std * _get_tributary_width_for_beam(comp)
    else:
        q_line_kN_m = q_std * (comp["立杆纵距_mm"] / 1000.0)

    q_line_N_mm = q_line_kN_m
    l_mm = comp["立杆横距_mm"] if comp["类型"] == "板" else comp["立杆纵距_mm"]

    deflection = 5.0 * q_line_N_mm * l_mm ** 4 / (384.0 * mat.steel_E_N_mm2 * I_total)
    limit = l_mm / 400.0

    passed = deflection <= limit
    ratio = deflection / limit if limit > 0 else 0
    suggestion = ""
    if not passed:
        suggestion = "减小立杆间距或调整主楞规格"
    return CheckResult(
        item="主楞挠度",
        passed=passed,
        ratio=ratio,
        demand=round(deflection, 2),
        capacity=round(limit, 2),
        unit="mm",
        suggestion=suggestion,
    )


def check_vertical_tube(comp: dict, mat: MaterialParams) -> CheckResult:
    od = mat.steel_tube_od_mm
    wall = mat.steel_tube_wall_mm
    area, I, W, i_r = _tube_section_props(od, wall)

    q_design, q_std = _get_equivalent_area_load(comp, mat)

    if comp["类型"] == "梁":
        tributary_area_m2 = (comp["立杆纵距_mm"] / 1000.0) * _get_tributary_width_for_beam(comp)
    else:
        tributary_area_m2 = (comp["立杆纵距_mm"] / 1000.0) * (comp["立杆横距_mm"] / 1000.0)

    N_design = q_design * tributary_area_m2 * 1e3

    step_mm = comp["立杆步距_mm"]
    l0_m = (step_mm / 1000.0) * 1.155 * 1.5
    lambda_val = l0_m * 1000.0 / i_r if i_r > 0 else 200

    phi = _stability_coefficient(lambda_val)
    N_capacity = phi * mat.steel_f_N_mm2 * area

    passed = N_design <= N_capacity
    ratio = N_design / N_capacity if N_capacity > 0 else 999
    suggestion = ""
    if not passed:
        suggestion = "减小立杆间距或减小步距；必要时增加立杆"
    return CheckResult(
        item="立杆承载力",
        passed=passed,
        ratio=ratio,
        demand=round(N_design, 2),
        capacity=round(N_capacity, 2),
        unit="N",
        suggestion=suggestion,
    )


def _stability_coefficient(lam: float) -> float:
    if lam <= 0:
        return 1.0
    if lam > 152:
        phi = 7600.0 / lam ** 2
    else:
        phi_val = lam ** 2 / 2.0
        phi = 1.0 - (1.04 - 7600.0 / lam ** 2) * phi_val / (1.0 + phi_val)
        phi = max(phi, 7600.0 / lam ** 2)
    return min(max(phi, 0.0), 1.0)


def check_clamp_slip(comp: dict, mat: MaterialParams) -> CheckResult:
    q_design, q_std = _get_equivalent_area_load(comp, mat)

    if comp["类型"] == "梁":
        q_line_kN_m = q_design * _get_tributary_width_for_beam(comp)
    else:
        q_line_kN_m = q_design * (comp["立杆纵距_mm"] / 1000.0)

    l_m = comp["立杆横距_mm"] / 1000.0 if comp["类型"] == "板" else comp["立杆纵距_mm"] / 1000.0
    R_kN = q_line_kN_m * l_m / 2.0

    clamp_type = comp.get("扣件类型", "直角扣件")
    if clamp_type == "旋转扣件":
        capacity = mat.rotating_clamp_kN
    else:
        capacity = mat.right_angle_clamp_kN

    passed = R_kN <= capacity
    ratio = R_kN / capacity if capacity > 0 else 999
    suggestion = ""
    if not passed:
        suggestion = "减小立杆间距或增加扣件数量（双扣件）"
    return CheckResult(
        item="扣件抗滑",
        passed=passed,
        ratio=ratio,
        demand=round(R_kN, 2),
        capacity=capacity,
        unit="kN",
        suggestion=suggestion,
    )


def run_all_checks(comp: dict, mat: MaterialParams) -> list[CheckResult]:
    results = []
    results.append(check_timber_bending(comp, mat))
    results.append(check_timber_deflection(comp, mat))
    results.append(check_main_steel_bending(comp, mat))
    results.append(check_main_steel_deflection(comp, mat))
    results.append(check_vertical_tube(comp, mat))
    results.append(check_clamp_slip(comp, mat))
    return results
