"""Command-line interface for one-shot Zotero metadata import."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from .files import PipelineError, VaultLock
from .ingest import Importer
from .library import initialize, load_config
from .pdf_links import PdfLinker
from .zotero import Zotero


DEFAULT_ZOTERO_URL = "http://localhost:23119/api/"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="将 Zotero Collection 元数据一次性导入 Obsidian vault")
    commands = result.add_subparsers(dest="command", required=True)

    collections = commands.add_parser("collections", help="列出 Zotero 个人库的 Collection")
    collections.add_argument("--zotero-url", default=DEFAULT_ZOTERO_URL)

    init = commands.add_parser("init", help="在已有或新建 vault 中初始化最小配置")
    init.add_argument("--vault", type=Path, required=True)
    init.add_argument("--collection", required=True, help="Zotero Collection 的 8 位 key")
    init.add_argument("--zotero-url", default=DEFAULT_ZOTERO_URL)

    doctor = commands.add_parser("doctor", help="检查配置、vault 和 Zotero 连接")
    doctor.add_argument("--vault", type=Path, required=True)

    sync = commands.add_parser("sync", help="导入尚未入库的 Zotero 元数据")
    sync.add_argument("--vault", type=Path, required=True)
    link_pdfs = commands.add_parser("link-pdfs", help="为已入库论文补建或修复 Zotero PDF 链接")
    link_pdfs.add_argument("--vault", type=Path, required=True)
    return result


def _vault(value: Path) -> Path:
    return value.expanduser().resolve()


def doctor(vault: Path) -> int:
    errors: list[str] = []
    try:
        config = load_config(vault)
        print("通过：配置")
    except PipelineError as error:
        print(f"待处理：配置 — {error}")
        return 1
    try:
        with tempfile.TemporaryFile(dir=vault) as handle:
            handle.write(b"check")
        print("通过：vault 可写")
    except OSError as error:
        errors.append(str(error))
        print(f"待处理：vault 不可写 — {error}")
    try:
        with tempfile.TemporaryDirectory(dir=vault) as directory:
            source = Path(directory) / "source.pdf"
            link = Path(directory) / "link.pdf"
            source.write_bytes(b"check")
            os.symlink(source, link, target_is_directory=False)
            if not link.is_symlink():
                raise OSError("创建结果不是符号链接")
        print("通过：PDF 符号链接")
    except OSError as error:
        errors.append(str(error))
        print(f"待处理：PDF 符号链接 — {error}（Windows 请开启开发者模式）")
    try:
        Zotero(config.zotero_url).items(config.collection)
        print("通过：Zotero 与 Collection")
    except (PipelineError, OSError) as error:
        errors.append(str(error))
        print(f"待处理：Zotero 与 Collection — {error}")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = parser().parse_args(argv)
    try:
        if args.command == "collections":
            for collection in Zotero(args.zotero_url).collections():
                data = collection.get("data", {})
                parent = data.get("parentCollection") or "root"
                print(f"{collection.get('key', '')}  {data.get('name', '')}  (parent: {parent})")
            return 0

        vault = _vault(args.vault)
        if args.command == "init":
            vault.mkdir(parents=True, exist_ok=True)
            with VaultLock(vault):
                initialize(vault, args.collection, args.zotero_url)
            print(f"已初始化：{vault}")
            return 0
        if args.command == "doctor":
            return doctor(vault)

        config = load_config(vault)
        if args.command == "link-pdfs":
            with VaultLock(vault):
                summary = PdfLinker(Zotero(config.zotero_url)).link_existing(vault)
            for message in summary.messages:
                print(message, file=sys.stderr)
            print(
                f"PDF 链接完成：papers={summary.papers} linked={summary.linked} "
                f"unchanged={summary.unchanged} missing={summary.missing} "
                f"conflicts={summary.conflicts} failed={summary.failed}"
            )
            return 0 if summary.successful else 1
        with VaultLock(vault):
            summary = Importer(vault, config, Zotero(config.zotero_url)).sync()
        for message in summary.messages:
            print(message, file=sys.stderr)
        print(
            f"同步完成：created={summary.created} skipped={summary.skipped} "
            f"conflicts={summary.conflicts} failed={summary.failed} "
            f"pdf_linked={summary.pdf_linked} pdf_missing={summary.pdf_missing} "
            f"pdf_failed={summary.pdf_failed}"
        )
        return 0 if summary.successful else 1
    except (PipelineError, OSError, ValueError, TypeError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已停止。", file=sys.stderr)
        return 130
