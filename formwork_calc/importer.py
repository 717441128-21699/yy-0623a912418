import os
import csv
from typing import Any

CSV_FIELD_ALIASES = {
    "编号": ["编号", "构件编号", "ID", "id", "序号", "name"],
    "类型": ["类型", "构件类型", "type", "category", "Type"],
    "混凝土厚度_mm": ["混凝土厚度_mm", "混凝土厚度", "板厚_mm", "板厚", "h", "thickness_mm", "slab_thickness_mm"],
    "梁截面宽_mm": ["梁截面宽_mm", "梁宽_mm", "梁宽", "b_mm", "beam_width_mm"],
    "梁截面高_mm": ["梁截面高_mm", "梁高_mm", "梁高", "h_mm", "beam_height_mm"],
    "支撑高度_m": ["支撑高度_m", "支模高度_m", "层高_m", "支撑高度", "支模高度", "层高", "H_m", "height_m"],
    "模板类型": ["模板类型", "模板", "formwork_type", "formwork"],
    "模板厚度_mm": ["模板厚度_mm", "模板厚度", "template_thickness_mm"],
    "木方规格": ["木方规格", "次楞规格", "木方", "joist_size", "joist_spec", "timber_size"],
    "木方间距_mm": ["木方间距_mm", "次楞间距_mm", "木方间距", "次楞间距", "joist_spacing_mm"],
    "主楞规格": ["主楞规格", "主楞", "钢管规格", "leder_size", "main_joist_size", "steel_size"],
    "主楞间距_mm": ["主楞间距_mm", "主楞间距", "main_joist_spacing_mm"],
    "立杆纵距_mm": ["立杆纵距_mm", "立杆纵距", "纵距_mm", "vertical_long_spacing_mm", "longitudinal_spacing_mm"],
    "立杆横距_mm": ["立杆横距_mm", "立杆横距", "横距_mm", "vertical_lat_spacing_mm", "lateral_spacing_mm"],
    "立杆步距_mm": ["立杆步距_mm", "立杆步距", "步距_mm", "step_mm", "vertical_step_mm"],
    "扣件类型": ["扣件类型", "扣件", "clamp_type", "coupler_type"],
    "施工活荷载_kN_m2": ["施工活荷载_kN_m2", "施工活荷载", "活载", "活荷载", "live_load_kN_m2", "Qk"],
    "倾倒混凝土荷载_kN_m2": ["倾倒混凝土荷载_kN_m2", "倾倒混凝土荷载", "浇筑荷载", "pour_load_kN_m2"],
}


def _build_header_map(fieldnames: list[str]) -> dict[str, str]:
    header_map = {}
    lower_to_orig = {fn.strip(): fn for fn in fieldnames if fn}
    lower_to_orig.update({fn.strip().lower(): fn for fn in fieldnames if fn})
    for std_key, aliases in CSV_FIELD_ALIASES.items():
        for alias in aliases:
            if alias in lower_to_orig:
                header_map[std_key] = lower_to_orig[alias]
                break
            if alias.lower() in lower_to_orig:
                header_map[std_key] = lower_to_orig[alias.lower()]
                break
    return header_map


def load_components_from_csv(path: str) -> list[dict[str, Any]]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"CSV 文件不存在: {path}")
    components = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV 文件为空或缺少表头: {path}")
        header_map = _build_header_map(reader.fieldnames)
        for row_num, row in enumerate(reader, start=2):
            comp: dict[str, Any] = {}
            for std_key, csv_col in header_map.items():
                val = row.get(csv_col, None)
                if val is None:
                    continue
                if isinstance(val, str):
                    s = val.strip()
                    if s == "":
                        continue
                    comp[std_key] = s
                else:
                    comp[std_key] = val
            if "编号" not in comp or not comp["编号"]:
                comp["编号"] = f"ROW{row_num}"
            components.append(comp)
    return components


def load_components_from_excel(path: str, sheet: str | int = 0) -> list[dict[str, Any]]:
    try:
        import openpyxl
    except ImportError:
        raise ImportError(
            "读取 Excel 文件需要安装 openpyxl，执行: pip install openpyxl"
        )
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Excel 文件不存在: {path}")
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb[sheet] if isinstance(sheet, str) else wb.worksheets[sheet]
    except (KeyError, IndexError):
        sheet_name = sheet if isinstance(sheet, str) else f"第{sheet + 1}个"
        raise ValueError(f"找不到 {sheet_name} 工作表")
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        raise ValueError(f"Excel 工作表为空: {path}")
    header_cells = []
    for idx, h in enumerate(header_row):
        if h is None:
            header_cells.append(f"__col_{idx}")
        else:
            header_cells.append(str(h).strip())
    header_map = _build_header_map(header_cells)
    components = []
    for row_num, raw_row in enumerate(rows_iter, start=3):
        comp: dict[str, Any] = {}
        for std_key, csv_col in header_map.items():
            if csv_col in header_cells:
                col_idx = header_cells.index(csv_col)
                val = raw_row[col_idx] if col_idx < len(raw_row) else None
                if val is None:
                    continue
                if isinstance(val, str):
                    s = val.strip()
                    if s == "":
                        continue
                    comp[std_key] = s
                else:
                    comp[std_key] = val
        if "编号" not in comp or not comp["编号"]:
            comp["编号"] = f"ROW{row_num}"
        components.append(comp)
    wb.close()
    return components


def load_components(path: str, sheet: str | int | None = None) -> list[dict[str, Any]]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return load_components_from_csv(path)
    if ext in (".xlsx", ".xlsm"):
        return load_components_from_excel(path, sheet=sheet if sheet is not None else 0)
    if ext in (".xls",):
        raise ValueError("旧版 .xls 格式不支持，请先另存为 .xlsx 或 CSV")
    raise ValueError(f"不支持的构件列表文件格式: {ext}（支持 .csv / .xlsx）")
