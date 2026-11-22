"""Pages for the Qt shell: placeholders, the actionable queue and local conversion."""

import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog,
                               QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu,
                               QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
                               QTextEdit, QVBoxLayout, QWidget)

import settings
import app_update
import audio
from local_convert import formats_for

TASK_LABELS = {
    "pending": "待下载", "running": "下载中", "complete": "已完成",
    "failed": "失败", "interrupted": "已中断", "cancelled": "已取消",
}

LOCAL_FORMATS = {
    "mp3": "MP3", "m4a": "M4A（AAC）", "flac": "FLAC", "wav": "WAV", "opus": "Opus",
    "mp4": "MP4", "mkv": "MKV", "webm": "WebM",
}

QUALITY = {"AAC": "AAC-LC · 兼容", "ALAC": "ALAC · 无损", "ATMOS": "Dolby Atmos"}
BILI_FORMATS = {"video": "视频 · MP4", "audio": "音频 · M4A", "flac": "音频 · 原始 FLAC", "mp3": "音频 · MP3"}
YOUTUBE_FORMATS = {"video": "视频 · MP4", "audio": "音频 · M4A", "mp3": "音频 · MP3"}
MUSIC_QUALITIES = {
    "qq": {"auto": "自动 · 最佳可用", "128": "MP3 · 128 kbps", "320": "MP3 · 320 kbps", "flac": "FLAC · 无损"},
    "netease": {"auto": "自动 · 最佳可用", "128": "标准", "192": "较高", "320": "极高",
                "flac": "无损", "hires": "Hi-Res · 无损"},
}
UI_MODES = {"tkinter": "Tkinter（经典界面）", "qt": "Qt（新界面）"}

PAGES = (
    ("music", "Apple Music"),
    ("bilibili", "B 站"),
    ("qq", "QQ 音乐"),
    ("netease", "网易云音乐"),
    ("youtube", "YouTube"),
    ("douyin", "抖音"),
    ("queue", "下载队列"),
    ("local", "本地转码"),
    ("settings", "设置"),
)


class PlaceholderPage(QWidget):
    def __init__(self, title, note):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        heading = QLabel(f"{title} · 迁移中")
        heading.setAlignment(Qt.AlignCenter)
        heading.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(heading)
        hint = QLabel(note)
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        hint.setMaximumWidth(420)
        hint.setProperty("muted", True)
        layout.addWidget(hint)


SOURCE_LABELS = {
    "apple_music": "Apple Music", "bilibili": "B 站", "qq": "QQ 音乐",
    "netease": "网易云音乐", "youtube": "YouTube", "local": "本地转码",
}


