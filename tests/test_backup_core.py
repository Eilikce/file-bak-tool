"""
flatbak 核心单元测试
"""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from src.backup_core import (
    sha256_file,
    generate_dst_name,
    generate_dst_name_with_counter,
    load_meta,
    write_meta,
    append_log,
    build_target_index,
    resolve_conflict,
    FlatBak,
    META_FILENAME,
    LOG_FILENAME,
    HASH_SHORT_LEN,
)


# ========== sha256_file ==========

def test_sha256_file(tmp_path):
    f = tmp_path / "test.txt"
    content = b"hello world"
    f.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    assert sha256_file(f) == expected


def test_sha256_file_empty(tmp_path):
    f = tmp_path / "empty.txt"
    f.touch()
    expected = hashlib.sha256(b"").hexdigest()
    assert sha256_file(f) == expected


def test_sha256_file_large(tmp_path):
    f = tmp_path / "large.bin"
    content = os.urandom(1024 * 1024)  # 1MB
    f.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    assert sha256_file(f) == expected


# ========== generate_dst_name ==========

def test_generate_dst_name_basic():
    name = generate_dst_name("readme", ".md", "a" * 64)
    assert name == f"readme_{'a' * HASH_SHORT_LEN}.md"


def test_generate_dst_name_no_ext():
    name = generate_dst_name("Makefile", "", "b" * 64)
    assert name == f"Makefile_{'b' * HASH_SHORT_LEN}"


def test_generate_dst_name_with_counter():
    name = generate_dst_name_with_counter("file", ".txt", "c" * 64, 3)
    assert name == f"file_{'c' * HASH_SHORT_LEN}_3.txt"


# ========== load_meta / write_meta ==========

def test_load_meta_not_exists(tmp_path):
    assert load_meta(tmp_path) == {"entries": []}


def test_load_meta_exists(tmp_path):
    data = {"entries": [{"dst_name": "a.txt", "sha256": "x"}]}
    meta_file = tmp_path / META_FILENAME
    meta_file.write_text(json.dumps(data), encoding="utf-8")
    assert load_meta(tmp_path) == data


def test_write_meta(tmp_path):
    data = {"entries": [{"dst_name": "b.txt", "sha256": "y"}]}
    write_meta(tmp_path, data)
    meta_file = tmp_path / META_FILENAME
    assert meta_file.exists()
    loaded = json.loads(meta_file.read_text(encoding="utf-8"))
    assert loaded == data


# ========== append_log ==========

def test_append_log(tmp_path):
    append_log(tmp_path, "test message")
    log_file = tmp_path / LOG_FILENAME
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "test message" in content


def test_append_log_multiple(tmp_path):
    append_log(tmp_path, "msg1")
    append_log(tmp_path, "msg2")
    log_file = tmp_path / LOG_FILENAME
    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2


# ========== build_target_index ==========

def test_build_target_index_empty():
    assert build_target_index(Path("/tmp"), {"entries": []}) == {}


def test_build_target_index_normal():
    meta = {
        "entries": [
            {"dst_name": "a.txt", "sha256": "aaa"},
            {"dst_name": "b.md", "sha256": "bbb"},
        ]
    }
    idx = build_target_index(Path("/tmp"), meta)
    assert idx == {"a.txt": "aaa", "b.md": "bbb"}


# ========== resolve_conflict ==========

def test_resolve_conflict_no_conflict():
    result = resolve_conflict("readme", ".md", "a" * 64, {})
    assert result == f"readme_{'a' * HASH_SHORT_LEN}.md"


def test_resolve_conflict_same_content():
    name_to_hash = {f"readme_{'a' * HASH_SHORT_LEN}.md": "a" * 64}
    result = resolve_conflict("readme", ".md", "a" * 64, name_to_hash)
    assert result is None


def test_resolve_conflict_diff_content():
    name_to_hash = {f"readme_{'b' * HASH_SHORT_LEN}.md": "b" * 64}
    result = resolve_conflict("readme", ".md", "a" * 64, name_to_hash)
    expected = f"readme_{'a' * HASH_SHORT_LEN}.md"
    assert result == expected


