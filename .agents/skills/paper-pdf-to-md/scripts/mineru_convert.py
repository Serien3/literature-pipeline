#!/usr/bin/env python3
"""Convert a local PDF with MinerU, omitting its redundant origin PDF copy."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


MAX_PDF_BYTES = 200 * 1024 * 1024
META_FILE_NAME = "meta.md"
SOURCE_FILE_NAME = "full.md"


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
    output_root: Path | None
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
        default=None,
        help="直接保存结果的目录（默认：输入 PDF 所在目录，不追加子目录）",
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
        help="覆盖同名结果文件，保留输入 PDF 和其他文件",
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

    destination = (
        options.output_root.expanduser().resolve()
        if options.output_root is not None else pdf.parent
    )
    if destination.exists() and not destination.is_dir():
        raise ConversionError(f"结果路径已存在且不是目录：{destination}")

    return pdf, destination


def organize_result(directory: Path) -> Path:
    """Discard downloaded origin PDFs and move auxiliary artifacts into ``temp/``."""
    root = directory.resolve(strict=True)
    if not root.is_dir():
        raise ConversionError(f"解析结果路径不是目录：{root}")

    # This directory contains only freshly downloaded results, never the input PDF.
    for entry in root.rglob("*_origin.pdf"):
        if entry.is_file():
            entry.unlink()

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


def add_yaml_type(path: Path, document_type: str) -> None:
    """Add or update a Markdown YAML front matter ``type`` field."""
    if not path.is_file():
        raise ConversionError(f"MinerU 结果缺少 Markdown 文件：{path}")

    text = path.read_text(encoding="utf-8")
    prefix = f"---\ntype: {document_type}\n---\n"

    # MinerU normally returns a Markdown file without front matter. If it does
    # return one in the future, update its type field instead of creating two
    # YAML blocks at the top of the document.
    if text.startswith("---\n"):
        lines = text.splitlines(keepends=True)
        closing_index = next(
            (
                index
                for index, line in enumerate(lines[1:], start=1)
                if line.rstrip("\r\n") in {"---", "..."}
            ),
            None,
        )
        if closing_index is not None:
            header = lines[: closing_index + 1]
            for index, line in enumerate(header[1:], start=1):
                if line.lstrip().startswith("type:"):
                    ending = "\r\n" if line.endswith("\r\n") else "\n"
                    header[index] = f"type: {document_type}{ending}"
                    path.write_text("".join(header + lines[closing_index + 1:]), encoding="utf-8")
                    return
            header.insert(1, f"type: {document_type}\n")
            path.write_text("".join(header + lines[closing_index + 1:]), encoding="utf-8")
            return

    path.write_text(prefix + text, encoding="utf-8")


def add_output_metadata(directory: Path) -> None:
    """Create the literature metadata file and mark the converted source."""
    source_path = directory / SOURCE_FILE_NAME
    if not source_path.is_file() or not source_path.read_text(encoding="utf-8").strip():
        raise ConversionError(f"MinerU 结果缺少非空全文：{source_path}")
    add_yaml_type(source_path, "source")
    (directory / META_FILE_NAME).write_text(
        "---\ntype: literature-meta\n---\n", encoding="utf-8"
    )


def publish_result(staging: Path, destination: Path, pdf: Path, overwrite: bool) -> None:
    """Preflight all collisions, then merge files without deleting the paper directory."""
    entries = sorted(staging.rglob("*"))
    # Metadata belongs to the library/user, even when conversion is overwritten.
    existing_meta = destination / META_FILE_NAME
    if existing_meta.is_symlink() or (existing_meta.exists() and not existing_meta.is_file()):
        raise ConversionError(f"元数据目标必须是普通文件：{existing_meta}")
    if existing_meta.exists():
        entries = [entry for entry in entries if entry.relative_to(staging) != Path(META_FILE_NAME)]
    entries = [entry for entry in entries
               if not (entry.name.endswith("-reading-note.md")
                       and (destination / entry.relative_to(staging)).exists())]
    for entry in entries:
        target = destination / entry.relative_to(staging)
        if entry.is_symlink() or target.is_symlink():
            raise ConversionError(f"结果路径不能是符号链接：{target}")
        if target.resolve() == pdf or (
            target.exists() and target.is_file() and target.samefile(pdf)
        ):
            raise ConversionError(f"结果与输入 PDF 重名，拒绝覆盖：{target}")
        if target.exists():
            if entry.is_dir() != target.is_dir():
                raise ConversionError(f"结果路径文件与目录类型冲突：{target}")
            if entry.is_file() and not overwrite:
                raise ConversionError(f"结果文件已存在：{target}。如需替换，请添加 --overwrite")

    destination.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        target = destination / entry.relative_to(staging)
        if entry.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            entry.replace(target)


def convert_pdf(
    options: ConversionOptions,
    *,
    client_factory: Callable[[str], Any] | None = None,
) -> Path:
    """Run a blocking precision extraction and merge its files into the output directory."""
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
                add_output_metadata(temp_path)

                publish_result(temp_path, destination, pdf, options.overwrite)
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
