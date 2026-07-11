# FlatBak - 扁平化文件备份工具

将源目录中所有层级的文件，扁平化备份到目标目录，**相同内容的文件只保存一份**。

## 功能

- **扁平化** — 递归读取源目录所有文件，全部存入目标目录同一层
- **按内容去重** — 相同内容的文件（无论文件名是否相同）只保留一份
- **增量备份** — 仅复制新增或内容变更的文件
- **冲突自动重命名** — 同名但不同内容时按可预判规则改名，永不丢文件
- **元数据自动重建** — 每次备份开始根据目标目录实际文件重建 `.flatbak_meta.json`，手动删除备份文件后下次备份会自动补全
- **纯离线** — 无需数据库，元数据和日志直接写入目标目录
- **跨平台** — 支持 macOS（Intel + Apple Silicon）/ Windows / Linux

## 重命名规则（可预判）

```
源文件:  report.pdf              SHA-256: abcdef123456...
目标名:  report_abcdef12.pdf     (原文件名_哈希前8位.扩展名)

如果目标中已有 report_abcdef12.pdf 但内容不同：
→ report_abcdef12_1.pdf
→ report_abcdef12_2.pdf  ... 直到不冲突
```

> 同内容的文件命名始终相同（哈希决定），增量备份时自动跳过。

## 使用说明

### 方式一：直接运行（开发/调试）

```bash
# 1. 安装依赖
pip3 install PySide6

# 2. 启动 GUI
python3 main.py

# 3. 在界面中选择源目录和目标目录，点击"开始备份"
```

### 方式二：打包后运行（推荐）

见下方打包说明，打包后得到独立可执行文件，无需安装 Python。

## 打包说明

### 环境要求

| 平台 | Python | 打包工具 | 产物 |
|------|--------|----------|------|
| macOS Intel | ≥ 3.10 | PyInstaller | FlatBak.app |
| macOS Apple Silicon (M1/M2/M3) | ≥ 3.10 | PyInstaller | FlatBak.app |
| Windows x64 | ≥ 3.10 | PyInstaller | FlatBak.exe |
| Linux x64 | ≥ 3.10 | PyInstaller | FlatBak 可执行文件 |

### 通用打包命令

```bash
pip3 install pyinstaller
python3 build.py
```

产物输出到 `dist/FlatBak-{platform}/` 目录：
- **macOS** — `FlatBak.app`（可直接拖入 Applications 文件夹使用）
- **Windows** — `FlatBak.exe`
- **Linux** — `FlatBak` 可执行文件

### macOS 平台说明

当前 macOS 机器是什么架构，打包出的就是什么架构：

```bash
# 查看当前架构
uname -m
# arm64 → Apple Silicon
# x86_64 → Intel

python3 build.py   # 产物自动适配当前架构
```

如需交叉编译（如在 Intel Mac 上打包 ARM 版本），需使用 GitHub Actions CI（见下方）。

### Windows 平台说明

Windows 环境下打包命令相同，产物为 `FlatBak.exe`。建议使用 `--onefile` 模式：

```bash
pyinstaller --onefile --windowed --name FlatBak main.py
```

### Linux 平台说明

Linux 环境下需额外安装 Qt 系统依赖：

```bash
sudo apt-get install libegl1-mesa libgl1-mesa-glx libxcb-cursor0
pip3 install pyinstaller
python3 build.py
```

## CI/CD（GitHub Actions 自动打包）

配置在 `.github/workflows/build.yml`，支持：

| 触发时机 | 行为 |
|----------|------|
| push / PR 到 main | 在 4 个平台运行测试 |
| 创建 Release | 在 3 个平台打包并上传 artifacts |

### Release 手动触发打包步骤

1. 在 GitHub 仓库页面点击 **Releases → Create a new release**
2. 填写版本号（如 `v1.0.0`）
3. 点击 **Publish release**
4. Actions 自动开始打包，完成后可在 Release 页面下载各平台产物

### 手动下载 artifacts

如果只想测试打包而不创建 Release，可在 GitHub Actions 页面手动触发 workflow：

```yaml
# 通过 gh CLI 触发
gh workflow run build.yml
```

## 运行测试

```bash
pip3 install pytest
python3 -m pytest tests/ -v
```

## 项目结构

```
├── main.py                  入口
├── build.py                 打包脚本
├── src/
│   ├── backup_core.py       核心逻辑（哈希、去重、冲突、元数据）
│   └── gui.py               PySide6 图形界面
├── tests/
│   └── test_backup_core.py  28 个单元 + 集成测试
├── test_data/               测试数据目录
│   ├── A/                   源目录（多层级、多文件）
│   └── B/                   备份目标目录
├── .github/workflows/
│   └── build.yml            CI/CD
└── README.md
```

## 输出到目标目录的文件

| 文件 | 说明 |
|------|------|
| `<原文件名>_<哈希8位>.<扩展名>` | 备份的源文件，同内容只存一份 |
| `.flatbak_meta.json` | 元数据（每次备份开始自动根据磁盘文件重建） |
| `.flatbak_log.txt` | 操作日志（每次备份追加） |

## 工作流程示意

```
源目录 A                         目标目录 B
├── A1/                            ├── 1_6b86b273        (内容"1")
│   ├── 1                          ├── 2_d4735e3a        (内容"2")
│   ├── 11                        ├── .flatbak_meta.json
│   ├── 2                         └── .flatbak_log.txt
│   ├── 22
│   ├── 222
│   └── xxx              →    扁平化 + 按内容去重
├── A2/
│   ├── 1
│   ├── 11
│   ├── 2
│   ├── 22
│   └── 222
├── A3/
│   ├── 1
│   ├── 11
│   └── 111
```

A 目录有 13 个文件（仅 2 种内容），B 目录只存 2 个文件，每种内容仅一份。
