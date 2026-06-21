import re
from typing import Any

REQUIRED_PLATE_KEYS = [
    ("编号", str),
    ("类型", str),
    ("混凝土厚度_mm", (int, float)),
    ("支撑高度_m", (int, float)),
    ("模板类型", str),
    ("模板厚度_mm", (int, float)),
    ("木方规格", str),
    ("木方间距_mm", (int, float)),
    ("主楞规格", str),
    ("主楞间距_mm", (int, float)),
    ("立杆纵距_mm", (int, float)),
    ("立杆横距_mm", (int, float)),
    ("立杆步距_mm", (int, float)),
    ("扣件类型", str),
]

REQUIRED_BEAM_KEYS = [
    ("编号", str),
    ("类型", str),
    ("梁截面宽_mm", (int, float)),
    ("梁截面高_mm", (int, float)),
    ("支撑高度_m", (int, float)),
    ("模板类型", str),
    ("模板厚度_mm", (int, float)),
    ("木方规格", str),
    ("木方间距_mm", (int, float)),
    ("主楞规格", str),
    ("主楞间距_mm", (int, float)),
    ("立杆纵距_mm", (int, float)),
    ("立杆横距_mm", (int, float)),
    ("立杆步距_mm", (int, float)),
    ("扣件类型", str),
]

OPTIONAL_KEYS = [
    ("施工活荷载_kN_m2", (int, float), 2.5),
    ("倾倒混凝土荷载_kN_m2", (int, float), 2.0),
]

RANGE_LIMITS = {
    "混凝土厚度_mm": (50, 2000, "混凝土厚度异常，常见范围 50~2000mm"),
    "支撑高度_m": (0.5, 30, "支撑高度异常，常见范围 0.5~30m"),
    "模板厚度_mm": (10, 25, "模板厚度异常，常见范围 10~25mm"),
    "木方间距_mm": (100, 600, "木方间距异常，常见范围 100~600mm"),
    "主楞间距_mm": (300, 1500, "主楞间距异常，常见范围 300~1500mm"),
    "立杆纵距_mm": (300, 1500, "立杆纵距异常，常见范围 300~1500mm"),
    "立杆横距_mm": (300, 1500, "立杆横距异常，常见范围 300~1500mm"),
    "立杆步距_mm": (600, 2500, "立杆步距异常，常见范围 600~2500mm"),
    "施工活荷载_kN_m2": (1.0, 10.0, "施工活荷载异常，常见范围 1.0~10.0 kN/m²"),
    "倾倒混凝土荷载_kN_m2": (1.0, 10.0, "倾倒混凝土荷载异常，常见范围 1.0~10.0 kN/m²"),
    "梁截面宽_mm": (100, 1000, "梁截面宽度异常，常见范围 100~1000mm"),
    "梁截面高_mm": (200, 2000, "梁截面高度异常，常见范围 200~2000mm"),
}

TIMBER_PATTERN = re.compile(r"^\d+[x×]\d+$", re.IGNORECASE)
STEEL_TUBE_PATTERN = re.compile(r"^[12]?\s*[Φφ]\d+\s*[x×]\s*\d+(\.\d+)?$", re.IGNORECASE)

VALID_TYPES = {"板", "梁"}
VALID_CLAMP_TYPES = {"直角扣件", "旋转扣件"}
VALID_FORMWORK_TYPES = {"胶合板", "竹胶板", "钢模板", "木模板"}


class ValidationError:
    def __init__(self, level: str, component_id: str, field: str, message: str):
        self.level = level
        self.component_id = component_id
        self.field = field
        self.message = message

    def __str__(self):
        symbol = "✖" if self.level == "error" else "⚠"
        return f"  {symbol} [{self.component_id}] {self.field}: {self.message}"


def validate_component(comp: dict, index: int) -> list[ValidationError]:
    errors: list[ValidationError] = []
    cid = comp.get("编号", f"构件{index + 1}")

    comp_type = comp.get("类型", "")
    if comp_type not in VALID_TYPES:
        errors.append(ValidationError("error", cid, "类型", f"类型必须为'板'或'梁'，当前为'{comp_type}'"))
        return errors

    required = REQUIRED_BEAM_KEYS if comp_type == "梁" else REQUIRED_PLATE_KEYS
    for key, expected_type in required:
        if key not in comp or comp[key] is None:
            errors.append(ValidationError("error", cid, key, "缺少必填项"))
        elif not isinstance(comp[key], expected_type):
            errors.append(ValidationError(
                "error", cid, key,
                f"类型错误，期望 {expected_type.__name__ if isinstance(expected_type, type) else '数值'}，实际为 {type(comp[key]).__name__}"
            ))

    for key, expected_type, default in OPTIONAL_KEYS:
        if key not in comp or comp[key] is None:
            comp[key] = default

    for key, (lo, hi, msg) in RANGE_LIMITS.items():
        if key in comp and isinstance(comp[key], (int, float)):
            if comp[key] < lo or comp[key] > hi:
                errors.append(ValidationError("warning", cid, key, msg))

    if "木方规格" in comp and isinstance(comp.get("木方规格"), str):
        if not TIMBER_PATTERN.match(comp["木方规格"]):
            errors.append(ValidationError(
                "error", cid, "木方规格",
                f"格式错误 '{comp['木方规格']}'，期望如 '50x80'"
            ))

    if "主楞规格" in comp and isinstance(comp.get("主楞规格"), str):
        if not STEEL_TUBE_PATTERN.match(comp["主楞规格"]):
            errors.append(ValidationError(
                "warning", cid, "主楞规格",
                f"格式可能不正确 '{comp['主楞规格']}'，期望如 '2Φ48x3.5'"
            ))

    if "扣件类型" in comp:
        if comp["扣件类型"] not in VALID_CLAMP_TYPES:
            errors.append(ValidationError(
                "warning", cid, "扣件类型",
                f"扣件类型 '{comp['扣件类型']}' 不在标准列表中，将按直角扣件计算"
            ))

    if "模板类型" in comp:
        if comp["模板类型"] not in VALID_FORMWORK_TYPES:
            errors.append(ValidationError(
                "warning", cid, "模板类型",
                f"模板类型 '{comp['模板类型']}' 不在标准列表中"
            ))

    return errors


def validate_yaml(data: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []

    if "工程名称" not in data:
        errors.append(ValidationError("warning", "全局", "工程名称", "未填写工程名称"))

    if "构件列表" not in data or not isinstance(data.get("构件列表"), list):
        errors.append(ValidationError("error", "全局", "构件列表", "缺少构件列表或格式不正确"))
        return errors

    if len(data["构件列表"]) == 0:
        errors.append(ValidationError("error", "全局", "构件列表", "构件列表为空"))

    for i, comp in enumerate(data["构件列表"]):
        if not isinstance(comp, dict):
            errors.append(ValidationError("error", f"构件{i + 1}", "整体", "构件数据格式不正确，应为字典"))
            continue
        errors.extend(validate_component(comp, i))

    return errors


def has_blocking_errors(errors: list[ValidationError]) -> bool:
    return any(e.level == "error" for e in errors)
