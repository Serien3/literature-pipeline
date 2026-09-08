from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

from literature_pipeline.cli import main
from literature_pipeline.files import (
    PipelineError,
    VaultLock,
    atomic_create,
    paper_folder_name,
    project_meta,
    read_meta,
    read_zotero_json,
    render_meta,
    render_zotero_json,
)
from literature_pipeline.ingest import Importer
from literature_pipeline.library import Config, index_existing, initialize, load_config
from literature_pipeline.pdf_links import PdfLinker, file_uri_path, pdf_link_name
from literature_pipeline.zotero import Zotero, key, validate_url


def item(item_key: str = "PAPER001", *, title: str = "中文论文：测试", doi: str = "10.1234/example") -> dict:
    data = {
        "key": item_key,
        "version": 1,
        "itemType": "journalArticle",
        "title": title,
        "creators": [
            {"creatorType": "author", "firstName": "A", "lastName": "Researcher"},
            {"creatorType": "editor", "name": "Example Institute"},
        ],
        "abstractNote": "",
        "publicationTitle": "Example Journal",
        "volume": "",
        "issue": "001",
        "date": "2025-01-02",
        "DOI": doi,
        "accepted": False,
        "missing": None,
        "tags": [{"tag": "zotero-tag", "type": 1}],
        "collections": ["COLLECT1"],
        "relations": {"dc:relation": ["x", "y"]},
        "dateAdded": "2026-09-08T10:00:00Z",
        "dateModified": "2026-09-08T10:00:00Z",
        "futureField": {"nested": [1, 1.5, True, None]},
    }
    return {"key": item_key, "version": 1, "data": data}


def item_folder(vault: Path, entry: dict | None = None) -> Path:
    entry = item() if entry is None else entry
    return vault / paper_folder_name(entry["data"]["key"], entry["data"])


class FakeZotero:
    def __init__(
        self,
        entries: list[dict] | None = None,
        children: dict[str, list[dict]] | None = None,
        file_urls: dict[str, str] | None = None,
    ):
        self.entries = [item()] if entries is None else entries
        self.children_by_parent = {} if children is None else children
        self.file_urls = {} if file_urls is None else file_urls

    def items(self, _collection: str) -> list[dict]:
        return self.entries

    def children(self, parent_key: str) -> list[dict]:
        return self.children_by_parent.get(parent_key, [])

    def attachment_file_url(self, attachment_key: str) -> str:
        return self.file_urls[attachment_key]


