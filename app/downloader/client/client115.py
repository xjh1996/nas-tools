import os
import posixpath

import log
from app.downloader.client._base import _IDownloadClient
from app.downloader.client.pan115_base import Pan115Provider
from app.downloader.client.pan115_models import TASK_DISPLAY_STATE, Pan115ProviderType
from app.downloader.client.pan115_open import Pan115OpenProvider
from app.downloader.client.pan115_session import Pan115SessionProvider
from app.utils import StringUtils
from app.utils.types import DownloaderType
from config import Config


class Client115(_IDownloadClient):
    schema = "client115"
    client_type = DownloaderType.Client115.value
    _client_config = {}

    downclient = None
    lasthash = None
    _persist_config = False
    _task_list_max_pages = 1
    _transfer_roots = []

    def __init__(self, config=None):
        if config:
            self._client_config = config
            self._persist_config = False
        else:
            self._client_config = Config().get_config("client115")
            self._persist_config = True
        self.init_config()
        self.connect()

    def init_config(self):
        if self._client_config:
            provider_type = Pan115Provider.resolve_provider_type(self._client_config)
            provider_cls = self._get_provider_cls(provider_type)
            self._task_list_max_pages = self._safe_int(self._client_config.get("task_list_max_pages"), 1)
            self._transfer_roots = self._resolve_transfer_roots()
            self.downclient = provider_cls(self._client_config, persist=self._persist_config)

    @staticmethod
    def _safe_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _get_provider_cls(provider_type):
        # Session is the supported path. Open remains a research placeholder.
        if provider_type == Pan115ProviderType.OPEN:
            return Pan115OpenProvider
        return Pan115SessionProvider

    @classmethod
    def match(cls, ctype):
        return True if ctype in [cls.schema, cls.client_type] else False

    def connect(self):
        if self.downclient:
            self.downclient.login()

    def get_status(self):
        if not self.downclient:
            return False
        ret = self.downclient.ensure_login()
        if not ret:
            log.info(self.downclient.err)
            return False
        return True

    def get_torrents(self, ids=None, status=None, **kwargs):
        tlist = []
        if not self.downclient:
            return tlist
        ret, tasks = self.downclient.gettasklist(page=1, max_pages=self._task_list_max_pages)
        if not ret:
            log.info(f"【{self.client_type}】获取任务列表错误：{self.downclient.err}")
            return tlist
        for task in tasks or []:
            task = self.downclient.normalize_task(task)
            if ids and task.get("info_hash") not in ids:
                continue
            if status and task.get("status") not in status:
                continue
            lookup_id = task.get("dir_id") or task.get("wp_path_id") or task.get("file_id")
            if lookup_id:
                ok, task_dir = self.downclient.getiddir(lookup_id)
                if ok:
                    task["path"] = task_dir
            tlist.append(task)
        return tlist or []

    def get_completed_torrents(self, **kwargs):
        return self.get_torrents(status=[2], **kwargs)

    def get_downloading_torrents(self, **kwargs):
        return self.get_torrents(status=[0, 1], **kwargs)

    def get_failed_torrents(self, **kwargs):
        return self.get_torrents(status=[-1], **kwargs)

    def remove_torrents_tag(self, **kwargs):
        return False

    def get_transfer_task(self, **kwargs):
        torrents = self.get_completed_torrents(**kwargs)
        trans_tasks = []
        for torrent in torrents:
            path = torrent.get("path")
            name = torrent.get("name")
            task_id = torrent.get("info_hash")
            if not path or not name or not task_id:
                continue
            if not self._is_transfer_path(path):
                log.debug(f"【{self.client_type}】跳过非下载目录任务：{path}/{name}")
                continue
            true_path = self.get_replace_path(path)
            trans_tasks.append({
                "path": os.path.join(true_path, name).replace("\\", "/"),
                "id": task_id
            })
        return trans_tasks

    def get_remove_torrents(self, **kwargs):
        return []

    def add_torrent(self, content, download_dir=None, **kwargs):
        if not self.downclient:
            return False
        if not isinstance(content, str):
            log.info(f"【{self.client_type}】暂不支持非链接下载")
            return None
        ret, self.lasthash = self.downclient.addtask_urls(content=content, download_dir=download_dir)
        if not ret:
            log.error(f"【{self.client_type}】添加下载任务失败：{self.downclient.err}")
            return None
        return self.lasthash

    def delete_torrents(self, delete_file, ids):
        if not self.downclient:
            return False
        return self.downclient.deltask(thash=ids)

    def start_torrents(self, ids):
        return False

    def stop_torrents(self, ids):
        return False

    def set_torrents_status(self, ids, **kwargs):
        # 115 offline tasks do not support qB/TR style tags or status labels.
        # Treating "mark as processed" as "delete task" can remove unrelated
        # cloud tasks when a transfer attempt fails, so keep this intentionally
        # non-destructive.
        log.info(f"【{self.client_type}】不支持设置任务标签/状态，跳过任务状态更新：{ids}")
        return False

    def get_download_dirs(self):
        return []

    def _resolve_transfer_roots(self):
        roots = []
        for path in [
            self._client_config.get("remote_download_path"),
            self._client_config.get("download_path")
        ]:
            root = self._normalize_remote_path(path)
            if root and root != "/" and root not in roots:
                roots.append(root)
        for attr in Config().get_config('downloaddir') or []:
            root = self._normalize_remote_path(attr.get("save_path"))
            if root and root != "/" and root not in roots:
                roots.append(root)
        return roots

    @classmethod
    def _normalize_remote_path(cls, path):
        path = (path or "").replace("\\", "/").strip()
        if not path:
            return ""
        if not path.startswith("/"):
            path = "/%s" % path
        if path == "/根目录":
            path = "/"
        elif path.startswith("/根目录/"):
            path = path[len("/根目录"):]
        return posixpath.normpath(path) if path != "/" else "/"

    def _is_transfer_path(self, path):
        if not self._transfer_roots:
            return True
        normalized_path = self._normalize_remote_path(path)
        for root in self._transfer_roots:
            if normalized_path == root or normalized_path.startswith("%s/" % root.rstrip("/")):
                return True
        return False

    def change_torrent(self, **kwargs):
        return False

    def get_downloading_progress(self, **kwargs):
        torrents = self.get_downloading_torrents(**kwargs)
        display_torrents = []
        for torrent in torrents:
            progress = round(torrent.get("percentDone"), 1)
            state = TASK_DISPLAY_STATE.get(torrent.get("status_name"), "Downloading")
            down_speed = StringUtils.str_filesize(torrent.get("rateDownload"))
            up_speed = StringUtils.str_filesize(torrent.get("rateUpload"))
            speed = "%s%sB/s %s%sB/s" % (chr(8595), down_speed, chr(8593), up_speed)
            display_torrents.append({
                "id": torrent.get("info_hash"),
                "name": torrent.get("name"),
                "speed": speed,
                "state": state,
                "progress": progress
            })
        return display_torrents

    def set_speed_limit(self, **kwargs):
        return False