class TaskDetailsDialog(QDialog):
    def __init__(self, parent, title, text):
        super().__init__(parent)
        self.setWindowTitle("下载任务")
        self.resize(520, 420)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 16px; font-weight: bold;")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self.body = QTextEdit()
        self.body.setReadOnly(True)
        self.body.setPlainText(text)
        layout.addWidget(self.body, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("关闭")
        close.clicked.connect(self.close)
        row.addWidget(close)
        layout.addLayout(row)


class QueuePage(QWidget):
    """Actionable download queue backed by the shared queue controller."""

    def __init__(self, core):
        super().__init__()
        self.core = core
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.summary = QLabel("下载队列")
        toolbar.addWidget(self.summary)
        toolbar.addStretch(1)
        toolbar.addWidget(QLabel("筛选"))
        self.filter_box = QComboBox()
        self.filter_box.addItem("全部", "")
        self.filter_box.currentIndexChanged.connect(lambda _index: self.refresh())
        toolbar.addWidget(self.filter_box)
        layout.addLayout(toolbar)

        actions = QHBoxLayout()
        self.start_button = QPushButton("开始 / 继续")
        self.start_button.clicked.connect(self.start)
        actions.addWidget(self.start_button)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.core.cancel)
        actions.addWidget(self.cancel_button)
        self.remove_button = QPushButton("移除所选")
        self.remove_button.clicked.connect(self.remove_selected)
        actions.addWidget(self.remove_button)
        self.details_button = QPushButton("任务详情")
        self.details_button.clicked.connect(self.show_details)
        actions.addWidget(self.details_button)
        self.open_button = QPushButton("打开位置")
        self.open_button.clicked.connect(self.open_location)
        actions.addWidget(self.open_button)
        self.export_button = QPushButton("导出 M3U8")
        self.export_button.clicked.connect(self.export_playlist)
        actions.addWidget(self.export_button)
        self.requeue_button = QPushButton("重新排队")
        self.requeue_button.clicked.connect(self.requeue_selected)
        actions.addWidget(self.requeue_button)
        actions.addStretch(1)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self.refresh)
        actions.addWidget(self.refresh_button)
        layout.addLayout(actions)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(("歌名", "歌手", "批次", "位置", "状态", "文件"))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_menu)
        self.table.doubleClicked.connect(lambda _index: self.show_details())
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2, 3, 4, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.ids = {}
        self.tasks = {}
        self.refresh()

    def selected_ids(self):
        return [self.ids[row] for row in {index.row() for index in self.table.selectedIndexes()}
                if row in self.ids]

    def selected_tasks(self):
        return [self.tasks[row] for row in {index.row() for index in self.table.selectedIndexes()}
                if row in self.tasks]

    def refresh(self):
        chosen = self.filter_box.currentData() if hasattr(self, "filter_box") else ""
        try:
            tasks = self.core.list_tasks()
        except (OSError, RuntimeError, ValueError) as error:
            tasks = []
            self.summary.setText(f"无法读取下载队列 · {error}")
        else:
            pending = sum(task.state in ("pending", "running", "interrupted") for task in tasks)
            self.summary.setText(f"下载队列 · 共 {len(tasks)} 项，其中待处理 {pending} 项")
        self._sync_filter(tasks)
        chosen = self.filter_box.currentData() if hasattr(self, "filter_box") else ""
        shown = [task for task in tasks if not chosen or task.source == chosen]
        self.table.setRowCount(0)
        self.ids = {}
        self.tasks = {}
        for task in sorted(shown, key=lambda item: item.id):
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.ids[row] = task.id
            self.tasks[row] = task
            position = f"{task.position}/{task.total}" if task.position and task.total else ""
            values = (task.title, task.artist or "", task.batch_title or "", position,
                      TASK_LABELS.get(task.state, task.state), str(len(task.files)))
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 4:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, column, item)

    def _sync_filter(self, tasks):
        present = sorted({task.source for task in tasks})
        known = [self.filter_box.itemData(index) for index in range(self.filter_box.count())]
        if known[1:] == present:
            return
        current = self.filter_box.currentData()
        self.filter_box.blockSignals(True)
        self.filter_box.clear()
        self.filter_box.addItem("全部", "")
        for source in present:
            self.filter_box.addItem(SOURCE_LABELS.get(source, source), source)
        index = self.filter_box.findData(current)
        self.filter_box.setCurrentIndex(max(0, index))
        self.filter_box.blockSignals(False)

    def start(self):
        self.core.start()
        self.refresh()

    def remove_selected(self):
        ids = self.selected_ids()
        if ids:
            self.core.remove(ids)
            self.refresh()

    def show_menu(self, position):
        from PySide6.QtWidgets import QMenu

        if not self.table.selectedIndexes():
            index = self.table.indexAt(position)
            if not index.isValid():
                return
            self.table.selectRow(index.row())
        menu = QMenu(self)
        menu.addAction("查看任务详情", self.show_details)
        menu.addAction("打开保存位置", self.open_location)
        menu.addAction("导出播放列表（M3U8）", self.export_playlist)
        menu.addSeparator()
        menu.addAction("重新排队", self.requeue_selected)
        menu.addAction("移除所选", self.remove_selected)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def show_details(self):
        tasks = self.selected_tasks()
        if not tasks:
            self.status.setText("请先选择任务。")
            return
        task = tasks[0]
        self.status.setText("正在读取任务详情…")
        self.detail_task = task
        self.detail_records = list(task.audio_details or [])

        def run():
            records = list(task.audio_details or [])
            if not records and task.files:
                for value in task.files:
                    path = Path(value)
                    if not formats_for(path):
                        continue
                    details = audio.audio_details(path)
                    if details:
                        records.append({"filename": path.name, "output": details})
            self.detail_records = records
            self.detail_ready = True

        if task.audio_details or not task.files:
            self.detail_ready = True
            self._open_details()
            return
        import threading
        self.detail_ready = False
        threading.Thread(target=run, daemon=True).start()
        self.detail_timer = QTimer(self)
        self.detail_timer.setSingleShot(True)
        self.detail_timer.setInterval(200)
        self.detail_timer.timeout.connect(self._wait_details)
        self.detail_timer.start()

    def _wait_details(self):
        if not getattr(self, "detail_ready", False):
            self.detail_timer.start()
            return
        self._open_details()

    def _open_details(self):
        task = self.detail_task
        records = getattr(self, "detail_records", [])
        lines = [TASK_LABELS.get(task.state, task.state)]
        if task.uploader:
            lines.append(f"投稿者 · {task.uploader}")
        if task.source_category:
            lines.append(f"分区 · {task.source_category}")
        options = task.options or {}
        if options:
            lines.append("来源 · " + SOURCE_LABELS.get(task.source, task.source))
            if task.source == "apple_music":
                quality = QUALITY.get(options.get("quality"), "")
                output = audio.OUTPUTS.get(options.get("output"), "")
                if quality or output:
                    lines.append(" · ".join(part for part in (quality, output) if part))
            elif task.source == "bilibili":
                lines.append(BILI_FORMATS.get(options.get("bili_mode"), BILI_FORMATS["video"]))
                converted = options.get("bili_output", "original")
                if options.get("bili_mode") != "video" and converted != "original":
                    lines.append("保存格式 · " + audio.OUTPUTS.get(converted, converted))
                    if converted == "mp3":
                        lines.append(f"MP3 输出 · {options.get('mp3_bitrate', audio.DEFAULT_MP3_BITRATE)} kbps")
                if options.get("bili_danmaku"):
                    lines.append("保存弹幕（ASS）")
                if options.get("bili_subtitle"):
                    lines.append("保存字幕（SRT）")
                if options.get("bili_archive"):
                    lines.append("保存封面与作品资料")
            elif task.source == "youtube":
                lines.append(YOUTUBE_FORMATS.get(options.get("youtube_mode"), YOUTUBE_FORMATS["video"]))
            elif task.source == "local":
                lines.append(task.url)
                lines.append(LOCAL_FORMATS.get(options.get("local_format"), ""))
            elif task.source in ("qq", "netease"):
                choices = MUSIC_QUALITIES[task.source]
                requested = options.get(f"{task.source}_quality", "auto")
                lines.append("请求音质 · " + choices.get(requested, "默认"))
                lines.append("保存格式 · " + audio.OUTPUTS.get(options.get("output", "original"), ""))
                if options.get("output") == "mp3":
                    lines.append(f"MP3 输出 · {options.get('mp3_bitrate', audio.DEFAULT_MP3_BITRATE)} kbps")
                if options.get("music_sidecars"):
                    lines.append("保存封面和歌词")
            folder = options.get("folder")
            if folder:
                from apple_download import task_category
                lines.append(str(Path(folder) / task_category(task)))
        if task.error:
            lines.append("错误 · " + task.error)
        for record in records:
            source = audio.describe_audio(record.get("source"))
            output = audio.describe_audio(record.get("output"))
            if len(records) > 1:
                lines.append(record.get("filename", ""))
            if source and source == output:
                lines.append(f"源与输出音频 · {source}")
            else:
                if source:
                    lines.append(f"源音频 · {source}")
                if output:
                    lines.append(f"输出音频 · {output}")
        lines.extend(task.files)
        self.status.setText("")
        TaskDetailsDialog(self, task.title, "\n".join([line for line in lines if line])).exec()

    def open_location(self):
        from apple_download import task_category

        tasks = self.selected_tasks()
        if not tasks:
            self.status.setText("请先选择任务。")
            return
        task = tasks[0]
        folder = None
        if task.files:
            folder = Path(task.files[0]).parent
        elif task.options and task.options.get("folder"):
            folder = Path(task.options["folder"]) / task_category(task)
        if folder is None or not Path(folder).is_dir():
            self.status.setText("找不到该任务的保存位置。")
            return
        try:
            os.startfile(str(folder))
        except OSError as error:
            self.status.setText(f"无法打开位置：{error}")

    def export_playlist(self):
        from playlist_export import save_m3u8

        tasks = [task for task in self.selected_tasks() if task.files]
        if not tasks:
            self.status.setText("所选任务还没有已保存的文件。")
            return
        batches = {task.batch_title for task in tasks}
        batch = next(iter(batches)) if len(batches) == 1 else ""
        initial = Path(tasks[0].files[0]).parent
        path, _ = QFileDialog.getSaveFileName(self, "导出播放列表", str(initial / f"{batch or '播放列表'}.m3u8"),
                                              "M3U8 播放列表 (*.m3u8)")
        if not path:
            return
        try:
            count = save_m3u8(path, tasks)
        except (OSError, ValueError) as error:
            self.status.setText(f"无法导出播放列表：{error}")
        else:
            self.status.setText(f"已导出 {count} 首 · {Path(path).name}")

    def requeue_selected(self):
        tasks = self.selected_tasks()
        if not tasks:
            self.status.setText("请先选择任务。")
            return
        if any(task.source == "local" for task in tasks):
            self.status.setText("本地转码任务不能按当前设置重新排队。")
            return
        try:
            self.core.requeue([task.id for task in tasks])
        except (OSError, RuntimeError, ValueError) as error:
            self.status.setText(f"无法重新排队：{error}")
        else:
            self.status.setText(f"已按当前设置重新排队 {len(tasks)} 项")
        self.refresh()

    def poll(self):
        while True:
            try:
                kind, value = self.core.messages.get_nowait()
            except Exception:
                break
            if kind == "status":
                self.status.setText(value)
            elif kind == "log":
                self.status.setText(value)
            elif kind in ("done", "failed"):
                self.core.busy = False
                if kind == "failed":
                    self.status.setText(str(value))
                elif isinstance(value, tuple):
                    saved, existing, errors, waiting = value
                    self.status.setText(f"处理结束 · 新增 {saved} · 已存在 {existing} · 失败 {errors}"
                                        + (f" · 等待磁盘 {waiting}" if waiting else ""))
                self.refresh()
        self.start_button.setEnabled(not self.core.busy)


