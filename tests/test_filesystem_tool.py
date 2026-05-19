from __future__ import annotations

from pathlib import Path

import pytest

from aiagent.tools.filesystem import (
    create_dir,
    delete_file,
    list_dir,
    read_file,
    rename_file,
    write_file,
    _resolve_in_dir,
)


class TestResolveInDir:
    def test_path_within_base_is_allowed(self, tmp_path: Path) -> None:
        target = _resolve_in_dir(str(tmp_path), "test.txt")
        assert target == tmp_path / "test.txt"

    def test_path_escape_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="escapes"):
            _resolve_in_dir(str(tmp_path), "../outside.txt")


class TestWriteAndReadFile:
    def test_write_and_read_roundtrip(self, tmp_path: Path) -> None:
        write_result = write_file(str(tmp_path), "hello.txt", "Hello, world!")
        assert Path(write_result["path"]).exists()

        read_result = read_file(str(tmp_path), "hello.txt")
        assert read_result["content"] == "Hello, world!"

    def test_append_mode(self, tmp_path: Path) -> None:
        write_file(str(tmp_path), "log.txt", "line1\n", append=False)
        write_file(str(tmp_path), "log.txt", "line2\n", append=True)

        result = read_file(str(tmp_path), "log.txt")
        assert result["content"] == "line1\nline2\n"

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        write_result = write_file(str(tmp_path / "sub" / "deep"), "file.txt", "data")
        assert Path(write_result["path"]).exists()


class TestListDir:
    def test_lists_files_and_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "sub").mkdir()
        result = list_dir(str(tmp_path))
        assert result["directory"] == str(tmp_path)
        names = [item["name"] for item in result["items"]]
        assert "a.txt" in names
        assert "sub" in names

    def test_nonexistent_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            list_dir(str(tmp_path / "nope"))


class TestRenameFile:
    def test_rename_success(self, tmp_path: Path) -> None:
        (tmp_path / "old.txt").write_text("x")
        result = rename_file(str(tmp_path), "old.txt", "new.txt")
        assert Path(result["to"]).exists()
        assert not Path(result["from"]).exists()

    def test_source_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            rename_file(str(tmp_path), "missing.txt", "new.txt")


class TestDeleteFile:
    def test_delete_success(self, tmp_path: Path) -> None:
        (tmp_path / "remove.txt").write_text("x")
        result = delete_file(str(tmp_path), "remove.txt")
        assert not Path(result["deleted"]).exists()

    def test_delete_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            delete_file(str(tmp_path), "missing.txt")


class TestCreateDir:
    def test_create_directory(self, tmp_path: Path) -> None:
        result = create_dir(str(tmp_path), "newdir")
        assert Path(result["path"]).is_dir()

    def test_create_nested(self, tmp_path: Path) -> None:
        result = create_dir(str(tmp_path), "a/b/c")
        assert Path(result["path"]).is_dir()