def test_resolve_conflict_name_collision_then_rename():
    name_to_hash = {
        f"readme_{'a' * HASH_SHORT_LEN}.md": "b" * 64,  # diff content but same name
    }
    result = resolve_conflict("readme", ".md", "a" * 64, name_to_hash)
    expected = f"readme_{'a' * HASH_SHORT_LEN}_1.md"
    assert result == expected


def test_resolve_conflict_multiple_collisions():
    name_to_hash = {
        f"readme_{'a' * HASH_SHORT_LEN}.md": "b" * 64,
        f"readme_{'a' * HASH_SHORT_LEN}_1.md": "c" * 64,
    }
    result = resolve_conflict("readme", ".md", "a" * 64, name_to_hash)
    expected = f"readme_{'a' * HASH_SHORT_LEN}_2.md"
    assert result == expected


def test_resolve_conflict_collision_same_content_countered():
    name_to_hash = {
        f"readme_{'a' * HASH_SHORT_LEN}.md": "b" * 64,
        f"readme_{'a' * HASH_SHORT_LEN}_1.md": "a" * 64,  # already has same content
    }
    result = resolve_conflict("readme", ".md", "a" * 64, name_to_hash)
    assert result is None


def test_resolve_conflict_no_ext():
    result = resolve_conflict("Makefile", "", "d" * 64, {})
    assert result == f"Makefile_{'d' * HASH_SHORT_LEN}"


# ========== FlatBak integration ==========

def _create_file(directory, rel_path, content):
    p = directory / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def test_flatbak_basic_backup(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "a.txt", "hello")
    _create_file(src, "sub/b.txt", "world")

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    assert count == 2

    dst_files = list(dst.iterdir())
    meta_file = dst / META_FILENAME
    assert meta_file.exists()
    assert len(dst_files) >= 3  # 2 files + meta


def test_flatbak_dedup_same_content(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "a.txt", "same content")
    _create_file(src, "sub/b.txt", "same content")

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    assert count == 2  # same content different names

    # run again
    count2 = bak.run(str(src), str(dst))
    assert count2 == 0  # nothing new


def test_flatbak_dedup_same_name_same_content(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "a.txt", "hello")
    _create_file(src, "sub/a.txt", "hello")  # same name, same content

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    # Only one copy since same name + same content
    assert count == 1


def test_flatbak_rename_on_conflict(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "a.txt", "version1")
    _create_file(src, "sub/a.txt", "version2")  # same name, diff content

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    # Should have 2 files in target (one renamed)
    assert count == 2

    dst_files = [f.name for f in dst.iterdir() if f.is_file() and not f.name.startswith(".flatbak")]
    assert len(dst_files) == 2


def test_flatbak_incremental(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "a.txt", "first")

    bak = FlatBak()
    count1 = bak.run(str(src), str(dst))
    assert count1 == 1

    # Add new file
    _create_file(src, "b.txt", "second")
    count2 = bak.run(str(src), str(dst))
    assert count2 == 1  # only new file copied

    # No change
    count3 = bak.run(str(src), str(dst))
    assert count3 == 0


def test_flatbak_subdir_flatten(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "level1/a.txt", "one")
    _create_file(src, "level1/level2/b.txt", "two")
    _create_file(src, "x.txt", "three")

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    assert count == 3

    # all files flat in target
    dst_file_count = sum(1 for f in dst.iterdir() if f.is_file() and not f.name.startswith(".flatbak"))
    assert dst_file_count == 3


def test_flatbak_empty_source(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    src.mkdir()

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    assert count == 0


def test_flatbak_cancel(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    for i in range(100):
        _create_file(src, f"f{i}.txt", f"content{i}")

    bak = FlatBak()
    import threading
    timer = threading.Timer(0.01, bak.cancel)
    timer.start()
    count = bak.run(str(src), str(dst))
    # should have cancelled before copying all
    assert count < 100


def test_flatbak_meta_persists(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "a.txt", "persist")

    bak = FlatBak()
    bak.run(str(src), str(dst))

    meta = load_meta(dst)
    assert len(meta["entries"]) == 1
    assert meta["entries"][0]["dst_name"].startswith("a_")


def test_flatbak_log_file_created(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "a.txt", "log test")

    bak = FlatBak()
    bak.run(str(src), str(dst))

    log_file = dst / LOG_FILENAME
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "已复制" in content or "备份完成" in content