class LocalPage(QWidget):
    """Add local files, pick an output format and hand them to the queue."""

    def __init__(self, core):
        super().__init__()
        self.core = core
        self.files = []
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        heading = QLabel("本地转码")
        heading.setStyleSheet("font-size: 20px; font-weight: bold;")
        toolbar.addWidget(heading)
        toolbar.addStretch(1)
        self.add_button = QPushButton("添加文件")
        self.add_button.clicked.connect(self.choose_files)
        toolbar.addWidget(self.add_button)
        self.tag_button = QPushButton("编辑标签")
        self.tag_button.clicked.connect(self.open_tag_editor)
        toolbar.addWidget(self.tag_button)
        self.remove_button = QPushButton("移除所选")
        self.remove_button.clicked.connect(self.remove_selected)
        toolbar.addWidget(self.remove_button)
        self.dedup_button = QPushButton("去重审阅")
        self.dedup_button.clicked.connect(self.open_dedup)
        toolbar.addWidget(self.dedup_button)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(("文件名", "类型"))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        options = QHBoxLayout()
        options.addWidget(QLabel("转码为"))
        self.format_box = QComboBox()
        options.addWidget(self.format_box)
        options.addWidget(QLabel("保存位置"))
        self.folder_button = QPushButton("原文件目录")
        self.folder_button.clicked.connect(self.choose_folder)
        options.addWidget(self.folder_button)
        options.addStretch(1)
        self.start_button = QPushButton("转码并加入队列")
        self.start_button.clicked.connect(self.start)
        options.addWidget(self.start_button)
        layout.addLayout(options)

        defaults = QHBoxLayout()
        defaults.addWidget(QLabel("默认输出格式"))
        preferences = settings.load()
        self.default_output = QComboBox()
        self.default_output.addItems(list(audio.OUTPUTS.values()))
        self.default_output.setCurrentText(
            audio.OUTPUTS.get(preferences.get("output", "original"), "保留原音轨"))
        defaults.addWidget(self.default_output)
        defaults.addWidget(QLabel("MP3 码率"))
        self.mp3_bitrate = QComboBox()
        self.mp3_bitrate.addItems([str(value) for value in audio.MP3_BITRATES])
        self.mp3_bitrate.setCurrentText(
            str(preferences.get("mp3_bitrate", audio.DEFAULT_MP3_BITRATE)))
        defaults.addWidget(self.mp3_bitrate)
        defaults.addStretch(1)
        self.defaults_note = QLabel("下载与本地转码共用的默认输出，修改后立即保存。")
        self.defaults_note.setProperty("muted", True)
        defaults.addWidget(self.defaults_note)
        layout.addLayout(defaults)
        self._defaults_ready = False
        self.default_output.currentTextChanged.connect(self.save_defaults)
        self.mp3_bitrate.currentTextChanged.connect(self.save_defaults)
        self._defaults_ready = True

        self.status = QLabel("添加音频或视频文件后选择输出格式。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.folder = ""
        self._update_formats()

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "添加本地影音文件")
        if paths:
            self.add_files(paths)

    def open_tag_editor(self):
        from qtui.tag_editor import TagEditorDialog
        dialog = TagEditorDialog(self)
        dialog.exec()

    def open_dedup(self):
        from qtui.dedup import DedupReviewDialog
        dialog = DedupReviewDialog(self)
        dialog.exec()

    def add_files(self, paths):
        known = {os.path.normcase(path) for path in self.files}
        added = 0
        for value in paths:
            path = Path(value)
            key = os.path.normcase(str(path))
            if key in known or not path.is_file() or not formats_for(path):
                continue
            self.files.append(str(path))
            known.add(key)
            added += 1
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(path.name))
            self.table.setItem(row, 1, QTableWidgetItem(path.suffix.upper().lstrip(".")))
        self.status.setText(f"{len(self.files)} 个文件")
        self._update_formats()

    def remove_selected(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
            del self.files[row]
        self.status.setText(f"{len(self.files)} 个文件")
        self._update_formats()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择转码保存位置",
                                                  self.folder or str(Path.home()))
        if folder:
            self.folder = folder
            self.folder_button.setText(folder)

    def save_defaults(self, _text=None):
        if not self._defaults_ready:
            return
        values = dict(settings.load())
        values["output"] = next((key for key, label in audio.OUTPUTS.items()
                                 if label == self.default_output.currentText()), "original")
        try:
            values["mp3_bitrate"] = int(self.mp3_bitrate.currentText())
        except ValueError:
            values["mp3_bitrate"] = audio.DEFAULT_MP3_BITRATE
        settings.save(values)
        self.defaults_note.setText("默认输出已保存：" + self.default_output.currentText()
                                   + (" · " + self.mp3_bitrate.currentText() + " kbps"
                                      if values["output"] == "mp3" else ""))

    def _common_formats(self):
        common = set(LOCAL_FORMATS)
        for path in self.files:
            common.intersection_update(formats_for(Path(path)))
        return [key for key in LOCAL_FORMATS if key in common]

    def _update_formats(self):
        keys = self._common_formats()
        self.format_box.clear()
        self.format_box.addItems([LOCAL_FORMATS[key] for key in keys])
        self.start_button.setEnabled(bool(keys and self.files))

    def start(self):
        if not self.files:
            return
        label = self.format_box.currentText()
        key = next((k for k, v in LOCAL_FORMATS.items() if v == label), None)
        if key is None:
            return
        ids = self.core.queue_local(self.files, key, self.folder)
        if ids:
            self.status.setText(f"已加入 {len(ids)} 个转码任务")
            self.core.start(ids)


