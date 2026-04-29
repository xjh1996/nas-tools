"""
115 OpenAPI provider.

Current decision:
- Keep this module as a research placeholder.
- Do not use OpenAPI as the primary runtime path for now.

Why:
- Some documented endpoints still have unstable real-world permission behavior.
- The session/cookie route has already been verified end-to-end for the flows
  this project currently depends on.
"""

import threading
import time

import requests

from app.downloader.client.pan115_base import Pan115Provider
from app.downloader.client.pan115_models import Pan115ProviderType, Pan115TaskStatus
from app.utils import ExceptionUtils, RequestUtils
from config import Config


class Pan115OpenProvider(Pan115Provider):
    provider_type = Pan115ProviderType.OPEN

    BASE_URL = "https://proapi.115.com"
    ALIST_API_BASE = "https://api.alistgo.com"
    ALIST_AUTH_DEVICE_CODE_API = ALIST_API_BASE + "/alist/115/auth_device_code"
    ALIST_GET_TOKEN_API = ALIST_API_BASE + "/alist/115/get_token"
    USER_INFO_API = "/open/user/info"
    REFRESH_TOKEN_API = "https://passportapi.115.com/open/refreshToken"
    OFFLINE_GET_TASK_LIST_API = "/open/offline/get_task_list"
    OFFLINE_ADD_TASK_URLS_API = "/open/offline/add_task_urls"
    OFFLINE_DEL_TASK_API = "/open/offline/del_task"
    UFILE_FILES_API = "/open/ufile/files"
    FOLDER_ADD_API = "/open/folder/add"
    FOLDER_GET_INFO_API = "/open/folder/get_info"
    DEFAULT_LIMIT_RATE = 1.0
    DISABLED_MESSAGE = (
        "115 OpenAPI path is intentionally not used right now because "
        "endpoint permissions are not stable enough in real-world use; "
        "use the session provider instead"
    )

    def __init__(self, config=None, persist=False):
        super().__init__(config=config, persist=persist)
        self.refresh_token = self.config.get("refresh_token")
        self.access_token = self.config.get("access_token")
        self.user_agent = self.config.get("user_agent")
        self.app_id = self.config.get("app_id") or ""
        self.limit_rate = self._resolve_limit_rate(self.config.get("limit_rate"))
        self.req = None
        self.user_info = None
        self.alist_open_session = {}
        self._limit_lock = threading.Lock()
        self._last_request_at = 0.0
        self._init_request()

    def _init_request(self):
        headers = {
            "User-Agent": self.user_agent or Config().get_ua()
        }
        if self.access_token:
            headers["Authorization"] = "Bearer %s" % self.access_token
        self.req = RequestUtils(headers=headers, session=requests.Session())

    def _wait_limit(self):
        if not self.limit_rate or self.limit_rate <= 0:
            return
        interval = 1.0 / float(self.limit_rate)
        with self._limit_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_at if self._last_request_at else None
            if elapsed is not None and elapsed < interval:
                time.sleep(interval - elapsed)
            self._last_request_at = time.monotonic()

    def _get_res(self, url, params=None):
        self._wait_limit()
        return self.req.get_res(url=url, params=params)

    def _post_res(self, url, params=None):
        self._wait_limit()
        return self.req.post_res(url=url, params=params)

    def _api_url(self, path):
        return "%s%s" % (self.BASE_URL.rstrip("/"), path)

    def _persist_alist_open_session(self):
        if not self.persist:
            return
        cfg = Config().get_config()
        client_cfg = cfg.get("client115") or {}
        changed = False
        serialized = self.alist_open_session or {}
        if client_cfg.get("alist_open_session") != serialized:
            client_cfg["alist_open_session"] = serialized
            changed = True
        if changed:
            cfg["client115"] = client_cfg
            Config().save_config(cfg)

    def _persist_tokens(self):
        if not self.persist:
            return
        cfg = Config().get_config()
        client_cfg = cfg.get("client115") or {}
        changed = False
        for key, value in {
            "refresh_token": self.refresh_token,
            "access_token": self.access_token
        }.items():
            if client_cfg.get(key) != value:
                client_cfg[key] = value
                changed = True
        if changed:
            cfg["client115"] = client_cfg
            Config().save_config(cfg)

    def _parse_json(self, response, action):
        if not response:
            self.err = "115 open %s request failed" % action
            return False, {}
        try:
            data = response.json()
        except ValueError:
            self.err = "115 open %s returned invalid json" % action
            return False, {}
        return True, data or {}

    def _is_open_success(self, payload):
        state = payload.get("state")
        if isinstance(state, bool):
            return state
        code = str(payload.get("code") or "").strip()
        return code in ["", "0"]

    def _extract_open_error(self, payload, default):
        return (
            payload.get("message")
            or payload.get("error")
            or payload.get("error_msg")
            or default
        )

    def _request_user_info(self):
        response = self._get_res(url=self._api_url(self.USER_INFO_API))
        ok, payload = self._parse_json(response, "user_info")
        if not ok:
            return False, {}
        if not self._is_open_success(payload):
            self.err = self._extract_open_error(payload, "Failed to get 115 open user info")
            return False, payload
        self.user_info = payload.get("data") or {}
        self.err = None
        return True, payload

    def create_alist_auth_device_code(self, app_id=None):
        params = {"app_id": app_id if app_id is not None else self.app_id}
        headers = {
            "Accept": "*/*",
            "Origin": "https://alistgo.com",
            "Referer": "https://alistgo.com/",
            "User-Agent": self.user_agent or Config().get_ua()
        }
        helper_req = RequestUtils(headers=headers, session=requests.Session())
        response = helper_req.get_res(url=self.ALIST_AUTH_DEVICE_CODE_API, params=params)
        ok, payload = self._parse_json(response, "alist_auth_device_code")
        if not ok:
            return False, {}
        if not self._safe_bool(payload.get("success")):
            self.err = payload.get("message") or "Failed to get AList auth device code"
            return False, {}
        data = payload.get("data") or {}
        resp = data.get("resp") or {}
        session = {
            "app_id": params.get("app_id") or "",
            "uid": resp.get("uid"),
            "time": resp.get("time"),
            "sign": resp.get("sign"),
            "qrcode": resp.get("qrcode"),
            "qrcode_image": "https://qrcodeapi.115.com/api/1.0/web/1.0/qrcode?uid=%s" % resp.get("uid"),
            "code_verifier": data.get("code_verifier")
        }
        self.alist_open_session = session
        self._persist_alist_open_session()
        self.err = None
        return True, session

    def exchange_alist_refresh_token(self, uid=None, code_verifier=None):
        session = self.alist_open_session or {}
        uid = uid or session.get("uid")
        code_verifier = code_verifier or session.get("code_verifier")
        if not uid or not code_verifier:
            self.err = "AList open token exchange requires uid and code_verifier"
            return False, {}
        headers = {
            "Accept": "*/*",
            "Origin": "https://alistgo.com",
            "Referer": "https://alistgo.com/",
            "User-Agent": self.user_agent or Config().get_ua(),
            "Content-Type": "text/plain;charset=UTF-8"
        }
        helper_req = RequestUtils(headers=headers, session=requests.Session())
        response = helper_req.post_res(
            url=self.ALIST_GET_TOKEN_API,
            params=None,
            json={"uid": uid, "code_verifier": code_verifier}
        )
        ok, payload = self._parse_json(response, "alist_get_token")
        if not ok:
            return False, {}
        if not self._safe_bool(payload.get("success")):
            self.err = payload.get("message") or "Failed to exchange AList open token"
            return False, {}
        data = payload.get("data") or {}
        self.refresh_token = data.get("refresh_token") or self.refresh_token
        self.access_token = data.get("access_token") or self.access_token
        self._init_request()
        self._persist_tokens()
        self.err = None
        return True, data

    def _refresh_access_token(self):
        if not self.refresh_token:
            self.err = "115 open provider requires refresh_token to refresh access_token"
            return False
        response = self._post_res(
            url=self.REFRESH_TOKEN_API,
            params={"refresh_token": self.refresh_token}
        )
        ok, payload = self._parse_json(response, "refresh_token")
        if not ok:
            return False
        if not self._is_open_success(payload):
            self.err = self._extract_open_error(payload, "Failed to refresh 115 open token")
            return False
        self.access_token = payload.get("access_token") or self.access_token
        self.refresh_token = payload.get("refresh_token") or self.refresh_token
        self._init_request()
        self._persist_tokens()
        self.err = None
        return bool(self.access_token)

    def login(self):
        # OpenAPI code paths are preserved below for future evaluation, but we
        # intentionally do not enable them as a supported runtime route now.
        self.err = self.DISABLED_MESSAGE
        return False

    def ensure_login(self):
        return self.login()

    def normalize_task(self, task):
        task = dict(task or {})
        raw_status = self._safe_int(task.get("status"), Pan115TaskStatus.PENDING)
        status = raw_status if raw_status in Pan115TaskStatus.NAME_MAP else Pan115TaskStatus.PENDING
        normalized = dict(task)
        normalized.update({
            "raw_status": raw_status,
            "status": status,
            "status_name": Pan115TaskStatus.NAME_MAP.get(status, "unknown"),
            "info_hash": task.get("info_hash"),
            "file_id": task.get("file_id"),
            "delete_file_id": task.get("delete_file_id"),
            "dir_id": task.get("wp_path_id"),
            "wp_path_id": task.get("wp_path_id"),
            "name": task.get("name") or "",
            "percentDone": round(self._safe_float(task.get("percentDone"), 0.0), 1),
            "rateDownload": self._safe_int(task.get("rateDownload"), 0),
            "rateUpload": self._safe_int(task.get("rateUpload"), 0),
            "size": self._safe_int(task.get("size"), 0),
            "path": task.get("path") or ""
        })
        return normalized

    def gettasklist(self, page=1):
        if not self.ensure_login():
            return False, []
        try:
            response = self._get_res(
                url=self._api_url(self.OFFLINE_GET_TASK_LIST_API),
                params={"page": page or 1}
            )
            ok, payload = self._parse_json(response, "get_task_list")
            if not ok:
                return False, []
            if not self._is_open_success(payload):
                self.err = self._extract_open_error(payload, "Failed to get 115 open tasks")
                return False, []
            data = payload.get("data") or {}
            self.err = None
            return True, data.get("tasks") or []
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 open gettasklist exception: %s" % result
        return False, []

    def addtask_urls(self, content, download_dir=None):
        if not self.ensure_login():
            return False, ""
        try:
            urls = self._normalize_urls(content)
            if not urls:
                self.err = "115 open addtask_urls requires at least one url"
                return False, ""
            ok, dir_id = self.ensure_dir(download_dir)
            if not ok:
                return False, ""
            payload = {"urls": "\n".join(urls)}
            if dir_id and str(dir_id) != "0":
                payload["wp_path_id"] = str(dir_id)
            response = self._post_res(
                url=self._api_url(self.OFFLINE_ADD_TASK_URLS_API),
                params=payload
            )
            ok, root = self._parse_json(response, "add_task_urls")
            if not ok:
                return False, ""
            if not self._is_open_success(root):
                self.err = self._extract_open_error(root, "Failed to add 115 open task urls")
                return False, ""
            items = root.get("data") or []
            for item in items:
                if self._safe_bool(item.get("state")) and item.get("info_hash"):
                    self.err = None
                    return True, item.get("info_hash")
            first = items[0] if items else {}
            self.err = self._extract_open_error(first, "115 open add_task_urls returned no info_hash")
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 open addtask_urls exception: %s" % result
        return False, ""

    def deltask(self, thash, delete_file=False):
        if not self.ensure_login():
            return False
        hashes = thash if isinstance(thash, list) else [thash]
        hashes = [value for value in hashes if value]
        if not hashes:
            return True
        for item in hashes:
            try:
                response = self._post_res(
                    url=self._api_url(self.OFFLINE_DEL_TASK_API),
                    params={
                        "info_hash": item,
                        "del_source_file": 1 if delete_file else 0
                    }
                )
                ok, payload = self._parse_json(response, "del_task")
                if not ok:
                    return False
                if not self._is_open_success(payload):
                    self.err = self._extract_open_error(payload, "Failed to delete 115 open task")
                    return False
            except Exception as result:
                ExceptionUtils.exception_traceback(result)
                self.err = "115 open deltask exception: %s" % result
                return False
        self.err = None
        return True

    def listdir(self, cid="0", offset=0, limit=1000):
        if not self.ensure_login():
            return False, []
        try:
            response = self._get_res(
                url=self._api_url(self.UFILE_FILES_API),
                params={
                    "aid": 1,
                    "cid": cid or "0",
                    "limit": limit,
                    "offset": offset,
                    "asc": 1,
                    "o": "file_name",
                    "show_dir": 1
                }
            )
            ok, payload = self._parse_json(response, "ufile_files")
            if not ok:
                return False, []
            if payload.get("state") is False:
                self.err = self._extract_open_error(payload, "Failed to list 115 open dir")
                return False, []
            self.err = None
            return True, payload.get("data") or []
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 open listdir exception: %s" % result
        return False, []

    def find_child_dir_id(self, parent_dir_id, dirname):
        ok, items = self.listdir(cid=parent_dir_id or "0", offset=0, limit=2000)
        if not ok:
            return False, ""
        dirname = (dirname or "").strip()
        for item in items:
            item_name = str(item.get("fn") or item.get("file_name") or "").strip()
            is_dir = str(item.get("fc") or "") == "0"
            item_id = str(item.get("fid") or item.get("file_id") or "").strip()
            if item_name == dirname and is_dir and item_id:
                return True, item_id
        self.err = "115 open child dir not found: %s" % dirname
        return False, ""

    def mkdir(self, parent_dir_id, dirname):
        if not self.ensure_login():
            return False, ""
        try:
            response = self._post_res(
                url=self._api_url(self.FOLDER_ADD_API),
                params={
                    "pid": parent_dir_id or "0",
                    "file_name": dirname
                }
            )
            ok, payload = self._parse_json(response, "folder_add")
            if not ok:
                return False, ""
            if not self._is_open_success(payload):
                message = self._extract_open_error(payload, "Failed to create 115 open dir")
                if "已存在" in str(message):
                    return self.find_child_dir_id(parent_dir_id, dirname)
                self.err = message
                return False, ""
            data = payload.get("data") or {}
            dir_id = str(data.get("file_id") or payload.get("file_id") or "").strip()
            if dir_id:
                self.err = None
                return True, dir_id
            return self.find_child_dir_id(parent_dir_id, dirname)
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 open mkdir exception: %s" % result
        return False, ""

    def ensure_dir(self, tdir):
        normalized_path = self._normalize_dir_path(tdir)
        if normalized_path == "/":
            self.err = None
            return True, "0"
        ok, dir_id = self._walk_dir_id(normalized_path, create_missing=True)
        if ok and dir_id:
            self.err = None
            return True, dir_id
        self.err = self.err or ("Failed to ensure 115 open dir: %s" % normalized_path)
        return False, ""

    def getdirid(self, tdir):
        normalized_path = self._normalize_dir_path(tdir)
        if normalized_path == "/":
            self.err = None
            return True, "0"
        return self._walk_dir_id(normalized_path, create_missing=False)

    def _walk_dir_id(self, normalized_path, create_missing=False):
        parts = [part for part in normalized_path.strip("/").split("/") if part]
        current_id = "0"
        for part in parts:
            ok, next_id = self.find_child_dir_id(current_id, part)
            if ok and next_id:
                current_id = next_id
                continue
            if not create_missing:
                return False, ""
            ok, next_id = self.mkdir(current_id, part)
            if not ok or not next_id:
                return False, ""
            current_id = next_id
        return True, current_id

    def getiddir(self, tid):
        if not self.ensure_login():
            return False, "/"
        tid = str(tid or "").strip()
        if not tid or tid == "0":
            return True, "/"
        try:
            response = self._get_res(
                url=self._api_url(self.FOLDER_GET_INFO_API),
                params={"file_id": tid}
            )
            ok, payload = self._parse_json(response, "folder_get_info")
            if not ok:
                return False, "/"
            if not self._is_open_success(payload):
                self.err = self._extract_open_error(payload, "Failed to get 115 open dir path")
                return False, "/"
            data = payload.get("data") or {}
            paths = data.get("paths") or []
            names = [str(item.get("file_name") or "").strip() for item in paths if item.get("file_name")]
            path = "/"
            if names:
                path = "/%s/" % "/".join(names)
            self.err = None
            return True, path
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 open getiddir exception: %s" % result
        return False, "/"

    def move(self, file_ids, to_dir_id):
        self.err = self.DISABLED_MESSAGE
        return False

    def rename(self, file_id, new_name):
        self.err = self.DISABLED_MESSAGE
        return False

    def delete(self, file_ids):
        self.err = self.DISABLED_MESSAGE
        return False

    @staticmethod
    def _normalize_urls(content):
        if isinstance(content, str):
            items = [line.strip() for line in content.splitlines()]
        elif isinstance(content, (list, tuple, set)):
            items = [str(item).strip() for item in content]
        else:
            items = []
        return [item for item in items if item]

    @staticmethod
    def _normalize_dir_path(path):
        path = (path or "/").strip()
        if not path:
            return "/"
        if not path.startswith("/"):
            path = "/%s" % path
        while "//" in path:
            path = path.replace("//", "/")
        return path.rstrip("/") or "/"

    @staticmethod
    def _safe_int(value, default=0):
        try:
            if value is None or value == "":
                return default
            return int(float(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return str(value).strip().lower() in ["1", "true", "yes"]

    def _resolve_limit_rate(self, value):
        if value is None or value == "":
            return self.DEFAULT_LIMIT_RATE
        try:
            return max(float(value), 0.0)
        except (TypeError, ValueError):
            return self.DEFAULT_LIMIT_RATE
