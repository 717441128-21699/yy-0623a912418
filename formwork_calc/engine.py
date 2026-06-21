import os
import copy
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any

from .calc import (
    MaterialParams,
    CheckResult,
    run_all_checks,
    _get_equivalent_area_load,
    SpecParseError,
)
from .validator import (
    validate_yaml,
    validate_components,
    has_blocking_errors,
    ValidationError,
)


MATERIAL_KEY_MAP = {
    "钢管外径_mm": "steel_tube_od_mm",
    "钢管壁厚_mm": "steel_tube_wall_mm",
    "钢管弹性模量_N_mm2": "steel_E_N_mm2",
    "钢管抗拉强度设计值_N_mm2": "steel_f_N_mm2",
    "木方弹性模量_N_mm2": "timber_E_N_mm2",
    "木方抗弯强度设计值_N_mm2": "timber_f_N_mm2",
    "胶合板弹性模量_N_mm2": "plywood_E_N_mm2",
    "胶合板抗弯强度设计值_N_mm2": "plywood_f_N_mm2",
    "直角扣件抗滑承载力_kN": "right_angle_clamp_kN",
    "旋转扣件抗滑承载力_kN": "rotating_clamp_kN",
    "钢筋混凝土容重_kN_m3": "concrete_density_kN_m3",
}


@dataclass
class ComponentDetail:
    component_id: str
    component_type: str
    description: str
    support_height_m: float
    errors: list[str] = field(default_factory=list)
    skipped: bool = False
    default_load_applied: list[tuple[str, float]] = field(default_factory=list)
    design_load_kN_m2: float = 0.0
    std_load_kN_m2: float = 0.0
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def total_pass(self):
        return sum(1 for c in self.checks if c.passed)

    @property
    def total_fail(self):
        return sum(1 for c in self.checks if not c.passed)

    @property
    def all_passed(self):
        return len(self.checks) > 0 and self.total_fail == 0 and not self.skipped


@dataclass
class BatchResult:
    project_name: str
    project_code: str
    generated_at: str
    validation_errors: list[ValidationError] = field(default_factory=list)
    components: list[ComponentDetail] = field(default_factory=list)
    raw_report: str = ""

    @property
    def failed_components(self):
        return [c for c in self.components if (not c.all_passed) or c.skipped]

    @property
    def components_summary(self):
        total = len(self.components)
        passed = sum(1 for c in self.components if c.all_passed)
        skipped = sum(1 for c in self.components if c.skipped)
        return total, passed, skipped


def _build_material_params(data: dict) -> MaterialParams:
    mat_data = data.get("材料参数", {}) or {}
    kwargs = {}
    for yaml_key, attr_name in MATERIAL_KEY_MAP.items():
        if yaml_key in mat_data and mat_data[yaml_key] is not None:
            try:
                kwargs[attr_name] = float(mat_data[yaml_key])
            except (ValueError, TypeError):
                pass
    return MaterialParams(**kwargs)


def _format_check_result(r: CheckResult) -> str:
    status = "✔ 满足" if r.passed else "✖ 不满足"
    line = f"    {r.item}: {status}  (计算值={r.demand}{r.unit}, 容许值={r.capacity}{r.unit}, 利用率={r.ratio:.2f})"
    if not r.passed and r.suggestion:
        line += f"\n    → 建议: {r.suggestion}"
    return line


def _format_component_header(comp: dict) -> str:
    ctype = comp.get("类型", "未知")
    cid = comp.get("编号", "—")
    if ctype == "梁":
        detail = f"梁截面 {comp.get('梁截面宽_mm', '?')}×{comp.get('梁截面高_mm', '?')}mm"
    else:
        detail = f"板厚 {comp.get('混凝土厚度_mm', '?')}mm"
    return f"  [{cid}] 类型={ctype} | {detail} | 支撑高度={comp.get('支撑高度_m', '?')}m"


def _component_has_errors(component_id: str, validation_errors: list[ValidationError]) -> bool:
    for e in validation_errors:
        if e.component_id == component_id and e.level == "error":
            return True
    return False


def _safe_comp_desc(comp: dict) -> tuple[str, str, str, float]:
    cid = str(comp.get("编号", "未命名"))
    ctype = str(comp.get("类型", "未知"))
    if ctype == "梁":
        desc = f"梁 {comp.get('梁截面宽_mm', '?')}×{comp.get('梁截面高_mm', '?')}mm"
    elif ctype == "板":
        desc = f"板厚 {comp.get('混凝土厚度_mm', '?')}mm"
    else:
        desc = f"{ctype}"
    h = comp.get("支撑高度_m", 0)
    try:
        h = float(h)
    except (ValueError, TypeError):
        h = 0.0
    return cid, ctype, desc, h