def pdf_attachment(
    attachment_key: str,
    parent_key: str = "PAPER001",
    filename: str = "paper.pdf",
) -> dict:
    data = {
        "key": attachment_key,
        "version": 1,
        "itemType": "attachment",
        "parentItem": parent_key,
        "linkMode": "imported_file",
        "title": "PDF",
        "contentType": "application/pdf",
        "filename": filename,
    }
    return {"key": attachment_key, "version": 1, "data": data}


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name) / "论文 vault"
        self.vault.mkdir()
        self.config = Config("COLLECT1", "http://localhost:23119/api/")

    def sync(self, entries: list[dict] | None = None):
        return Importer(self.vault, self.config, FakeZotero(entries)).sync()

    def test_complete_data_is_written_directly_under_vault(self):
        source = item()
        summary = self.sync([source])
        folder = item_folder(self.vault, source)
        path = folder / "meta.md"
        sidecar = folder / "zotero-item.json"
        self.assertEqual(summary.created, 1)
        self.assertTrue(path.is_file())
        self.assertTrue(sidecar.is_file())
        self.assertEqual(folder.name, "中文论文：测试 [PAPER001]")
        self.assertFalse((self.vault / "papers").exists())
        self.assertEqual(read_zotero_json(sidecar), source["data"])
        self.assertEqual(read_meta(path), project_meta(source["data"]))
        self.assertEqual(read_meta(path)["creators"], ["A Researcher", "Example Institute"])
        self.assertEqual(read_meta(path)["zoteroTags"], ["zotero-tag"])
        self.assertNotIn("tags", read_meta(path))
        self.assertEqual(read_meta(path)["relations"], source["data"]["relations"])
        self.assertEqual(path.read_text(encoding="utf-8").count("---"), 2)

    def test_render_preserves_empty_nested_unknown_and_string_types(self):
        data = item()["data"] | {
            "emptyList": [], "emptyObject": {}, "emptyString": "",
            "yesText": "yes", "numberText": "00123", "colonText": "a: b",
            "separatorText": "first line\n---\nlast line",
        }
        rendered = render_meta(data)
        loaded = yaml.safe_load(rendered[4:rendered.rfind("\n---\n")])
        expected = project_meta(data)
        self.assertEqual(loaded, expected)
        for name in ("date", "dateAdded", "yesText", "numberText", "colonText"):
            self.assertIs(type(loaded[name]), str)
        self.assertIs(type(loaded["accepted"]), bool)
        self.assertIsNone(loaded["missing"])

        path = self.vault / "with separator" / "meta.md"
        path.parent.mkdir()
        path.write_text(rendered, encoding="utf-8")
        self.assertEqual(read_meta(path), expected)

    def test_zotero_json_roundtrip_preserves_complete_data(self):
        data = item()["data"] | {
            "emptyList": [], "emptyObject": {}, "emptyString": "", "unicode": "论文",
        }
        path = self.vault / "PAPER001" / "zotero-item.json"
        path.parent.mkdir()
        path.write_text(render_zotero_json(data), encoding="utf-8")
        self.assertEqual(read_zotero_json(path), data)

    def test_sparse_short_title_is_not_synthesized(self):
        without = item("PAPER001")
        with_short = item("PAPER002")
        with_short["data"]["shortTitle"] = "A short title"
        summary = self.sync([without, with_short])
        self.assertEqual(summary.created, 2)
        self.assertNotIn("shortTitle", read_meta(item_folder(self.vault, without) / "meta.md"))
        self.assertEqual(
            read_meta(item_folder(self.vault, with_short) / "meta.md")["shortTitle"], "A short title"
        )
        self.assertEqual(item_folder(self.vault, with_short).name, "A short title [PAPER002]")

    def test_folder_name_falls_back_sanitizes_and_truncates(self):
        self.assertEqual(
            paper_folder_name("PAPER001", {"shortTitle": "  ", "title": "  A:\tB / C? .  "}),
            "A - B - C [PAPER001]",
        )
        self.assertEqual(
            paper_folder_name("PAPER001", {"title": 'A<>:"/\\|?*B'}),
            "A - B [PAPER001]",
        )
        self.assertEqual(paper_folder_name("PAPER001", {"title": ""}), "PAPER001")
        self.assertEqual(paper_folder_name("PAPER001", {}), "PAPER001")
        long_name = paper_folder_name("PAPER001", {"title": "文" * 120})
        self.assertEqual(long_name, f"{'文' * 100} [PAPER001]")
        with self.assertRaises(PipelineError):
            paper_folder_name("PAPER001", {"shortTitle": 123, "title": "fallback"})
        with self.assertRaises(PipelineError):
            paper_folder_name("PAPER001", {"shortTitle": "valid", "title": 123})

    def test_creator_and_tag_projection_preserves_display_values(self):
        entry = item()
        entry["data"]["creators"] = [
            {"creatorType": "author", "firstName": "Ada", "lastName": "Lovelace"},
            {"creatorType": "author", "name": "研究机构"},
        ]
        entry["data"]["tags"] = [
            {"tag": "machine learning", "type": 1},
            {"tag": "ML", "type": 0},
            {"tag": "machine learning", "type": 1},
        ]
        self.sync([entry])
        folder = item_folder(self.vault, entry)
        meta = read_meta(folder / "meta.md")
        self.assertEqual(meta["creators"], ["Ada Lovelace", "研究机构"])
        self.assertEqual(meta["zoteroTags"], ["machine learning", "ML", "machine learning"])
        self.assertNotIn("tags", meta)
        self.assertEqual(
            read_zotero_json(folder / "zotero-item.json"), entry["data"]
        )

    def test_repeat_sync_never_changes_existing_meta(self):
        self.sync()
        folder = item_folder(self.vault)
        path = folder / "meta.md"
        sidecar = folder / "zotero-item.json"
        edited_meta = path.read_bytes() + b"user body\n"
        original_json = sidecar.read_bytes()
        path.write_bytes(edited_meta)
        changed = item(title="Zotero changed the title")
        summary = self.sync([changed])
        self.assertEqual(summary.skipped, 1)
        self.assertEqual(path.read_bytes(), edited_meta)
        self.assertEqual(sidecar.read_bytes(), original_json)

    def test_completed_item_does_not_read_edited_sidecar(self):
        self.sync()
        folder = item_folder(self.vault)
        (folder / "zotero-item.json").write_text("not json", encoding="utf-8")
        summary = self.sync()
        self.assertEqual(summary.skipped, 1)
        self.assertEqual(summary.failed, 0)
        self.assertEqual((folder / "zotero-item.json").read_text(encoding="utf-8"), "not json")

    def test_existing_meta_without_sidecar_is_skipped_without_backfill(self):
        folder = self.vault / "renamed"
        folder.mkdir()
        meta = folder / "meta.md"
        meta.write_text(render_meta(item()["data"]), encoding="utf-8")
        summary = self.sync()
        self.assertEqual(summary.skipped, 1)
        self.assertFalse((folder / "zotero-item.json").exists())

    def test_existing_target_meta_with_another_key_gets_no_sidecar(self):
        folder = item_folder(self.vault)
        folder.mkdir()
        (folder / "meta.md").write_text(render_meta(item("OTHER001")["data"]), encoding="utf-8")
        summary = self.sync()
        self.assertEqual(summary.skipped, 1)
        self.assertFalse((folder / "zotero-item.json").exists())

    def test_sidecar_only_interrupted_import_recovers_from_saved_snapshot(self):
        original = item(title="original snapshot")["data"]
        folder = self.vault / paper_folder_name("PAPER001", original)
        folder.mkdir()
        sidecar = folder / "zotero-item.json"
        atomic_create(sidecar, render_zotero_json(original))
        original_bytes = sidecar.read_bytes()

        summary = self.sync([item(title="later Zotero value")])

        self.assertEqual(summary.created, 1)
        self.assertEqual(read_meta(folder / "meta.md"), project_meta(original))
        self.assertEqual(sidecar.read_bytes(), original_bytes)
        self.assertFalse(item_folder(self.vault, item(title="later Zotero value")).exists())

    def test_invalid_existing_sidecar_does_not_create_meta(self):
        folder = self.vault / "PAPER001"
        folder.mkdir()
        (folder / "zotero-item.json").write_text('{"key":"PAPER001","itemType":42}', encoding="utf-8")
        summary = self.sync()
        self.assertEqual(summary.failed, 1)
        self.assertFalse((folder / "meta.md").exists())

    def test_invalid_creator_or_tag_does_not_publish_partial_item(self):
        for field, invalid in (("creators", [{"creatorType": "author"}]), ("tags", [{"type": 1}])):
            with self.subTest(field=field):
                entry = item()
                entry["data"][field] = invalid
                summary = self.sync([entry])
                self.assertEqual(summary.failed, 1)
                self.assertFalse(item_folder(self.vault, entry).exists())

    def test_renamed_direct_child_folder_is_still_recognized(self):
        self.sync()
        item_folder(self.vault).rename(self.vault / "my paper")
        summary = self.sync()
        self.assertEqual(summary.skipped, 1)
        self.assertFalse(item_folder(self.vault).exists())

    def test_same_doi_with_different_keys_is_imported_twice(self):
        first, second = item("PAPER001"), item("PAPER002")
        summary = self.sync([first, second])
        self.assertEqual(summary.created, 2)
        self.assertTrue((item_folder(self.vault, first) / "meta.md").is_file())
        self.assertTrue((item_folder(self.vault, second) / "meta.md").is_file())
        self.assertNotEqual(item_folder(self.vault, first), item_folder(self.vault, second))

    def test_existing_key_named_folder_is_not_migrated(self):
        folder = self.vault / "PAPER001"
        folder.mkdir()
        (folder / "meta.md").write_text(render_meta(item()["data"]), encoding="utf-8")
        summary = self.sync()
        self.assertEqual(summary.skipped, 1)
        self.assertTrue(folder.is_dir())
        self.assertFalse(item_folder(self.vault).exists())

    def test_duplicate_partial_sidecars_are_a_conflict(self):
        for name in ("first [PAPER001]", "second [PAPER001]"):
            folder = self.vault / name
            folder.mkdir()
            (folder / "zotero-item.json").write_text(
                render_zotero_json(item()["data"]), encoding="utf-8"
            )
        summary = self.sync()
        self.assertEqual(summary.conflicts, 1)
        self.assertEqual(summary.created, 0)
        self.assertFalse(any(self.vault.glob("*/meta.md")))

    def test_removed_or_changed_zotero_item_has_no_local_effect(self):
        self.sync()
        path = item_folder(self.vault) / "meta.md"
        original = path.read_bytes()
        self.sync([])
        self.sync([item(title="changed")])
        self.assertEqual(path.read_bytes(), original)

    def test_invalid_item_does_not_block_another_item(self):
        bad = item("PAPER001")
        bad["data"]["key"] = "MISMATCH"
        summary = self.sync([bad, item("PAPER002")])
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.created, 1)
        self.assertTrue((item_folder(self.vault, item("PAPER002")) / "meta.md").is_file())

    def test_invalid_title_type_does_not_block_another_item(self):
        bad = item("PAPER001")
        bad["data"]["shortTitle"] = 42
        good = item("PAPER002")
        summary = self.sync([bad, good])
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.created, 1)
        self.assertTrue((item_folder(self.vault, good) / "meta.md").is_file())

    def test_duplicate_api_key_is_a_conflict_and_not_published(self):
        summary = self.sync([item(), item(title="other")])
        self.assertEqual(summary.conflicts, 1)
        self.assertFalse(item_folder(self.vault).exists())

    def test_duplicate_local_key_is_reported_without_overwrite(self):
        for folder in ("first", "second"):
            path = self.vault / folder / "meta.md"
            path.parent.mkdir()
            path.write_text(render_meta(item()["data"]), encoding="utf-8")
        summary = self.sync()
        self.assertEqual(summary.conflicts, 1)
        self.assertFalse(item_folder(self.vault).exists())

    def test_malformed_existing_meta_aborts_before_writes(self):
        bad = self.vault / "bad" / "meta.md"
        bad.parent.mkdir()
        bad.write_text("---\nnot: [closed\n", encoding="utf-8")
        with self.assertRaises(PipelineError):
            self.sync([item("PAPER002")])
        self.assertFalse(item_folder(self.vault, item("PAPER002")).exists())

    def test_existing_folder_contents_are_preserved(self):
        folder = item_folder(self.vault)
        folder.mkdir()
        marker = folder / "my-note.txt"
        marker.write_text("keep", encoding="utf-8")
        summary = self.sync()
        self.assertEqual(summary.created, 1)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
        self.assertTrue((folder / "meta.md").is_file())
        self.assertTrue((folder / "zotero-item.json").is_file())

    def test_nested_meta_is_not_indexed(self):
        nested = self.vault / "group" / "PAPER001" / "meta.md"
        nested.parent.mkdir(parents=True)
        nested.write_text(render_meta(item()["data"]), encoding="utf-8")
        summary = self.sync()
        self.assertEqual(summary.created, 1)
        self.assertTrue((item_folder(self.vault) / "meta.md").is_file())

    def test_non_paper_directories_are_untouched(self):
        obsidian = self.vault / ".obsidian"
        obsidian.mkdir()
        settings = obsidian / "app.json"
        settings.write_text("{}", encoding="utf-8")
        self.sync()
        self.assertEqual(settings.read_text(encoding="utf-8"), "{}")

    def test_attachment_note_and_annotation_are_skipped(self):
        entries = []
        for number, item_type in enumerate(("attachment", "note", "annotation"), start=1):
            entry = item(f"SKIP000{number}")
            entry["data"]["itemType"] = item_type
            entries.append(entry)
        summary = self.sync(entries)
        self.assertEqual(summary.skipped, 3)
        self.assertEqual(list(self.vault.iterdir()), [])

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks unavailable")
    def test_symlink_paper_directory_is_never_followed(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        marker = outside / "zotero-item.json"
        marker.write_text(render_zotero_json(item()["data"]), encoding="utf-8")
        original = marker.read_bytes()
        item_folder(self.vault).symlink_to(outside, target_is_directory=True)
        summary = self.sync()
        self.assertEqual(summary.failed, 1)
        self.assertFalse((outside / "meta.md").exists())
        self.assertEqual(marker.read_bytes(), original)


@unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks unavailable")
class PdfLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        self.config = Config("COLLECT1", "http://localhost:23119/api/")

    def source(self, name: str, content: bytes = b"%PDF-test") -> Path:
        path = self.root / "zotero" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
        return path

    def test_sync_links_all_pdfs_without_copying(self):
        first = self.source("main.pdf", b"%PDF-main")
        second = self.source("supp.pdf", b"%PDF-supplement")
        children = [
            pdf_attachment("PDFKEY01", filename="Main: Paper.pdf"),
            pdf_attachment("PDFKEY02", filename="Supplement.pdf"),
        ]
        zotero = FakeZotero(
            [item()],
            {"PAPER001": children},
            {"PDFKEY01": first.as_uri(), "PDFKEY02": second.as_uri()},
        )
        summary = Importer(self.vault, self.config, zotero).sync()
        folder = item_folder(self.vault)
        main = folder / "Main - Paper [PDFKEY01].pdf"
        supplement = folder / "Supplement [PDFKEY02].pdf"
        self.assertEqual(summary.created, 1)
        self.assertEqual(summary.pdf_linked, 2)
        self.assertTrue(main.is_symlink())
        self.assertTrue(supplement.is_symlink())
        self.assertEqual(main.resolve(), first.resolve())
        self.assertEqual(supplement.resolve(), second.resolve())
        self.assertEqual(first.read_bytes(), b"%PDF-main")

    def test_missing_pdf_does_not_block_metadata(self):
        summary = Importer(self.vault, self.config, FakeZotero([item()])).sync()
        folder = item_folder(self.vault)
        self.assertEqual(summary.created, 1)
        self.assertEqual(summary.pdf_missing, 1)
        self.assertEqual(summary.pdf_failed, 0)
        self.assertTrue((folder / "meta.md").is_file())
        self.assertTrue((folder / "zotero-item.json").is_file())

    def test_unavailable_pdf_reports_failure_after_metadata_success(self):
        missing = (self.root / "missing.pdf").as_uri()
        zotero = FakeZotero(
            [item()],
            {"PAPER001": [pdf_attachment("PDFKEY01")]},
            {"PDFKEY01": missing},
        )
        summary = Importer(self.vault, self.config, zotero).sync()
        self.assertEqual(summary.created, 1)
        self.assertEqual(summary.pdf_failed, 1)
        self.assertFalse(summary.successful)
        self.assertTrue((item_folder(self.vault) / "meta.md").is_file())

    def test_link_existing_repairs_target_and_filename(self):
        folder = self.vault / "renamed paper"
        folder.mkdir()
        (folder / "meta.md").write_text(render_meta(item()["data"]), encoding="utf-8")
        old = self.source("old.pdf")
        new = self.source("new.pdf")
        old_link = folder / "Old name [PDFKEY01].pdf"
        old_link.symlink_to(old)
        zotero = FakeZotero(
            [],
            {"PAPER001": [pdf_attachment("PDFKEY01", filename="New name.pdf")]},
            {"PDFKEY01": new.as_uri()},
        )
        summary = PdfLinker(zotero).link_existing(self.vault)
        repaired = folder / "New name [PDFKEY01].pdf"
        self.assertEqual(summary.papers, 1)
        self.assertEqual(summary.linked, 1)
        self.assertFalse(old_link.exists())
        self.assertTrue(repaired.is_symlink())
        self.assertEqual(repaired.resolve(), new.resolve())

        repeated = PdfLinker(zotero).link_existing(self.vault)
        self.assertEqual(repeated.unchanged, 1)
        self.assertEqual(repeated.linked, 0)

        new.unlink()
        replacement = self.source("replacement.pdf")
        zotero.file_urls["PDFKEY01"] = replacement.as_uri()
        repaired_again = PdfLinker(zotero).link_existing(self.vault)
        self.assertEqual(repaired_again.linked, 1)
        self.assertEqual(repaired.resolve(), replacement.resolve())

    def test_ordinary_file_collision_is_preserved(self):
        folder = self.vault / "paper"
        folder.mkdir()
        (folder / "meta.md").write_text(render_meta(item()["data"]), encoding="utf-8")
        collision = folder / "paper [PDFKEY01].pdf"
        collision.write_bytes(b"mine")
        source = self.source("source.pdf")
        zotero = FakeZotero(
            [],
            {"PAPER001": [pdf_attachment("PDFKEY01")]},
            {"PDFKEY01": source.as_uri()},
        )
        summary = PdfLinker(zotero).link_existing(self.vault)
        self.assertEqual(summary.conflicts, 1)
        self.assertEqual(collision.read_bytes(), b"mine")

    def test_uri_and_link_name_validation(self):
        source = self.source("论文 文件.pdf")
        self.assertEqual(file_uri_path(source.as_uri()), source.resolve())
        self.assertEqual(pdf_link_name("A/B?.PDF", "PDFKEY01"), "A - B [PDFKEY01].pdf")
        with self.assertRaises(PipelineError):
            file_uri_path("https://example.com/paper.pdf")

    def test_non_pdf_children_are_ignored(self):
        child = pdf_attachment("PDFKEY01", filename="snapshot.html")
        child["data"]["contentType"] = "text/html"
        zotero = FakeZotero([], {"PAPER001": [child]})
        folder = self.vault / "paper"
        folder.mkdir()
        summary = PdfLinker(zotero).link_paper(folder, "PAPER001")
        self.assertEqual(summary.missing, 1)
        self.assertEqual(summary.failed, 0)


class ConfigAndFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name) / "existing vault"
        self.vault.mkdir()

    def test_init_preserves_existing_vault_and_writes_minimal_config(self):
        existing = self.vault / "Home.md"
        existing.write_text("mine", encoding="utf-8")
        initialize(self.vault, "COLLECT1", "http://localhost:23119/api/")
        self.assertEqual(existing.read_text(encoding="utf-8"), "mine")
        self.assertEqual(load_config(self.vault), Config("COLLECT1", "http://localhost:23119/api/"))
        self.assertEqual(
            set(load_config(self.vault).__dict__), {"collection", "zotero_url"}
        )
        self.assertFalse((self.vault / "papers").exists())

    def test_init_never_overwrites_config(self):
        initialize(self.vault, "COLLECT1", "http://localhost:23119/api/")
        original = (self.vault / ".pipeline" / "config.toml").read_bytes()
        with self.assertRaises(PipelineError):
            initialize(self.vault, "COLLECT2", "http://localhost:23119/api/")
        self.assertEqual((self.vault / ".pipeline" / "config.toml").read_bytes(), original)

    def test_atomic_create_never_overwrites(self):
        path = self.vault / "meta.md"
        atomic_create(path, "first")
        with self.assertRaises(FileExistsError):
            atomic_create(path, "second")
        self.assertEqual(path.read_text(encoding="utf-8"), "first")

    def test_writer_lock_rejects_second_process(self):
        with VaultLock(self.vault):
            with self.assertRaises(PipelineError):
                with VaultLock(self.vault):
                    pass
        with VaultLock(self.vault):
            pass

    def test_index_only_reads_direct_children(self):
        direct = self.vault / "renamed" / "meta.md"
        direct.parent.mkdir()
        direct.write_text(render_meta(item()["data"]), encoding="utf-8")
        nested = self.vault / "group" / "nested" / "meta.md"
        nested.parent.mkdir(parents=True)
        nested.write_text(render_meta(item("PAPER002")["data"]), encoding="utf-8")
        self.assertEqual(index_existing(self.vault).keys, {"PAPER001"})

    def test_key_and_url_validation(self):
        self.assertEqual(key("ABCD1234"), "ABCD1234")
        self.assertEqual(validate_url("http://127.0.0.1:23119/api/"), "http://127.0.0.1:23119/api/")
        for value in ("bad", "../../xx", "abcd1234"):
            with self.subTest(value=value), self.assertRaises(PipelineError):
                key(value)
        for value in ("https://localhost/api/", "http://example.com/api/", "http://localhost/api/?token=x"):
            with self.subTest(value=value), self.assertRaises(PipelineError):
                validate_url(value)


