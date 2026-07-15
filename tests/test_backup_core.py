"""
flatbak 核心单元测试
"""

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from src.backup_core import (
    sha256_file,
    load_meta,
    write_meta,
    append_log,
    build_target_index,
    FlatBak,
    META_FILENAME,
    LOG_FILENAME,
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
    content = os.urandom(1024 * 1024)
    f.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    assert sha256_file(f) == expected


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
    names, hashes = build_target_index({"entries": []})
    assert names == {}
    assert hashes == {}


def test_build_target_index_normal():
    meta = {
        "entries": [
            {"dst_name": "a.txt", "sha256": "aaa"},
            {"dst_name": "b.md", "sha256": "bbb"},
        ]
    }
    names, hashes = build_target_index(meta)
    assert names == {"a.txt": "aaa", "b.md": "bbb"}
    assert hashes == {"aaa": "a.txt", "bbb": "b.md"}


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
    assert len(dst_files) >= 3


def test_flatbak_dedup_same_content(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "a.txt", "same content")
    _create_file(src, "sub/b.txt", "same content")

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    # a.txt copied, b.txt skipped because content already exists
    assert count == 1

    # run again
    count2 = bak.run(str(src), str(dst))
    assert count2 == 0  # nothing new


def test_flatbak_dedup_same_name_same_content(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "a.txt", "hello")
    _create_file(src, "sub/a.txt", "hello")

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    assert count == 1  # only one copy since same content


def test_flatbak_skip_name_conflict(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "IMG_001.jpg", "photo1 data")
    _create_file(src, "sub/IMG_001.jpg", "photo2 data")

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    assert count == 1  # second one skipped due to name conflict

    files = [f.name for f in dst.iterdir() if f.is_file() and not f.name.startswith(".flatbak")]
    assert len(files) == 1
    assert files[0] == "IMG_001.jpg"


def test_flatbak_same_content_across_names(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "a.txt", "hello")
    _create_file(src, "b.txt", "hello")

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    assert count == 1  # a.txt copied, b.txt has same content skipped

    # Add a file with new content
    _create_file(src, "c.txt", "world")
    count2 = bak.run(str(src), str(dst))
    assert count2 == 1  # c.txt has new content, copied


def test_flatbak_incremental(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "a.txt", "first")

    bak = FlatBak()
    count1 = bak.run(str(src), str(dst))
    assert count1 == 1

    _create_file(src, "b.txt", "second")
    count2 = bak.run(str(src), str(dst))
    assert count2 == 1

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
    assert count < 100


def test_flatbak_meta_persists(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "a.txt", "persist")

    bak = FlatBak()
    bak.run(str(src), str(dst))

    meta = load_meta(dst)
    assert len(meta["entries"]) == 1
    assert meta["entries"][0]["dst_name"] == "a.txt"


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


def test_flatbak_order_sorted(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "z.txt", "last")
    _create_file(src, "a.txt", "first")
    _create_file(src, "m.txt", "middle")

    bak = FlatBak()
    bak.run(str(src), str(dst))

    meta = load_meta(dst)
    names = [e["dst_name"] for e in meta["entries"]]
    assert names == sorted(names)


def test_flatbak_iphone_live_photo_scenario(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "IMG_0001.heic", "photo")
    _create_file(src, "IMG_0001.mov", "video")
    _create_file(src, "IMG_0002.heic", "photo2")
    _create_file(src, "IMG_0002.mov", "video2")

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    assert count == 4

    files = sorted([f.name for f in dst.iterdir() if f.is_file() and not f.name.startswith(".flatbak")])
    assert files == ["IMG_0001.heic", "IMG_0001.mov", "IMG_0002.heic", "IMG_0002.mov"]
