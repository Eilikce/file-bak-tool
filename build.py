#!/usr/bin/env python3
"""
flatbak 打包脚本
支持在当前平台打包本平台应用：
  - macOS   → FlatBak.app + FlatBak CLI
  - Windows → FlatBak.exe
  - Linux   → FlatBak 可执行文件
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


APP_NAME = "FlatBak"
ENTRY_POINT = "main.py"


def check_dependencies():
    try:
        import PyInstaller  # noqa
    except ImportError:
        print("请先安装 PyInstaller: pip install pyinstaller")
        sys.exit(1)


def build():
    check_dependencies()
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
        platform_name = f"macos-{arch}"
        extra = ["--windowed", "--argv-emulation"]
    elif system == "windows":
        platform_name = "windows-x64"
        extra = ["--windowed"]
    elif system == "linux":
        arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
        platform_name = f"linux-{arch}"
        extra = []
    else:
        print(f"不支持的系统: {system}")
        sys.exit(1)

    dist_dir = Path("dist") / f"{APP_NAME}-{platform_name}"
    build_dir = Path("build") / platform_name

    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    if build_dir.exists():
        shutil.rmtree(build_dir)

    cmd = [
        "pyinstaller",
        "--name", APP_NAME,
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--specpath", str(build_dir),
        "--noconfirm",
    ]
    if extra:
        cmd.extend(extra)
    cmd.append(ENTRY_POINT)

    print(f"打包平台: {platform_name}")
    print(f"命令: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("打包失败:")
        print(result.stdout)
        print(result.stderr)
        sys.exit(1)

    print("打包成功!")
    print(f"输出目录: {dist_dir.resolve()}")
    for f in sorted(dist_dir.rglob("*")):
        if f.is_file():
            rel = f.relative_to(dist_dir)
            print(f"  {rel}")


if __name__ == "__main__":
    build()
