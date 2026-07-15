"""
flatbak - 基于 PySide6 的扁平化文件备份 GUI
"""

import sys
import traceback
from pathlib import Path
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QFileDialog,
    QProgressBar,
    QTextEdit,
    QCheckBox,
    QMessageBox,
)

from src.backup_core import FlatBak


class BackupWorker(QThread):
    progress = Signal(int, int)
    log = Signal(str)
    phase = Signal(str)
    finished_signal = Signal(int)
    error_signal = Signal(str)

    def __init__(self, src_dir: str, target_dir: str, full_reindex: bool = True):
        super().__init__()
        self.src_dir = src_dir
        self.target_dir = target_dir
        self.full_reindex = full_reindex
        self.bak = FlatBak()

    def run(self):
        try:
            count = self.bak.run(
                src_dir=self.src_dir,
                target_dir=self.target_dir,
                progress_callback=self._on_progress,
                log_callback=self._on_log,
                phase_callback=self._on_phase,
                full_reindex=self.full_reindex,
            )
            self.finished_signal.emit(count)
        except Exception as e:
            self.error_signal.emit(f"{e}\n{traceback.format_exc()}")

    def cancel(self):
        self.bak.cancel()

    def _on_progress(self, current, total):
        self.progress.emit(current, total)

    def _on_log(self, msg):
        self.log.emit(msg)

    def _on_phase(self, name):
        self.phase.emit(name)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FlatBak - 扁平化文件备份工具")
        self.setMinimumSize(700, 500)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # 源目录
        src_layout = QHBoxLayout()
        src_layout.addWidget(QLabel("源目录:"))
        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText("选择要备份的源目录...")
        src_layout.addWidget(self.src_edit)
        src_btn = QPushButton("浏览...")
        src_btn.clicked.connect(self._choose_src)
        src_layout.addWidget(src_btn)
        layout.addLayout(src_layout)

        # 目标目录
        tgt_layout = QHBoxLayout()
        tgt_layout.addWidget(QLabel("目标目录:"))
        self.tgt_edit = QLineEdit()
        self.tgt_edit.setPlaceholderText("选择备份保存的目标目录...")
        tgt_layout.addWidget(self.tgt_edit)
        tgt_btn = QPushButton("浏览...")
        tgt_btn.clicked.connect(self._choose_target)
        tgt_layout.addWidget(tgt_btn)
        layout.addLayout(tgt_layout)

        # 索引模式
        self.full_reindex_cb = QCheckBox("完全重建索引（扫描目标目录所有文件计算哈希）")
        self.full_reindex_cb.setChecked(False)
        self.full_reindex_cb.setToolTip(
            "勾选：每次备份前重新扫描目标目录所有文件并计算SHA-256，最准确但较慢\n"
            "不勾选：直接使用上次备份生成的索引文件，快速但假设目标目录无外部改动"
        )
        layout.addWidget(self.full_reindex_cb)

        # 进度条
        self.phase_label = QLabel("就绪")
        layout.addWidget(self.phase_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m")
        layout.addWidget(self.progress_bar)

        # 控制按钮
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始备份")
        self.start_btn.clicked.connect(self._start_backup)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self._cancel_backup)
        self.cancel_btn.setEnabled(False)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        # 日志
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(QLabel("日志:"))
        layout.addWidget(self.log_area)

        self._worker: BackupWorker | None = None

    def _choose_src(self):
        d = QFileDialog.getExistingDirectory(self, "选择源目录")
        if d:
            self.src_edit.setText(d)

    def _choose_target(self):
        d = QFileDialog.getExistingDirectory(self, "选择目标目录")
        if d:
            self.tgt_edit.setText(d)

    def _start_backup(self):
        src = self.src_edit.text().strip()
        tgt = self.tgt_edit.text().strip()
        if not src or not tgt:
            QMessageBox.warning(self, "提示", "请先选择源目录和目标目录")
            return
        if src == tgt:
            QMessageBox.warning(self, "提示", "源目录和目标目录不能相同")
            return

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log_area.clear()
        self.progress_bar.setValue(0)
        self.phase_label.setText("就绪")

        self._worker = BackupWorker(src, tgt, full_reindex=self.full_reindex_cb.isChecked())
        self._worker.progress.connect(self._update_progress)
        self._worker.log.connect(self._append_log)
        self._worker.phase.connect(self._set_phase)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.error_signal.connect(self._on_error)
        self._worker.start()

    def _cancel_backup(self):
        if self._worker:
            self._worker.cancel()
            self._append_log("正在取消...")

    def _update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _set_phase(self, name):
        self.phase_label.setText(f"当前阶段: {name}")

    def _append_log(self, msg):
        self.log_area.append(msg)

    def _on_finished(self, count):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.phase_label.setText("完成")
        QMessageBox.information(self, "完成", f"备份完成, 共复制 {count} 个文件")
        self._worker = None

    def _on_error(self, err):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.phase_label.setText("错误")
        self.log_area.append(f"错误: {err}")
        QMessageBox.critical(self, "错误", f"备份过程中发生错误:\n{err}")
        self._worker = None


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("FlatBak")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
