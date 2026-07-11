#!/usr/bin/env python3
"""
flatbak 打包脚本
支持:
  - 本地打包 (macOS / Windows / Linux)
  - Docker 交叉编译 (macOS → Windows/Linux, Linux → Windows)
  - GitHub Actions CI
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


def pyinstaller_build(platform_name: str, extra_args: list[str] | None = None):
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
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(ENTRY_POINT)

    print(f"[{platform_name}] 打包命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[{platform_name}] 打包失败:")
        print(result.stdout)
        print(result.stderr)
        sys.exit(1)

    print(f"[{platform_name}] 打包成功 → {dist_dir.resolve()}")
    for f in sorted(dist_dir.rglob("*")):
        if f.is_file():
            rel = f.relative_to(dist_dir)
            print(f"  {rel}")
    return dist_dir


# ───────────────────────────── 本地打包 ─────────────────────────────

def build_local():
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

    pyinstaller_build(platform_name, extra)


# ───────────────────────────── Docker 交叉编译 ─────────────────────────────

DOCKER_IMAGES = {
    "windows-x64": "dockcross/windows-static-x64",
    "linux-x64":   "dockcross/linux-x64",
    "linux-arm64": "dockcross/linux-arm64",
}

def _docker_build_internal(target: str):
    image = DOCKER_IMAGES.get(target)
    if not image:
        print(f"不支持的交叉编译目标: {target}")
        print(f"可用: {list(DOCKER_IMAGES.keys())}")
        sys.exit(1)

    dist_dir = Path("dist") / f"{APP_NAME}-{target}"
    build_dir = Path("build") / target

    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    if build_dir.exists():
        shutil.rmtree(build_dir)

    os.makedirs(build_dir, exist_ok=True)

    container_script = f"""
set -e
pip install pyinstaller
pyinstaller \\
  --name {APP_NAME} \\
  --distpath /work/dist/{APP_NAME}-{target} \\
  --workpath /work/build/{target} \\
  --specpath /work/build/{target} \\
  --noconfirm \\
  /work/{ENTRY_POINT}
chown -R $(stat -c %u:%g /work) /work/dist /work/build 2>/dev/null || true
"""

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{Path.cwd()}:/work",
        image,
        "bash", "-c", container_script,
    ]

    print(f"[{target}] Docker 交叉编译命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"[{target}] 交叉编译失败")
        sys.exit(1)

    print(f"[{target}] 交叉编译成功 → {dist_dir.resolve()}")
    for f in sorted(dist_dir.rglob("*")):
        if f.is_file():
            rel = f.relative_to(dist_dir)
            print(f"  {rel}")


# ───────────────────────────── GitHub Actions ─────────────────────────────

GHA_MATRIX = {
    "macos-arm64":   {"runs-on": "macos-14",       "extra": ["--windowed", "--argv-emulation"]},
    "macos-x64":     {"runs-on": "macos-13",       "extra": ["--windowed", "--argv-emulation"]},
    "windows-x64":   {"runs-on": "windows-latest", "extra": ["--windowed"]},
    "linux-x64":     {"runs-on": "ubuntu-latest",  "extra": []},
}


# ───────────────────────────── CLI 入口 ─────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FlatBak 打包工具")
    parser.add_argument("action", nargs="?", default="local",
                        choices=["local", "docker", "list"])
    parser.add_argument("--target", "-t",
                        help="交叉编译目标平台 (如 windows-x64, linux-x64, linux-arm64)")
    args = parser.parse_args()

    if args.action == "list":
        print("可用目标平台:")
        print(f"  docker: {list(DOCKER_IMAGES.keys())}")
        print(f"  gha:    {list(GHA_MATRIX.keys())}")
        print()
        print("本地平台:", platform.system().lower(), platform.machine().lower())
        return

    if args.action == "local":
        build_local()
        return

    if args.action == "docker":
        if not args.target:
            print("请指定交叉编译目标: python3 build.py docker --target windows-x64")
            print(f"可用目标: {list(DOCKER_IMAGES.keys())}")
            sys.exit(1)
        _docker_build_internal(args.target)
        return


if __name__ == "__main__":
    main()
