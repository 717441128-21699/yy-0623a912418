import argparse
import sys
import os

import yaml

from formwork_calc.engine import run_batch
from formwork_calc.validator import validate_yaml, has_blocking_errors


def main():
    parser = argparse.ArgumentParser(
        prog="formwork-calc",
        description="模板支撑验算命令行工具 — 批量验算立杆承载力、木方挠度、主楞强度、扣件抗滑",
    )
    parser.add_argument(
        "input",
        help="参数文件路径（YAML格式）",
    )
    parser.add_argument(
        "-o", "--output",
        help="输出结果文件路径（默认输出到终端）",
        default=None,
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="仅校验参数文件，不执行计算",
    )

    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"错误: 文件不存在 '{args.input}'", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"错误: YAML解析失败 — {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误: 读取文件失败 — {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict):
        print("错误: YAML顶层应为字典（mapping）结构", file=sys.stderr)
        sys.exit(1)

    if args.check_only:
        errors = validate_yaml(data)
        if errors:
            print("参数校验结果:")
            for e in errors:
                print(str(e))
            if has_blocking_errors(errors):
                print("\n存在阻断性错误，请修正后重试。")
                sys.exit(1)
            else:
                print("\n仅有警告，无阻断性错误。")
        else:
            print("参数校验通过，未发现问题。")
        sys.exit(0)

    output_path = args.output
    result_text = run_batch(data, output_path=output_path)
    print(result_text)

    if output_path:
        print(f"\n结果已保存至: {output_path}")


if __name__ == "__main__":
    main()