def egress_text():
    """Return a one-line description of the current egress IP."""
    import json
    from urllib.request import Request, build_opener

    request = Request("http://ip-api.com/json/?fields=query,country,city,isp",
                      headers={"User-Agent": "Mozilla/5.0"})
    with build_opener().open(request, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8", "replace"))
    return (f"出口 {data.get('query')} · {data.get('country', '')} {data.get('city', '')} · "
            f"{data.get('isp', '')}")


def _app_version():
    try:
        return (Path(__file__).resolve().parents[1] / "app-version.txt").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return ""


class SettingsPage(QWidget):
    def __init__(self, app, dark):
        super().__init__()
        self.app = app
        self.dark = bool(dark)
        self.preferences = settings.load()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        heading = QLabel("设置")
        heading.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(heading)

        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setMaximumWidth(620)
        form = QVBoxLayout(frame)
        form.setSpacing(8)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("保存目录"))
        self.folder = QLineEdit(str(self.preferences.get("folder", "")))
        folder_row.addWidget(self.folder, 1)
        browse = QPushButton("浏览")
        browse.clicked.connect(self.choose_folder)
        folder_row.addWidget(browse)
        form.addLayout(folder_row)

        category_row = QHBoxLayout()
        category_row.addWidget(QLabel("分类文件夹"))
        self.category = QLineEdit(str(self.preferences.get("category", "")))
        category_row.addWidget(self.category, 1)
        form.addLayout(category_row)

        self.apple_quality = QComboBox()
        self.apple_quality.addItems(list(QUALITY.values()))
        self.apple_quality.setCurrentText(QUALITY.get(self.preferences.get("quality", "AAC"), QUALITY["AAC"]))
        form.addLayout(self._row("Apple 音质", self.apple_quality))

        for source, label in (("qq", "QQ 来源音质"), ("netease", "网易云来源音质")):
            box = QComboBox()
            box.addItems(list(MUSIC_QUALITIES[source].values()))
            box.setCurrentText(MUSIC_QUALITIES[source].get(self.preferences.get(f"{source}_quality", "auto"),
                                                          MUSIC_QUALITIES[source]["auto"]))
            setattr(self, f"{source}_quality", box)
            form.addLayout(self._row(label, box))

        self.bili_format = QComboBox()
        self.bili_format.addItems(list(BILI_FORMATS.values()))
        self.bili_format.setCurrentText(BILI_FORMATS.get(self.preferences.get("bili_mode", "video"), BILI_FORMATS["video"]))
        form.addLayout(self._row("B 站格式", self.bili_format))

        self.youtube_format = QComboBox()
        self.youtube_format.addItems(list(YOUTUBE_FORMATS.values()))
        self.youtube_format.setCurrentText(YOUTUBE_FORMATS.get(self.preferences.get("youtube_mode", "video"),
                                                               YOUTUBE_FORMATS["video"]))
        form.addLayout(self._row("YouTube 格式", self.youtube_format))

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("界面主题"))
        self.theme_button = QPushButton()
        self.theme_button.clicked.connect(self.toggle_theme)
        theme_row.addWidget(self.theme_button)
        theme_row.addStretch(1)
        form.addLayout(theme_row)

        self.ui_mode = QComboBox()
        self.ui_mode.addItems(list(UI_MODES.values()))
        self.ui_mode.setCurrentText(UI_MODES.get(self.preferences.get("ui_mode", "qt"), UI_MODES["qt"]))
        form.addLayout(self._row("启动界面", self.ui_mode))

        self.proxy = QLineEdit(str(self.preferences.get("proxy", "")))
        self.proxy.setPlaceholderText("例如 http://127.0.0.1:7890（留空则直连）")
        form.addLayout(self._row("网络代理", self.proxy))

        extras = QHBoxLayout()
        self.danmaku_box = QCheckBox("B 站弹幕（ASS）")
        self.subtitle_box = QCheckBox("B 站字幕（SRT）")
        self.archive_box = QCheckBox("B 站封面与资料")
        self.sidecar_box = QCheckBox("音乐封面歌词")
        for box, key in ((self.danmaku_box, "bili_danmaku"), (self.subtitle_box, "bili_subtitle"),
                         (self.archive_box, "bili_archive"), (self.sidecar_box, "music_sidecars")):
            box.setChecked(bool(self.preferences.get(key, False)))
            extras.addWidget(box)
        extras.addStretch(1)
        form.addLayout(extras)

        diag_row = QHBoxLayout()
        self.diag_button = QPushButton("测试网络")
        self.diag_button.clicked.connect(self.test_network)
        diag_row.addWidget(self.diag_button)
        self.diag = QLabel("显示当前出口 IP，用于确认代理或加速器是否生效。")
        self.diag.setWordWrap(True)
        self.diag.setProperty("muted", True)
        diag_row.addWidget(self.diag, 1)
        form.addLayout(diag_row)

        update_row = QHBoxLayout()
        self.update_button = QPushButton("检查更新")
        self.update_button.clicked.connect(self.check_updates)
        update_row.addWidget(self.update_button)
        self.update_status = QLabel("")
        self.update_status.setWordWrap(True)
        self.update_status.setProperty("muted", True)
        update_row.addWidget(self.update_status, 1)
        form.addLayout(update_row)
        self.update_install = QPushButton("下载并安装")
        self.update_install.clicked.connect(self.install_update)
        self.update_install.setVisible(False)
        form.addWidget(self.update_install)
        self.update_progress = QProgressBar()
        self.update_progress.setVisible(False)
        form.addWidget(self.update_progress)
        self.update_events = []
        self.update_result = None
        self.update_busy = False
        self.version = _app_version()

        self.messages = []
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        self.save_button = QPushButton("保存设置")
        self.save_button.clicked.connect(self.save)
        save_row.addWidget(self.save_button)
        form.addLayout(save_row)

        note = QLabel("其余设置与功能仍在迁移；请继续使用原界面（Run.cmd）完成平台操作。")
        note.setWordWrap(True)
        note.setProperty("muted", True)
        form.addWidget(note)
        layout.addWidget(frame)
        self._theme_text()

    @staticmethod
    def _row(label, widget):
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addWidget(widget, 1)
        return row

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择下载保存目录",
                                                  self.folder.text() or str(Path.home()))
        if folder:
            self.folder.setText(folder)

    def save(self):
        values = dict(settings.load())
        values["folder"] = self.folder.text().strip()
        values["category"] = self.category.text().strip()
        values["quality"] = next((key for key, label in QUALITY.items()
                                  if label == self.apple_quality.currentText()), "AAC")
        for source in ("qq", "netease"):
            box = getattr(self, f"{source}_quality")
            values[f"{source}_quality"] = next((key for key, label in MUSIC_QUALITIES[source].items()
                                                if label == box.currentText()), "auto")
        values["bili_mode"] = next((key for key, label in BILI_FORMATS.items()
                                    if label == self.bili_format.currentText()), "video")
        values["youtube_mode"] = next((key for key, label in YOUTUBE_FORMATS.items()
                                       if label == self.youtube_format.currentText()), "video")
        values["ui_mode"] = next((key for key, label in UI_MODES.items()
                                  if label == self.ui_mode.currentText()), "qt")
        values["proxy"] = self.proxy.text().strip()
        values["bili_danmaku"] = self.danmaku_box.isChecked()
        values["bili_subtitle"] = self.subtitle_box.isChecked()
        values["bili_archive"] = self.archive_box.isChecked()
        values["music_sidecars"] = self.sidecar_box.isChecked()
        settings.save(values)
        import net_proxy
        net_proxy.apply(values)
        self.status_message = "设置已保存"

    def check_updates(self):
        import threading

        if self.update_busy or not self.version:
            return
        self.update_button.setEnabled(False)
        self.update_install.setVisible(False)
        self.update_status.setText(f"版本 {self.version} · 正在检查更新…")
        events, version = self.update_events, self.version

        def run():
            try:
                result = app_update.check_update(version)
            except app_update.UpdateCheckError as error:
                events.append(("update_error", str(error)))
            else:
                events.append(("update_result", result))

        threading.Thread(target=run, daemon=True).start()

    def install_update(self):
        import tempfile
        import threading

        result = self.update_result
        if self.update_busy or result is None or not result.asset_url:
            return
        self.update_busy = True
        self.update_install.setEnabled(False)
        self.update_button.setEnabled(False)
        self.update_progress.setVisible(True)
        self.update_progress.setRange(0, 0)
        self.update_status.setText(f"版本 {self.version} · 正在下载 {result.version}…")
        target = Path(tempfile.gettempdir()) / f"MediaDownloadDesk-Setup-{result.version}.exe"
        events = self.update_events

        def progress(received, total):
            events.append(("update_progress", (received, total)))

        def run():
            try:
                path = app_update.download_update(
                    result.asset_url, target, expected_size=result.asset_size,
                    expected_digest=result.asset_digest, on_progress=progress)
            except app_update.UpdateCheckError as error:
                events.append(("update_failed", str(error)))
            else:
                events.append(("update_done", path))

        threading.Thread(target=run, daemon=True).start()

    def _handle_update_events(self):
        from PySide6.QtWidgets import QApplication
        import os

        while self.update_events:
            kind, value = self.update_events.pop(0)
            if kind == "update_error":
                self.update_button.setEnabled(True)
                self.update_status.setText(f"版本 {self.version} · {value}")
            elif kind == "update_result":
                self.update_button.setEnabled(True)
                self.update_result = value
                if value.status == "available":
                    self.update_status.setText(f"版本 {self.version} · 发现新版本 {value.version}")
                    self.update_install.setVisible(bool(value.asset_url))
                    self.update_install.setEnabled(True)
                else:
                    self.update_install.setVisible(False)
                    self.update_status.setText(
                        f"版本 {self.version} · " + ("已是最新版本" if value.status == "current"
                                                     else "GitHub 暂无正式发行版"))
            elif kind == "update_progress":
                received, total = value
                if total:
                    self.update_progress.setRange(0, 100)
                    self.update_progress.setValue(min(100, received * 100 // total))
                    self.update_status.setText(
                        f"版本 {self.version} · 正在下载更新 {received * 100 // total}%"
                        f"（{received // 1048576}/{total // 1048576} MB）")
                else:
                    self.update_status.setText(
                        f"版本 {self.version} · 正在下载更新 {received // 1048576} MB")
            elif kind == "update_failed":
                self.update_busy = False
                self.update_progress.setVisible(False)
                self.update_install.setEnabled(True)
                self.update_button.setEnabled(True)
                self.update_status.setText(f"版本 {self.version} · {value}")
            elif kind == "update_done":
                self.update_busy = False
                self.update_status.setText(f"版本 {self.version} · 正在启动安装程序…")
                try:
                    os.startfile(str(value))
                except OSError as error:
                    self.update_progress.setVisible(False)
                    self.update_install.setEnabled(True)
                    self.update_button.setEnabled(True)
                    self.update_status.setText(f"版本 {self.version} · 无法启动安装程序：{error}")
                    continue
                application = QApplication.instance()
                if application is not None:
                    application.quit()

    def test_network(self):
        import threading

        import net_proxy

        proxy = net_proxy.apply(settings.load())
        self.diag.setText("正在检测出口…" + (f"（代理 {proxy}）" if proxy else "（直连）"))
        self.diag_button.setEnabled(False)
        messages = self.messages

        def run():
            try:
                text = egress_text()
            except Exception as error:
                text = f"网络检测失败：{error}"
            messages.append(text)

        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        while self.messages:
            self.diag.setText(self.messages.pop(0))
            self.diag_button.setEnabled(True)
        self._handle_update_events()

    def _theme_text(self):
        self.theme_button.setText("深色模式" if not self.dark else "浅色模式")

    def toggle_theme(self):
        self.dark = not self.dark
        self._theme_text()
        from qtui.theme import apply_theme
        apply_theme(self.app, self.dark)
        values = settings.load()
        values["dark_mode"] = self.dark
        settings.save(values)


def build_pages(qt_app, core):
    """Return an ordered list of (key, title, widget) pages for the shell."""
    pages = []
    for key, title in PAGES:
        if key == "queue":
            widget = QueuePage(core)
        elif key == "local":
            widget = LocalPage(core)
        elif key == "music":
            from qtui.apple import ApplePage
            widget = ApplePage(core)
        elif key == "youtube":
            from qtui.youtube import YoutubePage
            widget = YoutubePage(core)
        elif key == "bilibili":
            from qtui.bilibili import BilibiliPage
            widget = BilibiliPage(core)
        elif key in ("qq", "netease"):
            from qtui.music import MusicPage
            widget = MusicPage(core, key)
        elif key == "settings":
            widget = SettingsPage(qt_app, settings.load().get("dark_mode", False))
        else:
            widget = PlaceholderPage(title, "此页面正在迁移到新界面，当前版本仍可使用原界面完成该平台操作。")
        pages.append((key, title, widget))
    return pages
