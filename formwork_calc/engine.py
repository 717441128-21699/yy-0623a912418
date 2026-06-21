import os
from datetime import datetime
from .calc import (
    MaterialParams,
    run_all_checks,
    _get_equivalent_area_load,
)
from .validator import validate_yaml, has_blocking_errors


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


def _build_material_params(data: dict) -> MaterialParams:
    mat_data = data.get("材料参数", {})
    kwargs = {}
    for yaml_key, attr_name in MATERIAL_KEY_MAP.items():
        if yaml_key in mat_data:
            kwargs[attr_name] = mat_data[yaml_key]
    return MaterialParams(**kwargs)


def _format_check_result(r) -> str:
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


def run_batch(data: dict, output_path: str | None = None) -> str:
    errors = validate_yaml(data)
    lines: list[str] = []

    project_name = data.get("工程名称", "未命名工程")
    project_code = data.get("项目编号", "—")
    lines.append("=" * 70)
    lines.append(f"  模板支撑验算报告")
    lines.append(f"  工程: {project_name}  |  编号: {project_code}")
    lines.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)

    if errors:
        lines.append("")
        lines.append("▶ 参数校验:")
        for e in errors:
            lines.append(str(e))
        if has_blocking_errors(errors):
            lines.append("")
            lines.append("  存在阻断性错误，无法继续验算。请修正后重试。")
            lines.append("=" * 70)
            result_text = "\n".join(lines)
            _maybe_write(output_path, result_text)
            return result_text
        else:
            lines.append("  以上警告不影响计算，继续验算...")

    mat = _build_material_params(data)
    components = data.get("构件列表", [])

    total_pass = 0
    total_fail = 0

    for comp in components:
        cid = comp.get("编号", "—")
        lines.append("")
        lines.append("─" * 50)
        lines.append(_format_component_header(comp))
        lines.append("─" * 50)

        q_d, q_s = _get_equivalent_area_load(comp, mat)
        lines.append(f"    等效面荷载 q={q_d:.2f} kN/m², 标准值 qk={q_s:.2f} kN/m²")

        results = run_all_checks(comp, mat)
        for r in results:
            lines.append(_format_check_result(r))
            if r.passed:
                total_pass += 1
            else:
                total_fail += 1

    lines.append("")
    lines.append("=" * 70)
    lines.append(f"  验算汇总: 通过 {total_pass} 项, 不通过 {total_fail} 项")
    if total_fail > 0:
        lines.append("  ※ 不满足项需调整参数后重新验算")
    else:
        lines.append("  ✔ 全部验算通过")
    lines.append("=" * 70)

    result_text = "\n".join(lines)
    _maybe_write(output_path, result_text)
    return result_text


def _maybe_write(path: str | None, content: str):
    if path:
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
