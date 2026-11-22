"""Qt 下载预览：确认 B 站音轨/画质与保存格式后再入队。"""

from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout)

import audio
from apple_download import download_options

MODES = {"video": "视频 · MP4", "audio": "音频 · M4A", "flac": "音频 · 原始 FLAC", "mp3": "音频 · MP3"}


class BiliPreviewDialog(QDialog):
    def __init__(self, parent, core, rows):
        super().__init__(parent)
        self.core = core
        self.rows = [dict(row) for row in rows]
        self.setWindowTitle("下载预览")
        self.resize(460, 380)
        first = self.rows[0]
        preferences = core.preferences

        layout = QVBoxLayout(self)
        heading = QLabel(f"共 {len(self.rows)} 个分 P" if len(self.rows) > 1 else "下载预览")
        heading.setStyleSheet("font-size: 17px; font-weight: bold;")
        layout.addWidget(heading)

        layout.addWidget(QLabel("歌名"))
        self.title = QLineEdit(first.get("audio_title") or first.get("title", ""))
        layout.addWidget(self.title)
        layout.addWidget(QLabel("歌手 / 投稿者"))
        self.artist = QLineEdit(first.get("artist") or first.get("uploader", ""))
        layout.addWidget(self.artist)

        layout.addWidget(QLabel("保存内容"))
        self.mode = QComboBox()
        self.mode.addItems(list(MODES.values()))
        self.mode.setCurrentText(MODES.get(preferences.get("bili_mode", "video"), MODES["video"]))
        layout.addWidget(self.mode)

        layout.addWidget(QLabel("保存格式"))
        self.output = QComboBox()
        self.output.addItems(list(audio.OUTPUTS.values()))
        self.output.setCurrentText(
            audio.OUTPUTS.get(preferences.get("bili_output", "original"), "保留原音轨"))
        layout.addWidget(self.output)

        layout.addWidget(QLabel("MP3 码率"))
        self.bitrate = QComboBox()
        self.bitrate.addItems([str(value) for value in audio.MP3_BITRATES])
        self.bitrate.setCurrentText(str(preferences.get("mp3_bitrate", audio.DEFAULT_MP3_BITRATE)))
        layout.addWidget(self.bitrate)

        self.spec = QLabel(self._describe(first))
        self.spec.setWordWrap(True)
        self.spec.setProperty("muted", True)
        layout.addWidget(self.spec)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        foot = QHBoxLayout()
        foot.addStretch(1)
        self.queue_button = QPushButton("加入队列")
        self.queue_button.clicked.connect(lambda: self.confirm(False))
        foot.addWidget(self.queue_button)
        self.download_button = QPushButton("下载")
        self.download_button.clicked.connect(lambda: self.confirm(True))
        foot.addWidget(self.download_button)
        close = QPushButton("取消")
        close.clicked.connect(self.close)
        foot.addWidget(close)
        layout.addLayout(foot)

    @staticmethod
    def _describe(row):
        parts = []
        duration = row.get("duration")
        if isinstance(duration, (int, float)) and duration > 0:
            minutes, seconds = divmod(int(round(duration)), 60)
            parts.append(f"时长 {minutes}:{seconds:02d}")
        if row.get("source_category"):
            parts.append(str(row["source_category"]))
        kind = row.get("media_category")
        if kind:
            parts.append("音频" if kind == "music" else "视频")
        return " · ".join(parts) or "已读取平台信息"

    def confirm(self, begin):
        mode = next((key for key, label in MODES.items() if label == self.mode.currentText()), "video")
        output = next((key for key, label in audio.OUTPUTS.items()
                       if label == self.output.currentText()), "original")
        try:
            bitrate = int(self.bitrate.currentText())
        except ValueError:
            bitrate = audio.DEFAULT_MP3_BITRATE
        options = download_options(self.core.preferences)
        options.update(bili_mode=mode, bili_output=output, mp3_bitrate=bitrate)
        title = self.title.text().strip()
        artist = self.artist.text().strip()
        prepared = []
        for row in self.rows:
            item = dict(row)
            if title:
                item["audio_title"] = title
                item["title"] = title
            if artist:
                item["artist"] = artist
                item["uploader"] = artist
            item["song_edited"] = True
            item["options"] = dict(options)
            prepared.append(item)
        try:
            ids = self.core.enqueue(prepared)
            if begin:
                self.core.start(ids)
        except (OSError, RuntimeError, ValueError) as error:
            self.status.setText(str(error))
            return
        self.status.setText(f"已加入队列 {len(ids)} 项" + ("并开始下载" if begin else ""))
        self.close()
