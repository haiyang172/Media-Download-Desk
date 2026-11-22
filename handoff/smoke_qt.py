import os, sys, tempfile, time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
with tempfile.TemporaryDirectory(prefix="amdl-qt-smoke-") as scratch:
    for key in ("LOCALAPPDATA", "APPDATA", "USERPROFILE"):
        os.environ[key] = scratch
    sys.path.insert(0, r"D:\AMDL")
    sys.path.insert(0, r"D:\AMDL\lib")
    import StudioQt
    import settings
    settings.DEFAULTS["auto_service"] = False

    window = StudioQt.build_window(dark=False)
    assert window.windowTitle() == "影音下载台"
    assert list(window.buttons) == ["music", "bilibili", "qq", "netease", "youtube", "douyin",
                                    "queue", "local", "settings"]
    window.show_page("queue")
    window.show_page("settings")
    window.pages["settings"].toggle_theme()
    assert window.pages["settings"].dark is True
    window.pages["settings"].toggle_theme()
    assert window.pages["settings"].dark is False
    for key in ("music", "bilibili", "qq", "netease", "youtube", "douyin", "local"):
        window.show_page(key)
        assert window.stack.currentWidget() is window.pages[key]

    # Functional local conversion through the Qt controller.
    backend = Path(r"D:\AMDL\backend")
    ffmpeg = backend / "tools" / "ffmpeg.exe"
    source = Path(scratch) / "source.m4a"
    import subprocess
    subprocess.run([str(ffmpeg), "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=0.1", "-c:a", "aac", str(source)],
                   check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    out = Path(scratch) / "out"
    out.mkdir()
    ids = window.core.queue_local([str(source)], "mp3", str(out))
    assert len(ids) == 1
    window.core.start(ids)
    deadline = time.monotonic() + 90
    while window.core.busy and time.monotonic() < deadline:
        window.pages["queue"].poll()
        time.sleep(0.05)
    task = window.core.queue_store.get(ids[0])
    assert task.state == "complete", task.error
    assert task.files and Path(task.files[0]).suffix == ".mp3" and Path(task.files[0]).is_file()

    # YouTube page resolve + enqueue via fixture.
    window.core.preferences["folder"] = scratch
    window.core.preferences["category"] = ""
    import qtui.youtube
    from unittest.mock import patch
    fixture = {"source": "youtube", "title": "测试频道", "rows": [
        {"source": "youtube", "id": "abcdefghijk", "url": "https://www.youtube.com/watch?v=abcdefghijk",
         "title": "测试视频", "artist": "测试频道", "position": 1, "total": 1, "duration": 30,
         "batch_key": "youtube:abcdefghijk", "batch_title": "测试频道"}]}
    with patch.object(qtui.youtube, "resolve_youtube", return_value=fixture):
        window.show_page("youtube")
        page = window.pages["youtube"]
        page.entry.setText("https://www.youtube.com/watch?v=abcdefghijk")
        page.resolve()
        deadline = time.monotonic() + 15
        while page.busy and time.monotonic() < deadline:
            page.poll()
            time.sleep(0.02)
        assert len(page.rows) == 1 and page.caption.text() == "测试频道"
        page.table.selectRow(0)
        page.enqueue(False)
    yt_task = [t for t in window.core.list_tasks() if t.url == "https://www.youtube.com/watch?v=abcdefghijk"]
    assert len(yt_task) == 1 and yt_task[0].source == "youtube" and yt_task[0].state == "pending"

    # QQ music page search + enqueue via fixture.
    import qq_catalog
    song_fixture = {"source": "qq", "title": "测试歌手", "total": 1, "rows": [
        {"position": 1, "title": "测试歌曲", "artist": "测试歌手", "album": "测试专辑",
         "duration": 90, "url": "https://y.qq.com/n/ryqq_v2/songDetail/0039MnYb0qxYhV"}]}
    with patch.object(qq_catalog, "search_songs", return_value=song_fixture):
        window.show_page("qq")
        page = window.pages["qq"]
        page.entry.setText("测试歌曲")
        page.resolve()
        deadline = time.monotonic() + 15
        while page.busy and time.monotonic() < deadline:
            page.poll()
            time.sleep(0.02)
        assert len(page.rows) == 1 and page.rows[0]["title"] == "测试歌曲"
        page.table.selectRow(0)
        page.enqueue(False)
    qq_task = [t for t in window.core.list_tasks() if t.url == "https://y.qq.com/n/ryqq_v2/songDetail/0039MnYb0qxYhV"]
    assert len(qq_task) == 1 and qq_task[0].source == "qq" and qq_task[0].state == "pending"

    # Bilibili page resolve + enqueue via fixture.
    import bili_catalog
    bili_fixture = {"id": "BV1xx411c7mD", "title": "测试视频", "uploader": "测试UP",
                    "source_category": "音乐", "media_category": "music",
                    "rows": [{"source": "bilibili", "url": "https://www.bilibili.com/video/BV1xx411c7mD?p=1",
                              "cid": 101, "id": "BV1xx411c7mD", "position": 1, "total": 1,
                              "title": "测试歌曲", "audio_title": "测试歌曲", "artist": "测试歌手",
                              "uploader": "测试UP", "source_category": "音乐", "media_category": "music",
                              "duration": 90, "batch_key": "bilibili:BV1xx411c7mD", "batch_title": "测试视频"}]}
    with patch.object(bili_catalog, "resolve_video", return_value=bili_fixture):
        window.show_page("bilibili")
        page = window.pages["bilibili"]
        page.entry.setText("https://www.bilibili.com/video/BV1xx411c7mD")
        page.resolve()
        deadline = time.monotonic() + 15
        while page.busy and time.monotonic() < deadline:
            page.poll()
            time.sleep(0.02)
        assert len(page.rows) == 1 and page.rows[0]["audio_title"] == "测试歌曲"
        page.table.selectRow(0)
        page.enqueue(False)
    bili_task = [t for t in window.core.list_tasks() if t.url == "https://www.bilibili.com/video/BV1xx411c7mD?p=1"]
    assert len(bili_task) == 1 and bili_task[0].source == "bilibili" and bili_task[0].state == "pending"

    # Apple Music page search + enqueue via fixture.
    from music_catalog import CatalogClient
    apple_fixture = [{"id": "1", "type": "songs", "title": "测试歌曲", "artist": "测试歌手",
                      "album": "测试专辑", "duration": 90, "url": "https://music.apple.com/au/song/1"}]
    with patch.object(CatalogClient, "search", return_value=apple_fixture):
        window.show_page("music")
        page = window.pages["music"]
        page.entry.setText("测试歌曲")
        page.resolve()
        deadline = time.monotonic() + 15
        while page.busy and time.monotonic() < deadline:
            page.poll()
            time.sleep(0.02)
        assert len(page.rows) == 1 and page.rows[0]["title"] == "测试歌曲"
        page.table.selectRow(0)
        page.enqueue(False)
    apple_task = [t for t in window.core.list_tasks() if t.url == "https://music.apple.com/au/song/1"]
    assert len(apple_task) == 1 and apple_task[0].source == "apple_music" and apple_task[0].state == "pending"

    # Qt account dialog: NetEase QR login success saves the session.
    from types import SimpleNamespace
    from netease_auth import NeteaseAuth, NeteaseSession, NeteaseAccount, NeteasePoll
    from qtui.account import MusicAccountDialog
    acct_saved = {}
    acct_qr = SimpleNamespace(url="https://music.163.com/login?codekey=fixture")
    acct_session = NeteaseSession(12345, (("MUSIC_U", "fixture-cookie"),))
    with patch.object(NeteaseAuth, "load", return_value=None), \
         patch.object(NeteaseAuth, "begin", return_value=acct_qr), \
         patch.object(NeteaseAuth, "poll", return_value=NeteasePoll("success", acct_session)), \
         patch.object(NeteaseAuth, "save", side_effect=lambda s: acct_saved.update(session=s)), \
         patch.object(NeteaseAuth, "check", return_value=NeteaseAccount(12345, "测试用户")):
        acct_dialog = MusicAccountDialog(window, "netease")
        assert acct_dialog.polling
        acct_dialog.poll()
        assert acct_dialog.session == acct_session and acct_saved.get("session") == acct_session
        acct_dialog.close()

    # Bilibili account dialog (QR login) saves the session.
    from bili_auth import BiliAuth, BiliSession, BiliAccount, LoginPoll
    bili_saved = {}
    bili_qr = SimpleNamespace(url="https://passport.bilibili.com/h5-app/passport/login/scan?navhide=1")
    bili_session = BiliSession((("SESSDATA", "fixture"),))
    with patch.object(BiliAuth, "load", return_value=None), \
         patch.object(BiliAuth, "begin", return_value=bili_qr), \
         patch.object(BiliAuth, "poll", return_value=LoginPoll("success", bili_session)), \
         patch.object(BiliAuth, "save", side_effect=lambda s: bili_saved.update(session=s)), \
         patch.object(BiliAuth, "check", return_value=BiliAccount(12345, "测试UP")):
        bili_dialog = MusicAccountDialog(window, "bilibili")
        assert bili_dialog.polling
        bili_dialog.poll()
        assert bili_dialog.session == bili_session and bili_saved.get("session") == bili_session
        bili_dialog.close()

    # NetEase cookie login fallback when the QR flow is risk-controlled.
    import netease_auth as na
    with patch.object(NeteaseAuth, "load", return_value=NeteaseSession(12345, (("MUSIC_U", "x"),))), \
         patch.object(NeteaseAuth, "save"), \
         patch.object(na, "_account", return_value=NeteaseAccount(12345, "Cookie用户")):
        cookie_dialog = MusicAccountDialog(window, "netease")
        cookie_dialog.login_with_cookies("MUSIC_U=abc123")
        assert cookie_dialog.session is not None
        cookie_dialog.close()

    # Qt music preview dialog: probe declaration shown and enqueue works.
    import qq_download
    from qtui.preview import MusicPreviewDialog
    preview_row = {"url": "https://y.qq.com/n/ryqq_v2/songDetail/0039MnYb0qyYhW",
                   "title": "预览歌曲", "artist": "预览歌手", "duration": 90}
    declaration = {"source": "qq", "requested": "auto", "selected": None,
                   "label": "平台提供 · MP3 · 320 kb/s", "codec": "MP3", "bitrate": 320000,
                   "size": 1000000, "duration": 90}
    with patch.object(qq_download, "probe_qq", return_value=declaration):
        pv_dialog = MusicPreviewDialog(window, window.core, "qq", preview_row)
        deadline = time.monotonic() + 15
        while pv_dialog.info is None and time.monotonic() < deadline:
            pv_dialog.poll()
            time.sleep(0.02)
        assert pv_dialog.info == declaration
        assert "MP3" in pv_dialog.source_info.text()
        pv_dialog.enqueue()
    pv_task = [t for t in window.core.list_tasks() if t.url == "https://y.qq.com/n/ryqq_v2/songDetail/0039MnYb0qyYhW"]
    assert len(pv_task) == 1 and pv_task[0].source == "qq" and pv_task[0].state == "pending"
    pv_dialog.close()

    # QQ personal playlists: list, open and enqueue a private track.
    from qq_auth import QqAuth, QqSession
    qq_session = QqSession("fixture1234", "fixture-key", "Fixture")
    playlist = {"id": "42", "title": "QQ 测试歌单", "kind": "created", "total": 1,
                "url": "", "private": True, "_account_id": "fixture1234"}
    tracks_result = {"source": "qq", "title": playlist["title"], "total": 1, "rows": [
        {"position": 1, "title": "私密歌曲", "artist": "歌手", "duration": 90,
         "url": "https://y.qq.com/n/ryqq_v2/songDetail/0039MnYb0qyYhZ"}]}
    with patch.object(QqAuth, "load", return_value=qq_session), \
         patch.object(qq_catalog, "list_playlists", return_value={"source": "qq", "rows": [playlist], "total": 1}), \
         patch.object(qq_catalog, "resolve_playlist", return_value=tracks_result):
        window.show_page("qq")
        page = window.pages["qq"]
        page.show_playlists()
        deadline = time.monotonic() + 15
        while page.busy and time.monotonic() < deadline:
            page.poll()
            time.sleep(0.02)
        assert page.playlist_view and len(page.rows) == 1
        page.table.selectRow(0)
        page.open_playlist()
        deadline = time.monotonic() + 15
        while page.busy and time.monotonic() < deadline:
            page.poll()
            time.sleep(0.02)
        assert not page.playlist_view and len(page.rows) == 1 and page.rows[0]["title"] == "私密歌曲"
        page.table.selectRow(0)
        page.enqueue(False)
    qq_priv_task = [t for t in window.core.list_tasks() if t.url == "https://y.qq.com/n/ryqq_v2/songDetail/0039MnYb0qyYhZ"]
    assert len(qq_priv_task) == 1 and qq_priv_task[0].source == "qq" and qq_priv_task[0].state == "pending"

    # Bilibili personal favorites: list, open a folder and enqueue a video.
    import bili_collections
    from bili_auth import BiliAuth, BiliSession, BiliAccount
    bili_session2 = BiliSession((("SESSDATA", "fixture"), ("DedeUserID", "12345")))
    bili_account = BiliAccount(12345, "测试UP")
    folder = {"id": "favorite:4242", "collection_id": "4242", "kind": "favorite", "owner_id": "12345",
              "title": "驾驶音乐", "total": 1, "url": "https://space.bilibili.com/12345/favlist?fid=4242",
              "_account_id": "12345"}
    favorites_result = {"source": "bilibili", "view": "favorites", "title": "我的收藏夹", "_account_id": "12345",
                        "rows": [folder], "total": 1, "complete": True, "warning": ""}
    folder_result = {"source": "bilibili", "title": "驾驶音乐", "total": 1, "rows": [
        {"source": "bilibili", "url": "https://www.bilibili.com/video/BV1yy411c7mE?p=1", "cid": 102,
         "id": "BV1yy411c7mE", "position": 1, "total": 1, "title": "收藏视频", "audio_title": "收藏视频",
         "artist": "收藏UP", "uploader": "收藏UP", "source_category": "音乐", "media_category": "music",
         "duration": 90, "batch_key": "bilibili:BV1yy411c7mE", "batch_title": "驾驶音乐"}]}
    with patch.object(BiliAuth, "load", return_value=bili_session2), \
         patch.object(BiliAuth, "check", return_value=bili_account), \
         patch.object(bili_collections, "list_my_favorites", return_value=favorites_result), \
         patch.object(bili_collections, "resolve_my_favorite", return_value=folder_result):
        window.show_page("bilibili")
        bpage = window.pages["bilibili"]
        bpage.show_favorites()
        deadline = time.monotonic() + 15
        while bpage.busy and time.monotonic() < deadline:
            bpage.poll()
            time.sleep(0.02)
        assert bpage.favorites_view and len(bpage.rows) == 1
        bpage.table.selectRow(0)
        bpage.open_folder()
        deadline = time.monotonic() + 15
        while bpage.busy and time.monotonic() < deadline:
            bpage.poll()
            time.sleep(0.02)
        assert not bpage.favorites_view and len(bpage.rows) == 1 and bpage.rows[0]["audio_title"] == "收藏视频"
        bpage.table.selectRow(0)
        bpage.enqueue(False)
    fav_task = [t for t in window.core.list_tasks() if t.url == "https://www.bilibili.com/video/BV1yy411c7mE?p=1"]
    assert len(fav_task) == 1 and fav_task[0].source == "bilibili" and fav_task[0].state == "pending"

    # Apple account dialog: login form drives the shared LoginService.
    from login_service import LoginService
    from qtui.apple_account import AppleAccountDialog
    with patch.object(LoginService, "status", return_value={"running": True, "logged_in": False}), \
         patch.object(LoginService, "login", return_value={"logged_in": True, "needs_code": False}):
        ap_dialog = AppleAccountDialog(window, window.core)
        ap_dialog.username.setText("test@example.com")
        ap_dialog.password.setText("secret")
        ap_dialog.login()
        deadline = time.monotonic() + 15
        while ap_dialog.busy and time.monotonic() < deadline:
            ap_dialog.poll()
            time.sleep(0.02)
        assert "已登录" in ap_dialog.status.text()
        ap_dialog.close()

    # Apple library: connected token lists personal songs and queues one.
    from music_library import LibraryClient
    from qtui.library import AppleLibraryDialog
    window.core.preferences["session"] = settings.protect_session("x" * 60)
    library_fixture = [{"id": "1", "type": "songs", "title": "资料库歌曲", "artist": "资料库歌手",
                        "album": "资料库专辑", "duration": 90,
                        "url": "https://music.apple.com/au/song/1"}]
    with patch.object(LibraryClient, "items", return_value=(library_fixture, None)):
        lib_dialog = AppleLibraryDialog(window, window.core)
        lib_dialog.load_songs()
        deadline = time.monotonic() + 15
        while lib_dialog.busy and time.monotonic() < deadline:
            lib_dialog.poll()
            time.sleep(0.02)
        assert len(lib_dialog.rows) == 1 and lib_dialog.rows[0]["title"] == "资料库歌曲"
        lib_dialog.table.selectRow(0)
        lib_dialog.enqueue()
    lib_task = [t for t in window.core.list_tasks() if t.url == "https://music.apple.com/au/song/1"]
    assert len(lib_task) == 1 and lib_task[0].source == "apple_music"
    lib_dialog.close()

    # Settings page saves the download configuration.
    import audio
    window.show_page("settings")
    settings_page = window.pages["settings"]
    settings_page.folder.setText(scratch)
    settings_page.category.setText("测试分类")
    settings_page.proxy.setText("http://127.0.0.1:7890")
    settings_page.save()
    saved = settings.load()
    assert (saved["folder"], saved["category"]) == (scratch, "测试分类")
    assert saved["ui_mode"] == "qt" and saved["proxy"] == "http://127.0.0.1:7890"

    # Conversion defaults now live on the local page and save immediately.
    window.show_page("local")
    local_page = window.pages["local"]
    local_page.default_output.setCurrentText(audio.OUTPUTS["mp3"])
    local_page.mp3_bitrate.setCurrentText("192")
    saved = settings.load()
    assert (saved["output"], saved["mp3_bitrate"]) == ("mp3", 192)
    import net_proxy
    settings_page.proxy.setText("")
    settings_page.save()
    assert net_proxy.apply(settings.load()) == ""
    assert "HTTPS_PROXY" not in os.environ

    # Update check exposes the release asset and reports download failures.
    from qtui import pages as qt_pages_module
    with patch.object(qt_pages_module.app_update, "check_update",
                      return_value=qt_pages_module.app_update.UpdateCheck(
                          "available", "9.9.9", "https://example.invalid/tag",
                          "https://example.invalid/setup.exe", 10, "0" * 64)):
        settings_page.check_updates()
        deadline = time.monotonic() + 15
        while not settings_page.update_events and time.monotonic() < deadline:
            settings_page.poll()
            time.sleep(0.02)
        settings_page.poll()
        assert "发现新版本" in settings_page.update_status.text()
        assert not settings_page.update_install.isHidden()
    with patch.object(qt_pages_module.app_update, "download_update",
                      side_effect=qt_pages_module.app_update.UpdateCheckError("下载失败测试")):
        settings_page.install_update()
        deadline = time.monotonic() + 15
        while not settings_page.update_events and time.monotonic() < deadline:
            settings_page.poll()
            time.sleep(0.02)
        settings_page.poll()
        assert "下载失败测试" in settings_page.update_status.text()

    # 设置页的网络诊断显示出口信息。
    import qtui.pages as qt_pages
    with patch.object(qt_pages, "egress_text", return_value="出口 1.2.3.4 · 中国 深圳 · 电信"):
        settings_page.test_network()
        deadline = time.monotonic() + 15
        while not settings_page.messages and time.monotonic() < deadline:
            settings_page.poll()
            time.sleep(0.02)
        settings_page.poll()
        assert "1.2.3.4" in settings_page.diag.text()

    # Launch dispatch defaults to Qt and can switch to Tkinter.
    import Studio
    assert Studio._launch_ui() == "qt"
    settings.save({**settings.load(), "ui_mode": "tkinter"})
    assert Studio._launch_ui() == "tkinter"
    settings.save({**settings.load(), "ui_mode": "qt"})
    assert Studio._launch_ui() == "qt"

    # 队列：任务详情、筛选、导出与重新排队。
    import qtui.pages as qp
    window.show_page("queue")
    qpage = window.pages["queue"]
    qpage.refresh()
    assert qpage.table.rowCount() >= 1
    qpage.table.selectRow(0)
    captured = {}
    def fake_exec(dialog):
        captured["text"] = dialog.body.toPlainText()
        return 0
    with patch.object(qp.TaskDetailsDialog, "exec", fake_exec):
        qpage.show_details()
    assert captured.get("text"), "task details dialog did not render"
    qpage.filter_box.setCurrentIndex(1)
    qpage.refresh()
    source = qpage.filter_box.currentData()
    assert source and all(task.source == source for task in qpage.tasks.values())
    qpage.filter_box.setCurrentIndex(0)
    qpage.refresh()
    qpage.export_playlist()
    assert "已保存的文件" in qpage.status.text()
    remote_row = next((row for row, task in qpage.tasks.items() if task.source != "local"), None)
    assert remote_row is not None
    qpage.table.selectRow(remote_row)
    qpage.requeue_selected()
    assert "重新排队" in qpage.status.text()

    # 本地转码页的去重审阅：扫描、标记并删除重复。
    from qtui.dedup import DedupReviewDialog
    dup_root = Path(scratch) / "dedup"
    dup_root.mkdir()
    payload = os.urandom(4096)
    (dup_root / "a.mp3").write_bytes(payload)
    (dup_root / "b.mp3").write_bytes(payload)
    dedup = DedupReviewDialog(window)
    dedup._set_folder(str(dup_root))
    dedup.scan()
    deadline = time.monotonic() + 20
    while dedup.busy and time.monotonic() < deadline:
        dedup.poll()
        time.sleep(0.02)
    assert len(dedup.rows) == 2 and "1 个可删除" in dedup.summary.text()
    dedup.remove_marked()
    deadline = time.monotonic() + 20
    while dedup.busy and time.monotonic() < deadline:
        dedup.poll()
        time.sleep(0.02)
    dedup.poll()
    remaining = [path for path in dup_root.iterdir()]
    assert len(remaining) == 1, remaining
    dedup.close()

    # 追更新歌：打开过的歌单再检查时没有新增。
    watch_page = window.pages["qq"]
    window.show_page("qq")
    watch_page.watch_playlist()
    assert "没有新增" in watch_page.status.text() or "已加入" in watch_page.status.text()

    # B 站下载预览：改名并按所选内容入队。
    from qtui.bili_preview import BiliPreviewDialog
    preview_row = {"source": "bilibili", "url": "https://www.bilibili.com/video/BV1aa411c7mF?p=1",
                   "id": "BV1aa411c7mF", "cid": 9001, "title": "预览视频", "audio_title": "预览视频",
                   "artist": "UP 主", "uploader": "UP 主", "duration": 95, "position": 1, "total": 1,
                   "batch_key": "bilibili:BV1aa411c7mF", "batch_title": "预览视频"}
    preview = BiliPreviewDialog(window, window.core, [preview_row])
    preview.title.setText("改过的歌名")
    preview.mode.setCurrentText(qp.BILI_FORMATS["flac"])
    preview.confirm(False)
    preview_task = [t for t in window.core.list_tasks()
                    if t.url == "https://www.bilibili.com/video/BV1aa411c7mF?p=1"]
    assert len(preview_task) == 1 and preview_task[0].audio_title == "改过的歌名"
    assert preview_task[0].options["bili_mode"] == "flac"

    # 拖拽文件到窗口会把它们加进本地转码。
    class _Url:
        def __init__(self, path):
            self.path = path
        def isLocalFile(self):
            return True
        def toLocalFile(self):
            return self.path

    class _Mime:
        def urls(self):
            return [_Url(str(dup_root / remaining[0].name))]
    class _Event:
        def mimeData(self):
            return _Mime()
        def acceptProposedAction(self):
            pass

    local_page = window.pages["local"]
    before = len(local_page.files)
    window.dropEvent(_Event())
    assert len(local_page.files) == before + 1

    # Apple 资料库：双击专辑/歌单展开曲目。
    library_rows = [{"id": "1", "type": "playlist", "title": "资料库歌单", "artist": "",
                     "album": "", "duration": 0, "url": "", "library_id": "p.1", "expandable": True}]
    tracks_fixture = [{"id": "2", "type": "songs", "title": "歌单曲目", "artist": "歌手",
                       "album": "专辑", "duration": 60, "url": "https://music.apple.com/au/song/2"}]
    window.core.preferences["session"] = settings.protect_session("y" * 60)
    with patch.object(LibraryClient, "tracks", return_value=(tracks_fixture, None)):
        lib = AppleLibraryDialog(window, window.core)
        lib._fill(library_rows)
        lib.table.selectRow(0)
        lib.open_collection()
        deadline = time.monotonic() + 15
        while lib.busy and time.monotonic() < deadline:
            lib.poll()
            time.sleep(0.02)
        lib.poll()
        assert len(lib.rows) == 1 and lib.rows[0]["title"] == "歌单曲目"
        lib.close()

    print("Qt shell smoke OK: nav, queue, theme, local conversion, YouTube, QQ, Bilibili, Apple, account, preview, "
          "playlists, favorites, Apple login, library, settings, queue actions, dedup, watch, bili preview, "
          "drag and drop and library expansion passed.")
    window.core.close()
    window.close()
