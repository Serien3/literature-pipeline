"""Explicit, quota-conscious orchestration for selected PDF conversions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .files import PipelineError, PdfConversionLock, VaultLock
from .library import Config, ExistingIndex, index_existing
from .pdf2md import ConversionOptions, convert_pdf_into_paper
from .pdf_links import AvailablePdf, PdfLinker
from .zotero import Zotero, key


@dataclass(frozen=True)
class ConversionCandidate:
    item_key: str
    paper_folder: Path
    status: str
    detail: str
    pdf: AvailablePdf | None = None


@dataclass
class ConversionSummary:
    selected: int = 0
    converted: int = 0
    skipped: int = 0
    failed: int = 0
    messages: list[str] = field(default_factory=list)

    @property
    def successful(self) -> bool:
        return self.failed == 0


class ConversionService:
    def __init__(self, vault: Path, config: Config, zotero: Zotero):
        self.vault = vault
        self.config = config
        self.pdf_linker = PdfLinker(zotero)

    def _index(self) -> ExistingIndex:
        with VaultLock(self.vault):
            return index_existing(self.vault)

    def inspect(self, item_key: str, folder: Path) -> ConversionCandidate:
        full_markdown = folder / "full.md"
        if full_markdown.is_file() and not full_markdown.is_symlink():
            return ConversionCandidate(item_key, folder, "Converted", "full.md 已存在")
        if full_markdown.exists() or full_markdown.is_symlink():
            return ConversionCandidate(item_key, folder, "Conflict", "full.md 不是普通文件")
        occupied = [
            name
            for name in ("images", "temp")
            if (folder / name).exists() or (folder / name).is_symlink()
        ]
        if occupied:
            return ConversionCandidate(
                item_key,
                folder,
                "Conflict",
                "已有转换目标：" + "、".join(occupied),
            )
        try:
            count, available = self.pdf_linker.conversion_pdf(folder, item_key)
        except (PipelineError, OSError, UnicodeError, ValueError, TypeError) as error:
            return ConversionCandidate(item_key, folder, "Unavailable", str(error))
        if count == 0:
            return ConversionCandidate(item_key, folder, "No PDF", "Zotero 中没有 PDF 附件")
        if count > 1:
            return ConversionCandidate(
                item_key,
                folder,
                "Multiple",
                f"Zotero 中有 {count} 个 PDF 附件",
            )
        if available is None:
            return ConversionCandidate(item_key, folder, "Unavailable", "唯一 PDF 不可用")
        return ConversionCandidate(item_key, folder, "Ready", "可以转换", available)

    def list_candidates(self) -> list[ConversionCandidate]:
        index = self._index()
        conflicts = set(index.conflicts)
        candidates: list[ConversionCandidate] = []
        for item_key, paths in sorted(index.complete.items()):
            folder = paths[0].parent
            if item_key in conflicts:
                candidates.append(
                    ConversionCandidate(item_key, folder, "Conflict", "多个论文目录声明同一 key")
                )
            else:
                candidates.append(self.inspect(item_key, folder))
        return candidates

    def convert_selected(self, requested_keys: list[str], token: str) -> ConversionSummary:
        index = self._index()
        summary = ConversionSummary()
        unique_keys: list[str] = []
        seen: set[str] = set()
        for value in requested_keys:
            summary.selected += 1
            try:
                item_key = key(value)
            except PipelineError as error:
                summary.failed += 1
                summary.messages.append(f"无效论文 key {value!r}：{error}")
                continue
            if item_key in seen:
                summary.skipped += 1
                summary.messages.append(f"论文 {item_key} 重复选择，已跳过")
                continue
            seen.add(item_key)
            unique_keys.append(item_key)

        conflicts = set(index.conflicts)
        for item_key in unique_keys:
            if item_key in conflicts:
                summary.failed += 1
                summary.messages.append(f"论文 {item_key} 有多个本地目录声明，无法转换")
                continue
            paths = index.complete.get(item_key, ())
            if not paths:
                summary.failed += 1
                summary.messages.append(f"论文 {item_key} 尚未完成入库")
                continue
            folder = paths[0].parent
            try:
                with PdfConversionLock(self.vault, item_key):
                    candidate = self.inspect(item_key, folder)
                    if candidate.status == "Converted":
                        summary.skipped += 1
                        summary.messages.append(f"论文 {item_key} 已有 full.md，未调用 MinerU")
                        continue
                    if candidate.status != "Ready" or candidate.pdf is None:
                        raise PipelineError(f"{candidate.status}：{candidate.detail}")
                    options = ConversionOptions(
                        pdf=candidate.pdf.path,
                        output_root=folder,
                        token=token,
                        model=self.config.pdf2md.model,
                        language=self.config.pdf2md.language,
                        ocr=self.config.pdf2md.ocr,
                        timeout=self.config.pdf2md.timeout,
                    )
                    convert_pdf_into_paper(options, folder)
                summary.converted += 1
            except (PipelineError, OSError, UnicodeError, ValueError, TypeError) as error:
                summary.failed += 1
                summary.messages.append(f"论文 {item_key} 转换失败：{error}")
        return summary
