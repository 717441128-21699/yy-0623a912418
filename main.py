import argparse
import sys
import os

import yaml

from formwork_calc.engine import run_batch, run_batch_from_components
from formwork_calc.validator import validate_yaml, validate_components, has_blocking_errors, ValidationError
from formwork_calc.importer import load_components
from formwork_calc.exporter import export_auto, export_to_csv, export_to_json


def _friendly_exit(msg: str, code: int = 1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def main():
    parser = argparse.ArgumentParser(
        prog="formwork-calc",
        description="模板支撑验算命令行工具 — 批量验算立杆承载力、木方挠度、主楞强度、扣件抗滑",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础：YAML参数中带构件列表
  python main.py example_input.yaml

  # 从CSV读取构件列表，工程信息和材料仍用YAML
  python main.py example_input.yaml -c components.csv

  # 从Excel读取构件（第2个工作表）
  python main.py example_input.yaml -c parts.xlsx -s 1

  # 输出文本报告 + CSV/JSON明细
  python main.py example_input.yaml -o report.txt --export-csv result.csv --export-json result.json

  # 仅校验参数
  python main.py example_input.yaml --check-only
""",
    )
    parser.add_argument(
        "input",
        help="工程参数文件路径（YAML格式，含工程名称、材料参数）",
    )
    parser.add_argument(
        "-c", "--components",
        help="构件列表文件路径（.csv 或 .xlsx），若指定则覆盖YAML中的构件列表",
        default=None,
    )
    parser.add_argument(
        "-s", "--sheet",
        help="Excel构件列表的工作表（名称或索引，默认第一个）",
        default=None,
    )
    parser.add_argument(
        "-o", "--output",
        help="文本报告输出路径（默认仅输出到终端）",
        default=None,
    )
    parser.add_argument(
        "--export-csv",
        help="导出结构化验算明细到CSV",
        default=None,
    )
    parser.add_argument(
        "--export-json",
        help="导出结构化验算明细到JSON",
        default=None,
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="仅校验参数文件，不执行计算",
    )

    args = parser.parse_args()

    if not os.path.isfile(args.input):
        _friendly_exit(f"错误: 工程参数文件不存在 '{args.input}'")

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        _friendly_exit(f"错误: YAML解析失败 — {e}")
    except UnicodeDecodeError:
        _friendly_exit(f"错误: 文件编码不正确，要求 UTF-8")
    except Exception as e:
        _friendly_exit(f"错误: 读取工程参数失败 — {type(e).__name__}: {e}")

    if not isinstance(data, dict):
        _friendly_exit("错误: YAML顶层应为字典（mapping）结构")

    external_components = None
    if args.components:
        if not os.path.isfile(args.components):
            _friendly_exit(f"错误: 构件列表文件不存在 '{args.components}'")
        try:
            sheet_arg: str | int | None = None
            if args.sheet is not None:
                try:
                    sheet_arg = int(args.sheet)
                except ValueError:
                    sheet_arg = args.sheet
            external_components = load_components(args.components, sheet=sheet_arg)
            if not external_components:
                _friendly_exit(f"错误: 构件列表文件 '{args.components}' 中没有有效数据行")
            data["构件列表"] = external_components
        except ImportError as e:
            _friendly_exit(f"错误: {e}")
        except ValueError as e:
            _friendly_exit(f"错误: 读取构件列表失败 — {e}")
        except Exception as e:
            _friendly_exit(f"错误: 读取构件列表失败 — {type(e).__name__}: {e}")

    if args.check_only:
        if external_components:
            errors = validate_components(external_components)
            if "工程名称" not in data or not data.get("工程名称"):
                errors.insert(0, ValidationError("warning", "全局", "工程名称", "未填写工程名称"))
        else:
            errors = list(validate_yaml(data))
        if errors:
            print("参数校验结果:")
            for e in errors:
                print(str(e))
            if has_blocking_errors(errors):
                print("\n存在阻断性错误，请修正后重试。")
                sys.exit(1)
            else:
                print("\n仅有警告/信息，无阻断性错误。")
        else:
            print("参数校验通过，未发现问题。")
        if external_components:
            print(f"已从外部文件加载 {len(external_components)} 条构件。")
        sys.exit(0)

    try:
        result = run_batch(data, output_path=args.output)
    except Exception as e:
        _friendly_exit(f"错误: 验算过程中出现未处理异常 — {type(e).__name__}: {e}")

    print(result.raw_report)

    if args.output:
        print(f"\n文本报告已保存至: {args.output}")

    exported = []
    if args.export_csv:
        try:
            path = export_to_csv(result, args.export_csv)
            exported.append(f"CSV明细: {path}")
        except Exception as e:
            print(f"  [警告] 导出CSV失败: {type(e).__name__}: {e}", file=sys.stderr)
    if args.export_json:
        try:
            path = export_to_json(result, args.export_json)
            exported.append(f"JSON明细: {path}")
        except Exception as e:
            print(f"  [警告] 导出JSON失败: {type(e).__name__}: {e}", file=sys.stderr)
    for line in exported:
        print(f"  已导出 {line}")

    total, passed, skipped = result.components_summary
    if total - passed - skipped > 0 or skipped > 0:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