def run_batch(data: dict, output_path: str | None = None) -> BatchResult:
    validation_errors = validate_yaml(data)
    lines: list[str] = []

    project_name = str(data.get("工程名称") or "未命名工程")
    project_code = str(data.get("项目编号") or "—")
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    batch = BatchResult(
        project_name=project_name,
        project_code=project_code,
        generated_at=generated_at,
        validation_errors=validation_errors,
    )

    lines.append("=" * 70)
    lines.append(f"  模板支撑验算报告")
    lines.append(f"  工程: {project_name}  |  编号: {project_code}")
    lines.append(f"  生成时间: {generated_at}")
    lines.append("=" * 70)

    if validation_errors:
        lines.append("")
        lines.append("▶ 参数校验:")
        for e in validation_errors:
            lines.append(str(e))

    mat = _build_material_params(data)
    raw_components = data.get("构件列表", []) or []
    validated_components = copy.deepcopy(raw_components)

    blocking = has_blocking_errors([e for e in validation_errors if e.component_id == "全局"])

    if blocking:
        lines.append("")
        lines.append("  全局存在阻断性错误，无法继续验算。请修正后重试。")
        lines.append("=" * 70)
        batch.raw_report = "\n".join(lines)
        _maybe_write(output_path, batch.raw_report)
        return batch

    for comp in validated_components:
        if not isinstance(comp, dict):
            cid, ctype, desc, h = "未知", "未知", "数据格式错误", 0.0
            detail = ComponentDetail(
                component_id=cid, component_type=ctype,
                description=desc, support_height_m=h, skipped=True,
                errors=["构件数据格式错误，无法解析"],
            )
            batch.components.append(detail)
            continue

        cid, ctype, desc, h = _safe_comp_desc(comp)

        if _component_has_errors(cid, validation_errors):
            comp_errors = [str(e) for e in validation_errors if e.component_id == cid and e.level == "error"]
            lines.append("")
            lines.append("─" * 50)
            lines.append(f"  [{cid}] {desc}（跳过 — 含阻断性参数错误）")
            lines.append("─" * 50)
            for ce in comp_errors:
                lines.append(f"    ✖ 错误: {ce}")
            detail = ComponentDetail(
                component_id=cid, component_type=ctype,
                description=desc, support_height_m=h, skipped=True,
                errors=comp_errors,
            )
            batch.components.append(detail)
            continue

        lines.append("")
        lines.append("─" * 50)
        lines.append(_format_component_header(comp))
        lines.append("─" * 50)

        default_applied = comp.get("_default_applied", [])
        if default_applied:
            note_parts = [f"{k}={v} kN/m²" for k, v in default_applied]
            lines.append(f"    ⚑ 使用默认荷载: {', '.join(note_parts)}")

        try:
            q_d, q_s = _get_equivalent_area_load(comp, mat)
            lines.append(f"    等效面荷载 q={q_d:.2f} kN/m², 标准值 qk={q_s:.2f} kN/m²")
        except Exception as e:
            lines.append(f"    ✖ 计算荷载失败: {e}")
            detail = ComponentDetail(
                component_id=cid, component_type=ctype,
                description=desc, support_height_m=h, skipped=True,
                errors=[f"计算荷载失败: {e}"],
                default_load_applied=list(default_applied),
            )
            batch.components.append(detail)
            continue

        detail = ComponentDetail(
            component_id=cid, component_type=ctype,
            description=desc, support_height_m=h,
            default_load_applied=list(default_applied),
            design_load_kN_m2=round(q_d, 3),
            std_load_kN_m2=round(q_s, 3),
        )

        try:
            checks = run_all_checks(comp, mat)
            detail.checks = checks
            for r in checks:
                lines.append(_format_check_result(r))
        except SpecParseError as e:
            lines.append(f"    ✖ 规格解析失败: {e}")
            detail.skipped = True
            detail.errors.append(str(e))
        except ZeroDivisionError as e:
            lines.append(f"    ✖ 计算错误: 数值出现除零，请检查间距、壁厚等数值是否为 0")
            detail.skipped = True
            detail.errors.append(f"除零错误: {e}")
        except Exception as e:
            lines.append(f"    ✖ 计算时出现未知错误: {type(e).__name__}: {e}")
            detail.skipped = True
            detail.errors.append(f"{type(e).__name__}: {e}")

        batch.components.append(detail)

    total, passed, skipped = batch.components_summary
    total_checks_pass = sum(c.total_pass for c in batch.components)
    total_checks_fail = sum(c.total_fail for c in batch.components)

    lines.append("")
    lines.append("─" * 50)
    lines.append("▶ 构件汇总")
    lines.append("─" * 50)
    lines.append(f"  共 {total} 个构件: 通过 {passed}, 跳过 {skipped}, 未通过 {total - passed - skipped}")
    failed_comps = batch.failed_components
    if failed_comps:
        lines.append(f"  ⚠ 需关注构件: {', '.join(c.component_id for c in failed_comps)}")
    lines.append(f"  验算项: 通过 {total_checks_pass}, 不通过 {total_checks_fail}")

    lines.append("")
    lines.append("=" * 70)
    lines.append(f"  验算汇总: 通过 {total_checks_pass} 项, 不通过 {total_checks_fail} 项")
    if total_checks_fail > 0 or skipped > 0:
        lines.append("  ※ 不满足或跳过的构件需调整参数后重新验算")
    else:
        lines.append("  ✔ 全部验算通过")
    lines.append("=" * 70)

    batch.raw_report = "\n".join(lines)
    _maybe_write(output_path, batch.raw_report)
    return batch


def run_batch_from_components(base_data: dict, components: list[dict], output_path: str | None = None) -> BatchResult:
    data = dict(base_data)
    data["构件列表"] = components
    return run_batch(data, output_path=output_path)


def _maybe_write(path: str | None, content: str):
    if path:
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