class AdapterAndCliTests(unittest.TestCase):
    def test_list_paginates_and_rejects_inconsistent_snapshot(self):
        api = Zotero()

        def request(path):
            api.last_version = "1" if "start=0" in path else "2"
            return [{}] * 100 if "start=0" in path else []

        with patch.object(api, "request", side_effect=request):
            with self.assertRaises(PipelineError):
                api.listing("users/0/collections")

    def test_cli_sync_reports_summary_and_exit_code(self):
        with tempfile.TemporaryDirectory() as root:
            vault = Path(root) / "vault"
            initialize(vault, "COLLECT1", "http://localhost:23119/api/")
            output = io.StringIO()
            with patch("literature_pipeline.cli.Zotero", return_value=FakeZotero()), redirect_stdout(output):
                result = main(["sync", "--vault", str(vault)])
            self.assertEqual(result, 0)
            self.assertIn("created=1 skipped=0 conflicts=0 failed=0", output.getvalue())
            self.assertIn("pdf_linked=0 pdf_missing=1 pdf_failed=0", output.getvalue())

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks unavailable")
    def test_cli_link_pdfs_reports_summary(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            vault = root_path / "vault"
            initialize(vault, "COLLECT1", "http://localhost:23119/api/")
            folder = vault / "paper"
            folder.mkdir()
            (folder / "meta.md").write_text(render_meta(item()["data"]), encoding="utf-8")
            source = root_path / "source.pdf"
            source.write_bytes(b"%PDF")
            fake = FakeZotero(
                [],
                {"PAPER001": [pdf_attachment("PDFKEY01")]},
                {"PDFKEY01": source.as_uri()},
            )
            output = io.StringIO()
            with patch("literature_pipeline.cli.Zotero", return_value=fake), redirect_stdout(output):
                result = main(["link-pdfs", "--vault", str(vault)])
            self.assertEqual(result, 0)
            self.assertIn(
                "papers=1 linked=1 unchanged=0 missing=0 conflicts=0 failed=0",
                output.getvalue(),
            )
            self.assertTrue((folder / "paper [PDFKEY01].pdf").is_symlink())

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks unavailable")
    def test_doctor_checks_pdf_symlink_capability(self):
        with tempfile.TemporaryDirectory() as root:
            vault = Path(root) / "vault"
            initialize(vault, "COLLECT1", "http://localhost:23119/api/")
            output = io.StringIO()
            with patch("literature_pipeline.cli.Zotero", return_value=FakeZotero()), redirect_stdout(output):
                result = main(["doctor", "--vault", str(vault)])
            self.assertEqual(result, 0)
            self.assertIn("通过：PDF 符号链接", output.getvalue())

    def test_cli_has_no_removed_commands(self):
        for command in ("watch", "status", "convert", "select-pdf"):
            with self.subTest(command=command), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main([command])


if __name__ == "__main__":
    unittest.main()
