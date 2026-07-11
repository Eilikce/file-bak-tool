"""
flatbak - 扁平化文件备份工具核心模块

命名规则（可预判的唯一名称）:
  dst_name = f"{stem}_{hash_short}{ext}"
  
冲突时（极低概率）追加计数器: dst_name = f"{stem}_{hash_short}_{n}{ext}"
"""

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from threading import Lock

META_FILENAME = ".flatbak_meta.json"
LOG_FILENAME = ".flatbak_log.txt"
HASH_SHORT_LEN = 8


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_dst_name(stem: str, ext: str, sha256_full: str) -> str:
    short_hash = sha256_full[:HASH_SHORT_LEN]
    return f"{stem}_{short_hash}{ext}"


def generate_dst_name_with_counter(stem: str, ext: str, sha256_full: str, counter: int) -> str:
    short_hash = sha256_full[:HASH_SHORT_LEN]
    return f"{stem}_{short_hash}_{counter}{ext}"


def load_meta(target_dir: Path) -> dict:
    meta_path = target_dir / META_FILENAME
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"entries": []}


def write_meta(target_dir: Path, data: dict):
    meta_path = target_dir / META_FILENAME
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def append_log(target_dir: Path, message: str):
    log_path = target_dir / LOG_FILENAME
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def build_target_index(meta: dict) -> tuple[dict[str, str], dict[str, str]]:
    name_to_hash: dict[str, str] = {}
    hash_to_name: dict[str, str] = {}
    for entry in meta.get("entries", []):
        dn = entry["dst_name"]
        h = entry["sha256"]
        name_to_hash[dn] = h
        hash_to_name[h] = dn
    return name_to_hash, hash_to_name


def resolve_conflict(
    stem: str,
    ext: str,
    src_sha256: str,
    name_to_hash: dict,
    hash_to_name: dict,
) -> str | None:
    # 1. 先按内容去重：目标中已有同内容文件则跳过
    if src_sha256 in hash_to_name:
        existing_name = hash_to_name[src_sha256]
        # 检查目标文件是否真的还在磁盘上
        return None

    candidate = generate_dst_name(stem, ext, src_sha256)
    if candidate not in name_to_hash:
        return candidate

    counter = 1
    while True:
        candidate = generate_dst_name_with_counter(stem, ext, src_sha256, counter)
        if candidate not in name_to_hash:
            return candidate
        counter += 1


class FlatBak:
    def __init__(self):
        self._lock = Lock()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @staticmethod
    def _rebuild_meta(target_dir: Path) -> dict:
        entries = []
        for f in target_dir.iterdir():
            if f.is_file() and not f.name.startswith("."):
                h = sha256_file(f)
                entries.append({
                    "src_path": "",
                    "sha256": h,
                    "dst_name": f.name,
                    "mtime": f.stat().st_mtime,
                })
        return {"entries": entries}

    def run(
        self,
        src_dir: str | Path,
        target_dir: str | Path,
        progress_callback=None,
        log_callback=None,
    ) -> int:
        self._cancelled = False
        src = Path(src_dir).resolve()
        target = Path(target_dir).resolve()

        if not src.is_dir():
            raise ValueError(f"源目录不存在: {src}")
        target.mkdir(parents=True, exist_ok=True)

        meta = FlatBak._rebuild_meta(target)
        name_to_hash, hash_to_name = build_target_index(meta)
        copied_count = 0

        all_files = list(src.rglob("*"))
        total = sum(1 for f in all_files if f.is_file())
        processed = 0

        for filepath in all_files:
            if self._cancelled:
                self._log(log_callback, "用户取消了备份")
                break
            if not filepath.is_file():
                continue

            sha = sha256_file(filepath)
            stem = filepath.stem
            ext = filepath.suffix
            mtime = filepath.stat().st_mtime

            dst_name = resolve_conflict(stem, ext, sha, name_to_hash, hash_to_name)
            if dst_name is None:
                processed += 1
                if progress_callback:
                    progress_callback(processed, total)
                continue

            dst_path = target / dst_name
            try:
                shutil.copy2(str(filepath), str(dst_path))
            except Exception as e:
                msg = f"复制失败 {filepath.name} -> {dst_name}: {e}"
                self._log(log_callback, msg)
                append_log(target, msg)
                processed += 1
                if progress_callback:
                    progress_callback(processed, total)
                continue

            meta["entries"].append({
                "src_path": str(filepath),
                "sha256": sha,
                "dst_name": dst_name,
                "mtime": mtime,
            })
            name_to_hash[dst_name] = sha
            hash_to_name[sha] = dst_name
            copied_count += 1
            msg = f"已复制 {filepath.name} -> {dst_name}"
            self._log(log_callback, msg)
            append_log(target, msg)

            processed += 1
            if progress_callback:
                progress_callback(processed, total)

        write_meta(target, meta)
        summary = f"备份完成: 共处理 {processed} 个文件, 复制 {copied_count} 个"
        self._log(log_callback, summary)
        append_log(target, summary)
        return copied_count

    def _log(self, callback, msg):
        if callback:
            callback(msg)
