"""Configuration and local-vault indexing for import-once metadata."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .files import PipelineError, atomic_create, read_meta, read_zotero_json
from .zotero import key, validate_url


@dataclass(frozen=True)
class Config:
    collection: str
    zotero_url: str


@dataclass(frozen=True)
class ExistingIndex:
    complete: dict[str, tuple[Path, ...]]
    partial: dict[str, tuple[Path, ...]]

    @property
    def keys(self) -> set[str]:
        return set(self.complete)

    @property
    def conflicts(self) -> dict[str, tuple[Path, ...]]:
        declarations: dict[str, tuple[Path, ...]] = {}
        for item_key in self.complete.keys() | self.partial.keys():
            paths = self.complete.get(item_key, ()) + self.partial.get(item_key, ())
            if len(paths) > 1:
                declarations[item_key] = paths
        return declarations


def initialize(vault: Path, collection: str, zotero_url: str) -> None:
    collection = key(collection)
    zotero_url = validate_url(zotero_url)
    vault.mkdir(parents=True, exist_ok=True)
    if vault.is_symlink() or not vault.is_dir():
        raise PipelineError(f"vault 不是普通目录：{vault}")
    path = vault / ".pipeline" / "config.toml"
    content = f"collection = {json.dumps(collection)}\nzotero_url = {json.dumps(zotero_url)}\n"
    try:
        atomic_create(path, content)
    except FileExistsError as error:
        raise PipelineError(f"配置已存在，初始化不会覆盖：{path}") from error


def load_config(vault: Path) -> Config:
    path = vault / ".pipeline" / "config.toml"
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PipelineError(f"无法读取配置，请先 init：{path}") from error
    expected = {"collection", "zotero_url"}
    if set(config) != expected:
        raise PipelineError("配置只能包含 collection 和 zotero_url")
    collection = key(config.get("collection", ""))
    zotero_url = config.get("zotero_url")
    if not isinstance(zotero_url, str):
        raise PipelineError("zotero_url 必须是字符串")
    validate_url(zotero_url)
    return Config(collection=collection, zotero_url=zotero_url)


def index_existing(vault: Path) -> ExistingIndex:
    """Index complete and interrupted imports in direct-child folders."""
    complete: dict[str, list[Path]] = {}
    partial: dict[str, list[Path]] = {}
    try:
        children = list(vault.iterdir())
    except OSError as error:
        raise PipelineError(f"无法扫描 vault：{vault}") from error
    for folder in children:
        if folder.is_symlink() or not folder.is_dir():
            continue
        meta_path = folder / "meta.md"
        sidecar_path = folder / "zotero-item.json"
        if meta_path.exists() or meta_path.is_symlink():
            fields = read_meta(meta_path)
            item_key = fields.get("key")
            path = meta_path
            destination = complete
        elif sidecar_path.exists() or sidecar_path.is_symlink():
            fields = read_zotero_json(sidecar_path)
            item_key = fields.get("key")
            path = sidecar_path
            destination = partial
        else:
            continue
        if not isinstance(item_key, str):
            raise PipelineError(f"已有元数据文件缺少 Zotero 字符串 key：{path}")
        try:
            item_key = key(item_key)
        except PipelineError as error:
            raise PipelineError(f"已有元数据文件的 Zotero key 无效：{path}") from error
        destination.setdefault(item_key, []).append(path)
    return ExistingIndex(
        {item_key: tuple(paths) for item_key, paths in complete.items()},
        {item_key: tuple(paths) for item_key, paths in partial.items()},
    )
