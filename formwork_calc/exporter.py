import os
import json
import csv
from typing import Any

from .engine import BatchResult, ComponentDetail

CHECK_ITEMS = ["木方抗弯强度", "木方挠度", "主楞强度", "主楞挠度", "立杆承载力", "扣件抗滑"]

CSV_HEADERS = [
    "编号", "类型", "描述", "支撑高度_m", "状态",
    "等效面荷载设计值_kN_m2", "等效面荷载标准值_kN_m2",
    "使用默认荷载", "备注/错误",
]
for item in CHECK_ITEMS:
    CSV_HEADERS.extend([
        f"{item}_计算值", f"{item}_限值", f"{item}_单位",
        f"{item}_利用率", f"{item}_是否通过", f"{item}_建议",
    ])
CSV_HEADERS.extend(["验算通过项数", "验算不通过项数"])


def _check_dict(detail: ComponentDetail) -> dict[str, Any]:
    out = {}
    for item in CHECK_ITEMS:
        out[f"{item}_计算值"] = ""
        out[f"{item}_限值"] = ""
        out[f"{item}_单位"] = ""
        out[f"{item}_利用率"] = ""
        out[f"{item}_是否通过"] = ""
        out[f"{item}_建议"] = ""
    for check in detail.checks:
        if check.item in CHECK_ITEMS:
            out[f"{check.item}_计算值"] = check.demand
            out[f"{check.item}_限值"] = check.capacity
            out[f"{check.item}_单位"] = check.unit
            out[f"{check.item}_利用率"] = round(check.ratio, 3)
            out[f"{check.item}_是否通过"] = "是" if check.passed else "否"
            out[f"{check.item}_建议"] = check.suggestion
    return out


def _detail_to_row(detail: ComponentDetail) -> dict[str, Any]:
    status = "通过" if detail.all_passed else ("跳过" if detail.skipped else "不通过")
    default_load_note = "; ".join(
        f"{k}={v}" for k, v in detail.default_load_applied
    ) if detail.default_load_applied else ""
    error_note = "; ".join(detail.errors) if detail.errors else ""

    row = {
        "编号": detail.component_id,
        "类型": detail.component_type,
        "描述": detail.description,
        "支撑高度_m": detail.support_height_m,
        "状态": status,
        "等效面荷载设计值_kN_m2": detail.design_load_kN_m2,
        "等效面荷载标准值_kN_m2": detail.std_load_kN_m2,
        "使用默认荷载": default_load_note,
        "备注/错误": error_note,
    }
    row.update(_check_dict(detail))
    row["验算通过项数"] = detail.total_pass
    row["验算不通过项数"] = detail.total_fail
    return row


def export_to_csv(batch: BatchResult, path: str) -> str:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for detail in batch.components:
            writer.writerow(_detail_to_row(detail))
    return path


def export_to_json(batch: BatchResult, path: str) -> str:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    data = {
        "project_name": batch.project_name,
        "project_code": batch.project_code,
        "generated_at": batch.generated_at,
        "components": [],
        "summary": {
            "total_components": len(batch.components),
            "passed_components": sum(1 for c in batch.components if c.all_passed),
            "skipped_components": sum(1 for c in batch.components if c.skipped),
            "failed_components": sum(1 for c in batch.components if (not c.all_passed) and not c.skipped),
            "failed_ids": [c.component_id for c in batch.failed_components],
        },
    }
    for detail in batch.components:
        comp_obj = {
            "id": detail.component_id,
            "type": detail.component_type,
            "description": detail.description,
            "support_height_m": detail.support_height_m,
            "status": "passed" if detail.all_passed else ("skipped" if detail.skipped else "failed"),
            "design_load_kN_m2": detail.design_load_kN_m2,
            "std_load_kN_m2": detail.std_load_kN_m2,
            "default_load_applied": [
                {"field": k, "value": v} for k, v in detail.default_load_applied
            ],
            "errors": detail.errors,
            "checks": [],
            "total_pass": detail.total_pass,
            "total_fail": detail.total_fail,
        }
        for c in detail.checks:
            comp_obj["checks"].append({
                "item": c.item,
                "passed": c.passed,
                "demand": c.demand,
                "capacity": c.capacity,
                "unit": c.unit,
                "ratio": round(c.ratio, 3),
                "suggestion": c.suggestion,
            })
        data["components"].append(comp_obj)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def export_auto(batch: BatchResult, path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return export_to_csv(batch, path)
    if ext == ".json":
        return export_to_json(batch, path)
    raise ValueError(f"不支持的导出格式: {ext}（支持 .csv / .json）")
