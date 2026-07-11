#!/usr/bin/env python3
"""
flatbak 打包脚本
支持: macOS (arm64), Windows (x64)
"""

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
        import PySide6  # noqa
    except ImportError:
        print("请先安装依赖: pip install PySide6")
        sys.exit(1)
    try:
        import PyInstaller  # noqa
    except ImportError:
        print("请先安装 PyInstaller: pip install pyinstaller")
        sys.exit(1)


def get_platform_config():
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        if machine in ("arm64", "aarch64"):
            return "macos-arm64", {
                "onedir": False,
                "windowed": True,
                "icon": None,
                "suffix": "",
            }
        else:
            return "macos-x64", {
                "onedir": False,
                "windowed": True,
                "icon": None,
                "suffix": "",
            }
    elif system == "windows":
        return "windows-x64", {
            "onedir": False,
            "windowed": True,
            "icon": None,
            "suffix": ".exe",
        }
    elif system == "linux":
        return f"linux-{machine}", {
            "onedir": False,
            "windowed": False,
            "icon": None,
            "suffix": "",
        }
    else:
        print(f"不支持的系统: {system}")
        sys.exit(1)


def build():
    check_dependencies()

    platform_name, config = get_platform_config()
    dist_dir = Path("dist") / f"{APP_NAME}-{platform_name}"
    build_dir = Path("build")

    # Clean old builds
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

    if config["windowed"]:
        cmd.append("--windowed")
        if platform_name.startswith("macos"):
            cmd.append("--argv-emulation")

    if config["icon"]:
        cmd.extend(["--icon", config["icon"]])

    # Add data files if needed
    # cmd.extend(["--add-data", f"src{os.pathsep}src"])

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

    # Show output files
    for f in dist_dir.rglob("*"):
        if f.is_file():
            rel = f.relative_to(dist_dir)
            print(f"  {rel}")


def build_cross_platform():
    """Cross-compilation placeholders - actual cross-compilation requires
    running on each target platform or using CI runners."""
    print("注意: 交叉编译需要在目标平台上运行 PyInstaller。")
    print("建议使用 GitHub Actions + matrix 策略:")
    print("  - macOS M1: macos-14  runner")
    print("  - macOS x64: macos-13 runner")
    print("  - Windows:   windows-latest runner")
    print("  - Linux:     ubuntu-latest runner")
    print()
    print("当前平台将自动打包:")
    build()


if __name__ == "__main__":
    build()
