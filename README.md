# FlatBak - 扁平化文件备份工具

将源目录中所有层级的文件，扁平化备份到目标目录，**文件保持原名**，**同内容文件只存一份**。

## 功能

- **扁平化** — 递归读取源目录所有文件，全部存入目标目录同一层
- **不重命名** — 文件保持原名，同名同内容自动跳过，同名不同内容则跳过（不覆盖、不改名）
- **按文件名排序** — 按文件名顺序扫描，保证每次备份行为一致
- **增量备份** — 仅复制新增或内容变更的文件
- **元数据自动重建** — 每次备份开始根据目标目录实际文件重建 `.flatbak_meta.json`，手动删除备份文件后下次备份会自动补全
- **纯离线** — 无需数据库，元数据和日志直接写入目标目录
- **跨平台** — 支持 macOS（Intel + Apple Silicon）/ Windows / Linux

## 使用说明

### 直接运行（开发/调试）

```bash
# 1. 安装依赖
pip3 install PySide6

# 2. 启动 GUI
python3 main.py

# 3. 在界面中选择源目录和目标目录，点击"开始备份"
```

### 打包后运行

见下方打包说明，打包后得到独立可执行文件，无需安装 Python。

## 打包说明

支持在当前平台打包本平台应用，不支持交叉编译。

| 打包平台 | 命令 | 产物 |
|----------|------|------|
| macOS | `pip3 install pyinstaller && python3 build.py` | FlatBak.app |
| Windows | `pip install pyinstaller && python3 build.py` | FlatBak.exe |
| Linux | `pip3 install pyinstaller && python3 build.py` | FlatBak |

产物输出到 `dist/FlatBak-{platform}/` 目录。

### Linux 额外依赖

```bash
sudo apt-get install libegl1-mesa libgl1-mesa-glx libxcb-cursor0
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
│   ├── backup_core.py       核心逻辑（哈希、去重、元数据）
│   └── gui.py               PySide6 图形界面
├── tests/
│   └── test_backup_core.py  测试
├── test_data/               测试数据目录
│   ├── A/                   源目录（多层级、多文件）
│   └── B/                   备份目标目录
└── README.md
```

## 输出到目标目录的文件

| 文件 | 说明 |
|------|------|
| 源文件名（保持原名） | 备份的源文件，同内容只存一份 |
| `.flatbak_meta.json` | 元数据（每次备份开始自动根据磁盘文件重建） |
| `.flatbak_log.txt` | 操作日志（每次备份追加） |

## 工作流程示意

```
源目录 A                         目标目录 B
├── A1/                            ├── 1        (内容"1")
│   ├── 1                          ├── 11       (同内容，跳过)
│   ├── 11                         ├── 111      (同内容，跳过)
│   ├── 111                        ├── 2        (内容"2")
│   ├── 2                          ├── 22       (同内容，跳过)
│   ├── 22                         ├── 222      (同内容，跳过)
│   ├── 222                        ├── 2222     (同内容，跳过)
│   └── xxx                        ├── xxx      (同内容，跳过)
├── A2/                  →         ├── .flatbak_meta.json
│   ├── 1               扁平化      └── .flatbak_log.txt
│   ├── 11              保持原名
│   ├── 111
│   ├── 2
│   ├── 22
│   └── 222
├── A3/
│   ├── 1
│   ├── 11
│   ├── 111
│   ├── 2
│   ├── 22
│   ├── 222
│   └── 2222
```

A 目录有 22 个文件（仅 2 种内容），B 目录只存 7 个文件（每个不同文件名首次出现的副本），同内容同名的后续文件跳过。
