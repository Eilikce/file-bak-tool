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
    _generate_unique_name,
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


def test_flatbak_rename_name_conflict(tmp_path):
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "IMG_001.jpg", "photo1 data")
    _create_file(src, "sub/IMG_001.jpg", "photo2 data")

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    assert count == 2  # both saved, second one renamed

    files = sorted([f.name for f in dst.iterdir() if f.is_file() and not f.name.startswith(".flatbak")])
    assert len(files) == 2
    assert files[0] == "IMG_001.jpg"
    assert files[1] == "IMG_001_1.jpg"


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


def test_flatbak_rename_cascading(tmp_path):
    """三个同名但不同内容的文件：a.txt, a_1.txt, a_2.txt"""
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "a.txt", "content A")
    _create_file(src, "sub1/a.txt", "content B")
    _create_file(src, "sub2/a.txt", "content C")

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    assert count == 3  # all three saved, a.txt, a_1.txt, a_2.txt

    files = sorted([f.name for f in dst.iterdir() if f.is_file() and not f.name.startswith(".flatbak")])
    assert files == ["a.txt", "a_1.txt", "a_2.txt"]


def test_flatbak_rename_not_overwrite_existing(tmp_path):
    """目标中已存在 a_1.txt，源文件 a.txt 重命名时应跳过 a_1.txt"""
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(dst, "a.txt", "existing A")
    _create_file(dst, "a_1.txt", "existing B")
    _create_file(src, "a.txt", "new content different from both")

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    assert count == 1  # the new a.txt gets renamed to a_2.txt

    files = sorted([f.name for f in dst.iterdir() if f.is_file() and not f.name.startswith(".flatbak")])
    assert "a.txt" in files
    assert "a_1.txt" in files
    assert "a_2.txt" in files
    assert len(files) == 3


def test_flatbak_rename_many_collisions(tmp_path):
    """目标中 a.txt ~ a_5.txt 都被占用了，新来的 a.txt 应变成 a_6.txt"""
    src = tmp_path / "source"
    dst = tmp_path / "target"
    for i in range(6):
        suffix = "" if i == 0 else f"_{i}"
        _create_file(dst, f"a{suffix}.txt", f"existing {i}")
    _create_file(src, "a.txt", "new content")

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    assert count == 1

    files = sorted([f.name for f in dst.iterdir() if f.is_file() and not f.name.startswith(".flatbak")])
    assert "a_6.txt" in files
    assert len(files) == 7


def test_generate_unique_name_no_conflict():
    name_to_hash = {}
    assert _generate_unique_name("a.txt", name_to_hash) == "a.txt"


def test_generate_unique_name_has_conflict():
    name_to_hash = {"a.txt": "sha1"}
    assert _generate_unique_name("a.txt", name_to_hash) == "a_1.txt"


def test_generate_unique_name_multi_conflict():
    name_to_hash = {"a.txt": "sha1", "a_1.txt": "sha2"}
    assert _generate_unique_name("a.txt", name_to_hash) == "a_2.txt"


def test_generate_unique_name_no_ext():
    name_to_hash = {"file": "sha1"}
    assert _generate_unique_name("file", name_to_hash) == "file_1"


def test_generate_unique_name_multi_dot():
    name_to_hash = {"file.tar.gz": "sha1"}
    assert _generate_unique_name("file.tar.gz", name_to_hash) == "file.tar_1.gz"


def test_flatbak_rename_same_name_same_content_still_dedup(tmp_path):
    """两个同名同内容文件：只存一份（情况1先命中）"""
    src = tmp_path / "source"
    dst = tmp_path / "target"
    _create_file(src, "a.txt", "hello")
    _create_file(src, "sub/a.txt", "hello")

    bak = FlatBak()
    count = bak.run(str(src), str(dst))
    assert count == 1

    files = [f.name for f in dst.iterdir() if f.is_file() and not f.name.startswith(".flatbak")]
    assert files == ["a.txt"]


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
