"""Check the project's public GitHub Releases and install a newer stable version."""

from dataclasses import dataclass
from hashlib import sha256
from http.client import HTTPException
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


REPOSITORY = "haiyang172/Media-Download-Desk"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
_LATEST_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
_MAX_RELEASE_BYTES = 1024 * 1024
_ASSET_NAME = "MediaDownloadDesk-Setup.exe"
_CHUNK = 256 * 1024
_NUMBER = r"(0|[1-9][0-9]*)"
_VERSION = re.compile(rf"v?{_NUMBER}\.{_NUMBER}\.{_NUMBER}(?:\.{_NUMBER})?")


class UpdateCheckError(RuntimeError):
    """The public release could not be checked this time."""


@dataclass(frozen=True)
class UpdateCheck:
    status: str
    version: str | None = None
    url: str | None = None
    asset_url: str | None = None
    asset_size: int | None = None
    asset_digest: str | None = None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _version_key(version):
    if isinstance(version, str) and len(version) <= 64 and (match := _VERSION.fullmatch(version)):
        return tuple(int(part or 0) for part in match.groups())
    return None


def check_update(current_version):
    """Return available/current/unreleased after reading the public release metadata."""
    current = _version_key(current_version)
    if current is None:
        raise UpdateCheckError("无法识别当前程序版本。")

    request = Request(_LATEST_API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"MediaDownloadDesk/{current_version}",
    })
    payload = None
    for attempt in range(2):
        try:
            # Follow redirects so a renamed repository still resolves.
            with build_opener().open(request, timeout=15) as response:
                payload = response.read(_MAX_RELEASE_BYTES + 1)
            break
        except HTTPError as error:
            status = error.code
            headers = error.headers or {}
            error.close()
            if status == 404:
                return UpdateCheck("unreleased")
            if status == 429 or status == 403:
                if headers.get("X-RateLimit-Remaining") == "0" or headers.get("Retry-After"):
                    raise UpdateCheckError("GitHub 更新查询过于频繁，请稍后再试。") from None
                raise UpdateCheckError(f"GitHub 拒绝了更新查询（HTTP {status}），请稍后再试。") from None
            raise UpdateCheckError(f"暂时无法读取 GitHub 版本信息（HTTP {status}）。") from None
        except (OSError, HTTPException):
            if attempt == 0:
                continue
            raise UpdateCheckError("暂时无法连接 GitHub 检查更新。") from None
    if payload is None:
        raise UpdateCheckError("暂时无法连接 GitHub 检查更新。")

    if len(payload) > _MAX_RELEASE_BYTES:
        raise UpdateCheckError("GitHub 返回的版本信息过大。")
    try:
        release = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        raise UpdateCheckError("GitHub 返回的版本信息无法读取。") from None
    if (not isinstance(release, dict) or not isinstance(release.get("tag_name"), str)
            or not isinstance(release.get("draft"), bool) or not isinstance(release.get("prerelease"), bool)):
        raise UpdateCheckError("GitHub 返回的版本信息不完整。")

    tag = release["tag_name"]
    remote = _version_key(tag)
    if release["draft"] or release["prerelease"] or remote is None:
        return UpdateCheck("unreleased")
    version = tag.removeprefix("v")
    if remote <= current:
        return UpdateCheck("current", version)
    asset_url = asset_size = asset_digest = None
    assets = release.get("assets")
    if isinstance(assets, list):
        chosen = next((item for item in assets if isinstance(item, dict) and item.get("name") == _ASSET_NAME), None)
        if chosen is not None:
            url, size, digest = chosen.get("browser_download_url"), chosen.get("size"), chosen.get("digest")
            if isinstance(url, str) and url.startswith("https://") and type(size) is int and size > 0:
                asset_url = url
                asset_size = size
                if isinstance(digest, str) and digest.startswith("sha256:"):
                    asset_digest = digest.removeprefix("sha256:")
    return UpdateCheck("available", version, f"{RELEASES_URL}/tag/{tag}", asset_url, asset_size, asset_digest)


class Cancelled(RuntimeError):
    """The download was stopped by the caller."""


def download_update(asset_url, target, *, expected_size=None, expected_digest=None, stop=None, on_progress=None):
    """Stream the release installer to target, verifying size and digest when given."""
    if not isinstance(asset_url, str) or not asset_url.lower().startswith(("https://", "http://")):
        raise UpdateCheckError("没有可下载的更新安装包。")
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    digest = sha256(usedforsecurity=False)
    received = 0
    request = Request(asset_url, headers={"User-Agent": f"MediaDownloadDesk/{_ASSET_NAME}",
                                          "Accept-Encoding": "identity"})
    try:
        with build_opener().open(request, timeout=60) as response:
            total = response.headers.get("Content-Length")
            total = int(total) if isinstance(total, str) and total.isdigit() else expected_size
            with partial.open("wb") as stream:
                while True:
                    if stop is not None and stop.is_set():
                        raise Cancelled("已取消下载更新。")
                    chunk = response.read1(_CHUNK)
                    if not chunk:
                        break
                    stream.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    if on_progress is not None:
                        on_progress(received, total)
    except Cancelled:
        partial.unlink(missing_ok=True)
        raise
    except HTTPError as error:
        error.close()
        partial.unlink(missing_ok=True)
        raise UpdateCheckError(f"下载更新失败（HTTP {error.code}），请稍后重试。") from None
    except (OSError, HTTPException):
        partial.unlink(missing_ok=True)
        raise UpdateCheckError("下载更新失败，请检查网络后重试。") from None
    if expected_size is not None and received != expected_size:
        partial.unlink(missing_ok=True)
        raise UpdateCheckError("更新安装包大小不完整，请重试。")
    if expected_digest is not None and digest.hexdigest().lower() != expected_digest.lower():
        partial.unlink(missing_ok=True)
        raise UpdateCheckError("更新安装包校验失败，请重试。")
    partial.replace(target)
    return target
