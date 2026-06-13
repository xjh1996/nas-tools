import os
import posixpath

import log
from app.downloader.client._base import _IDownloadClient
from app.downloader.client.pan115_base import Pan115Provider
from app.downloader.client.pan115_models import TASK_DISPLAY_STATE, Pan115ProviderType
from app.downloader.client.pan115_open import Pan115OpenProvider
from app.downloader.client.pan115_session import Pan115SessionProvider
from app.utils import StringUtils
from app.utils.types import DownloaderType, MediaType, RmtMode
from config import Config, RMT_MEDIAEXT


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
            remote_path = posixpath.join(self._normalize_remote_path(path), name).replace("\\", "/")
            true_path = self.get_replace_path(path)
            trans_tasks.append({
                "path": os.path.join(true_path, name).replace("\\", "/"),
                "remote_path": remote_path,
                "id": task_id,
                "preserve_task": True
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

    def transfer_media_task(self, task, rmt_mode=None):
        if rmt_mode != RmtMode.MOVE:
            return None
        local_path = task.get("path")
        remote_path = task.get("remote_path")
        if not local_path or not remote_path:
            return None

        from app.downloader.client.pan115_service import get_pan115_remote_fs
        from app.filetransfer import FileTransfer
        from app.mediaserver import MediaServer

        filetransfer = FileTransfer()
        remote_fs = get_pan115_remote_fs(config=self._client_config, persist=self._persist_config)
        local_files = self._get_local_media_files(local_path, filetransfer._min_filesize)
        if not local_files:
            return False, "目录下未找到媒体文件"
        medias = filetransfer.media.get_media_info_on_files(local_files)
        if not medias:
            return False, "检索媒体信息出错"

        failed = []
        moved = []
        for local_file, media in medias.items():
            if not media or not media.tmdb_info or not media.get_title_string():
                failed.append("%s 无法识别媒体信息" % os.path.basename(local_file))
                continue
            source_path = self._local_to_remote_path(local_file) or self._join_remote_child(remote_path, local_file, local_path)
            target_path = self._build_remote_target_path(filetransfer, media, local_path, local_file)
            if not target_path:
                failed.append("%s 目的路径不存在" % os.path.basename(local_file))
                continue
            ok, plan = remote_fs.move_path(source_path, target_path, execute=True, overwrite=filetransfer._filesize_cover)
            if not ok:
                failed.append(plan.get("error") or remote_fs.err or ("%s 移动失败" % os.path.basename(local_file)))
                continue
            moved.append(plan)

        if moved and filetransfer._refresh_mediaserver:
            MediaServer().refresh_root_library()
        if failed:
            return False, "；".join(failed)
        return True, ""

    def _get_local_media_files(self, path, min_filesize):
        from app.utils import PathUtils

        if os.path.isdir(path):
            return PathUtils.get_dir_files(in_path=path, exts=RMT_MEDIAEXT, filesize=min_filesize)
        if os.path.isfile(path) and os.path.splitext(path)[-1].lower() in RMT_MEDIAEXT:
            return [path]
        return []

    def _join_remote_child(self, remote_root, local_file, local_root):
        rel_path = os.path.relpath(local_file, local_root).replace("\\", "/")
        if rel_path == ".":
            return self._normalize_remote_path(remote_root)
        return posixpath.join(self._normalize_remote_path(remote_root), rel_path)

    def _build_remote_target_path(self, filetransfer, media, local_root, local_file):
        media.size = os.path.getsize(local_file)
        dest = filetransfer._FileTransfer__get_best_target_path(mtype=media.type, in_path=local_root, size=media.size)
        if not dest:
            return ""
        if media.type == MediaType.MOVIE:
            dir_name, file_name = filetransfer.get_moive_dest_path(media)
            local_target = os.path.join(dest, media.category, dir_name, "%s%s" % (file_name, os.path.splitext(local_file)[-1]))
        else:
            dir_name, season_name, file_name = filetransfer.get_tv_dest_path(media)
            local_target = os.path.join(dest, media.category, dir_name, season_name, "%s%s" % (file_name, os.path.splitext(local_file)[-1]))
        return self._local_to_remote_path(local_target)

    def _local_to_remote_path(self, path):
        normalized = os.path.normpath(path).replace("\\", "/")
        for local_root, remote_root in self._local_remote_roots():
            local_root = os.path.normpath(local_root).replace("\\", "/")
            if normalized == local_root or normalized.startswith("%s/" % local_root.rstrip("/")):
                rel = normalized[len(local_root.rstrip("/")):].strip("/")
                return posixpath.join(remote_root, rel) if rel else remote_root
        return ""

    def _local_remote_roots(self):
        roots = []
        for attr in Config().get_config('downloaddir') or []:
            if attr.get("container_path") and attr.get("save_path"):
                roots.append((attr.get("container_path"), self._normalize_remote_path(attr.get("save_path"))))
        media_cfg = Config().get_config('media') or {}
        for local_key, remote_key in [
            ("movie_path", "remote_movie_path"),
            ("tv_path", "remote_tv_path"),
            ("anime_path", "remote_anime_path")
        ]:
            local_paths = media_cfg.get(local_key) or []
            if not isinstance(local_paths, list):
                local_paths = [local_paths]
            remote_path = self._normalize_remote_path(self._client_config.get(remote_key))
            for local_path in local_paths:
                if local_path and remote_path:
                    roots.append((local_path, remote_path))
        return roots

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
