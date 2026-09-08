#!/usr/bin/env python3
"""Upload a local PDF to MinerU Precision Extract and save every result file."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


MAX_PDF_BYTES = 200 * 1024 * 1024


class ConversionError(RuntimeError):
    """An expected, user-facing conversion error."""


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("必须是大于 0 的整数")
    return number


@dataclass(frozen=True)
class ConversionOptions:
    pdf: Path
    output_root: Path
    token: str
    model: str = "vlm"
    language: str = "en"
    ocr: bool = False
    formula: bool = True
    table: bool = True
    pages: str | None = None
    timeout: int = 1800
    overwrite: bool = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="使用 MinerU 精准解析 API 转换本地 PDF，并保存完整解析结果。"
    )
    parser.add_argument("pdf", type=Path, help="要解析的本地 PDF 文件")
    parser.add_argument(
        "-o",
        "--output",
        dest="output_root",
        type=Path,
        default=Path("mineru_output"),
        help="结果根目录（默认：./mineru_output）",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="从指定的 .env 文件读取 MINERU_TOKEN（默认：读取当前运行目录下的 .env）",
    )
    parser.add_argument(
        "--model",
        choices=("vlm", "pipeline"),
        default="vlm",
        help="解析模型（默认：vlm）",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="文档语言，例如 en、ch（默认：en）",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="为扫描版 PDF 开启 OCR",
    )
    parser.add_argument(
        "--no-formula",
        action="store_true",
        help="关闭公式识别",
    )
    parser.add_argument(
        "--no-table",
        action="store_true",
        help="关闭表格识别",
    )
    parser.add_argument(
        "--pages",
        help='只解析指定页，例如 "1-20" 或 "2,4-6"（默认：全部）',
    )
    parser.add_argument(
        "--timeout",
        type=positive_int,
        default=1800,
        help="等待解析完成的最长秒数（默认：1800）",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖同名 PDF 已有的结果目录",
    )
    return parser


def validate_options(options: ConversionOptions) -> tuple[Path, Path]:
    if not options.token.strip():
        raise ConversionError(
            "未设置 MINERU_TOKEN。请先在 MinerU API 管理页面创建 Token，然后任选其一："
            "1) 在运行目录创建 .env 文件并写入 MINERU_TOKEN='你的Token'；"
            "2) 执行 export MINERU_TOKEN='你的Token'（也可用 --env-file 指定 .env 路径）"
        )

    try:
        pdf = options.pdf.expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise ConversionError(f"PDF 文件不存在：{options.pdf}") from exc

    if not pdf.is_file():
        raise ConversionError(f"输入路径不是文件：{pdf}")
    if pdf.suffix.lower() != ".pdf":
        raise ConversionError(f"当前程序只接受 PDF 文件：{pdf}")
    if pdf.stat().st_size > MAX_PDF_BYTES:
        raise ConversionError("PDF 超过 MinerU 精准解析 API 的 200 MB 限制")

    output_root = options.output_root.expanduser().resolve()
    destination = output_root / pdf.stem
    if destination.exists() and not options.overwrite:
        raise ConversionError(
            f"结果目录已存在：{destination}。如需替换，请添加 --overwrite"
        )
    if destination.exists() and not destination.is_dir():
        raise ConversionError(f"结果路径已存在且不是目录：{destination}")

    return pdf, destination


def organize_result(directory: Path) -> Path:
    """Move auxiliary MinerU artifacts into ``temp/`` without altering assets."""
    root = directory.resolve(strict=True)
    if not root.is_dir():
        raise ConversionError(f"解析结果路径不是目录：{root}")

    temp_dir = root / "temp"
    if temp_dir.exists() and not temp_dir.is_dir():
        raise ConversionError(f"无法整理结果：{temp_dir} 已存在且不是目录")

    def should_stay(entry: Path) -> bool:
        if entry.name in {"images", "temp"}:
            return True
        return entry.is_file() and entry.suffix.lower() in {".md", ".pdf"}

    to_move = [entry for entry in root.iterdir() if not should_stay(entry)]

    # Check every destination before moving anything so a collision cannot leave
    # the staging result only partially organized.
    for entry in to_move:
        target = temp_dir / entry.name
        if target.exists():
            raise ConversionError(f"无法整理结果，目标已存在：{target}")

    temp_dir.mkdir(exist_ok=True)
    for entry in to_move:
        entry.replace(temp_dir / entry.name)

    return temp_dir


def convert_pdf(
    options: ConversionOptions,
    *,
    client_factory: Callable[[str], Any] | None = None,
) -> Path:
    """Run a blocking precision extraction and atomically publish its files."""
    pdf, destination = validate_options(options)

    if client_factory is None:
        try:
            from mineru import MinerU
        except ImportError as exc:
            raise ConversionError(
                "未安装 MinerU SDK，请执行：pip install -r requirements.txt"
            ) from exc
        client_factory = MinerU

    print(f"正在提交：{pdf}")
    print(
        "解析参数："
        f"model={options.model}, language={options.language}, "
        f"ocr={options.ocr}, formula={options.formula}, table={options.table}"
    )

    try:
        with client_factory(options.token.strip()) as client:
            result = client.extract(
                str(pdf),
                model=options.model,
                ocr=options.ocr,
                formula=options.formula,
                table=options.table,
                language=options.language,
                pages=options.pages,
                timeout=options.timeout,
            )

            if getattr(result, "state", None) != "done":
                detail = getattr(result, "error", None) or "任务未成功完成"
                raise ConversionError(f"MinerU 解析失败：{detail}")

            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix=f".{pdf.stem}-", dir=destination.parent
            ) as temp_dir:
                temp_path = Path(temp_dir)
                result.save_all(str(temp_path))
                organize_result(temp_path)

                if destination.exists():
                    shutil.rmtree(destination)
                temp_path.replace(destination)
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(f"MinerU 请求或结果保存失败：{exc}") from exc

    return destination


def load_env_file(path: Path) -> None:
    """Load environment variables from a .env file (real env vars win)."""
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise ConversionError(
            "未安装 python-dotenv，请执行：pip install -r requirements.txt"
        ) from exc
    # override=False：已存在的真实环境变量优先于 .env 文件中的同名键
    load_dotenv(path, override=False)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.env_file is not None:
            env_file = args.env_file.expanduser().resolve()
            if not env_file.is_file():
                raise ConversionError(f".env 文件不存在：{env_file}")
        else:
            env_file = Path.cwd() / ".env"
            if not env_file.is_file():
                env_file = None

        if env_file is not None:
            load_env_file(env_file)

        options = ConversionOptions(
            pdf=args.pdf,
            output_root=args.output_root,
            token=os.environ.get("MINERU_TOKEN", ""),
            model=args.model,
            language=args.language,
            ocr=args.ocr,
            formula=not args.no_formula,
            table=not args.no_table,
            pages=args.pages,
            timeout=args.timeout,
            overwrite=args.overwrite,
        )

        destination = convert_pdf(options)
    except ConversionError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130

    print(f"解析完成，完整结果已保存到：{destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
