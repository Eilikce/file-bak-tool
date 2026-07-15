"""
flatbak - 扁平化文件备份工具核心模块

策略：
  - 按文件名排序扫描源目录
  - 文件保持原名，不重命名
  - 同名 + 同内容的文件只存一份
  - 同名但内容不同的文件：后到的跳过（不保存）
  - 元数据每次备份开始根据目标目录实际文件重建
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


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


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


class FlatBak:
    def __init__(self):
        self._lock = Lock()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @staticmethod
    def _rebuild_meta(target_dir: Path) -> dict:
        entries = []
        for f in sorted(target_dir.iterdir()):
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
        skipped_same_content = 0
        skipped_name_conflict = 0

        all_files = sorted(src.rglob("*"))
        total = sum(1 for f in all_files if f.is_file())
        processed = 0

        for filepath in all_files:
            if self._cancelled:
                self._log(log_callback, "用户取消了备份")
                break
            if not filepath.is_file():
                continue

            sha = sha256_file(filepath)
            fname = filepath.name
            mtime = filepath.stat().st_mtime

            # 情况1：目标中已有同内容文件（无论文件名）→ 跳过
            if sha in hash_to_name:
                skipped_same_content += 1
                processed += 1
                if progress_callback:
                    progress_callback(processed, total)
                continue

            # 情况2：同名文件已存在且内容不同 → 跳过（不重命名）
            if fname in name_to_hash:
                skipped_name_conflict += 1
                msg = f"跳过 {fname}: 目标中已有同名但不同内容的文件"
                self._log(log_callback, msg)
                append_log(target, msg)
                processed += 1
                if progress_callback:
                    progress_callback(processed, total)
                continue

            dst_path = target / fname
            try:
                shutil.copy2(str(filepath), str(dst_path))
            except Exception as e:
                msg = f"复制失败 {fname}: {e}"
                self._log(log_callback, msg)
                append_log(target, msg)
                processed += 1
                if progress_callback:
                    progress_callback(processed, total)
                continue

            meta["entries"].append({
                "src_path": str(filepath),
                "sha256": sha,
                "dst_name": fname,
                "mtime": mtime,
            })
            name_to_hash[fname] = sha
            hash_to_name[sha] = fname
            copied_count += 1
            msg = f"已复制 {fname}"
            self._log(log_callback, msg)
            append_log(target, msg)

            processed += 1
            if progress_callback:
                progress_callback(processed, total)

        write_meta(target, meta)
        summary = (f"备份完成: 共处理 {processed} 个文件, "
                   f"复制 {copied_count} 个, "
                   f"跳过(同内容) {skipped_same_content} 个, "
                   f"跳过(同名冲突) {skipped_name_conflict} 个")
        self._log(log_callback, summary)
        append_log(target, summary)
        return copied_count

    def _log(self, callback, msg):
        if callback:
            callback(msg)
