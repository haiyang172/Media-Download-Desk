import hashlib
import http.server
import os
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, r"D:\AMDL")
sys.path.insert(0, r"D:\AMDL\lib")

import app_update

payload = os.urandom(600 * 1024)
expected = hashlib.sha256(payload).hexdigest()

with tempfile.TemporaryDirectory(prefix="amdl-update-src-") as source:
    serve = Path(source) / "MediaDownloadDesk-Setup.exe"
    serve.write_bytes(payload)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=source, **kwargs)

        def log_message(self, *args):
            pass

    httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/MediaDownloadDesk-Setup.exe"
    target = Path(tempfile.mkdtemp(prefix="amdl-update-dst-")) / "out.exe"
    seen = []

    path = app_update.download_update(url, target, expected_size=len(payload),
                                      expected_digest=expected,
                                      on_progress=lambda r, t: seen.append((r, t)))
    assert path.read_bytes() == payload, "content mismatch"
    assert seen and seen[-1][0] == len(payload), "progress not reported"
    assert not target.with_name(target.name + ".part").exists(), "part file left behind"
    print(f"download OK: {len(payload)} bytes, {len(seen)} progress updates")

    try:
        app_update.download_update(url, target, expected_size=len(payload) + 1)
    except app_update.UpdateCheckError as error:
        print("size mismatch rejected:", error)
    else:
        raise AssertionError("size mismatch accepted")

    try:
        app_update.download_update(url, target, expected_digest="0" * 64)
    except app_update.UpdateCheckError as error:
        print("digest mismatch rejected:", error)
    else:
        raise AssertionError("digest mismatch accepted")

    stop = threading.Event()
    stop.set()
    try:
        app_update.download_update(url, target, stop=stop)
    except app_update.Cancelled:
        print("cancel honoured")
    else:
        raise AssertionError("cancel ignored")

    httpd.shutdown()
    for leftover in Path(tempfile.gettempdir()).glob("amdl-update-dst-*"):
        pass
print("update download probe OK")
