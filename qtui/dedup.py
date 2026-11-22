"""Qt 曲库去重审阅：扫描音频目录，预览重复文件后清理。"""

import threading
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from dedup_review import delete_duplicates, format_size, scan_folder


class DedupReviewDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("曲库去重审阅")
        self.resize(760, 520)
        self.folder = ""
        self.rows = {}
        self.groups = []
        self.busy = False
        self.stop = threading.Event()
        self.events = []
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        head = QHBoxLayout()
        heading = QLabel("曲库去重审阅")
        heading.setStyleSheet("font-size: 18px; font-weight: bold;")
        head.addWidget(heading)
        head.addStretch(1)
        self.choose_button = QPushButton("选择目录")
        self.choose_button.clicked.connect(self.choose_folder)
        head.addWidget(self.choose_button)
        self.scan_button = QPushButton("开始扫描")
        self.scan_button.clicked.connect(self.scan)
        head.addWidget(self.scan_button)
        layout.addLayout(head)

        self.folder_label = QLabel("先选择要检查的目录。")
        self.folder_label.setWordWrap(True)
        self.folder_label.setProperty("muted", True)
        layout.addWidget(self.folder_label)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("处理", "文件", "大小", "组"))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.cellClicked.connect(self.toggle)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for column in (0, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setProperty("muted", True)
        layout.addWidget(self.summary)

        foot = QHBoxLayout()
        self.mark_all_button = QPushButton("全部标记删除")
        self.mark_all_button.clicked.connect(self.mark_all)
        foot.addWidget(self.mark_all_button)
        foot.addStretch(1)
        self.delete_button = QPushButton("删除所选重复")
        self.delete_button.clicked.connect(self.remove_marked)
        foot.addWidget(self.delete_button)
        close = QPushButton("关闭")
        close.clicked.connect(self.close)
        foot.addWidget(close)
        layout.addLayout(foot)

        self.timer = QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self._refresh()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if urls:
            root = Path(urls[0])
            self._set_folder(str(root if root.is_dir() else root.parent))

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择要检查的目录", self.folder or str(Path.home()))
        if folder:
            self._set_folder(folder)

    def _set_folder(self, folder):
        self.folder = folder
        self.folder_label.setText("目录 · " + folder)

    def scan(self):
        if self.busy:
            return
        if not self.folder or not Path(self.folder).is_dir():
            self.folder_label.setText("请先选择有效的目录。")
            return
        self.busy = True
        self.stop = threading.Event()
        self.table.setRowCount(0)
        self.rows = {}
        self.summary.setText("正在扫描目录…")
        self._refresh()
        folder, stop, events = self.folder, self.stop, self.events

        def run():
            try:
                result = scan_folder(folder, stop=stop,
                                     on_status=lambda text: events.append(("status", text)))
            except Exception as error:
                events.append(("failed", str(error)))
            else:
                events.append(("done", result))

        threading.Thread(target=run, daemon=True).start()

    def toggle(self, row, _column):
        if self.busy:
            return
        item = self.rows.get(row)
        if not item or item["keeper"]:
            return
        item["deleting"] = not item["deleting"]
        self.table.setItem(row, 0, QTableWidgetItem("删除" if item["deleting"] else "保留"))
        self._refresh()

    def mark_all(self):
        if self.busy:
            return
        for row, item in self.rows.items():
            if not item["keeper"]:
                item["deleting"] = True
                self.table.setItem(row, 0, QTableWidgetItem("删除"))
        self._refresh()

    def remove_marked(self):
        if self.busy:
            return
        entries = [(item["path"], item["fingerprint"]) for item in self.rows.values()
                   if item["deleting"] and not item["keeper"]]
        if not entries:
            self.summary.setText("请先标记要删除的重复文件。")
            return
        self.busy = True
        self.stop = threading.Event()
        events, stop = self.events, self.stop
        self.summary.setText(f"正在删除 {len(entries)} 个重复文件…")
        self._refresh()

        def run():
            try:
                removed, failures = delete_duplicates(entries, stop=stop,
                                                      on_status=lambda text: events.append(("status", text)))
            except Exception as error:
                events.append(("failed", str(error)))
            else:
                events.append(("removed", (removed, failures)))

        threading.Thread(target=run, daemon=True).start()

    def _refresh(self):
        idle = not self.busy
        self.choose_button.setEnabled(idle)
        self.scan_button.setEnabled(idle and bool(self.folder))
        self.mark_all_button.setEnabled(idle and bool(self.rows))
        self.delete_button.setEnabled(idle and any(
            item["deleting"] and not item["keeper"] for item in self.rows.values()))

    def _render(self, result):
        self.groups = result.get("groups") or []
        self.table.setRowCount(0)
        self.rows = {}
        for group_index, group in enumerate(self.groups, 1):
            for file_index, path in enumerate(group["files"]):
                keeper = file_index == 0
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem("保留" if keeper else "删除"))
                self.table.setItem(row, 1, QTableWidgetItem(path))
                self.table.setItem(row, 2, QTableWidgetItem(format_size(group.get("size", 0))))
                self.table.setItem(row, 3, QTableWidgetItem(f"#{group_index}"))
                self.rows[row] = {"path": path, "fingerprint": group["fingerprint"],
                                  "keeper": keeper, "deleting": not keeper}
        self.summary.setText(
            f"扫描 {result.get('scanned', 0)} 个音频文件，发现 {result.get('duplicates', 0)} 个可删除的重复文件。")

    def poll(self):
        while self.events:
            kind, value = self.events.pop(0)
            if kind == "status":
                self.summary.setText(value)
            elif kind == "failed":
                self.busy = False
                self.summary.setText(str(value))
            elif kind == "done":
                self.busy = False
                self._render(value)
            elif kind == "removed":
                self.busy = False
                removed, failures = value
                text = f"已删除 {len(removed)} 个重复文件。"
                if failures:
                    text += " 失败 " + "；".join(failures[:3])
                self.summary.setText(text)
                self.scan()
        self._refresh()
