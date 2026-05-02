import base64
import json
import os
import re
import threading
import time
from urllib import parse

import requests
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from app.utils import ExceptionUtils, RequestUtils
from config import Config


PAN115_XOR_KEY_SEED = bytes([
    0xf0, 0xe5, 0x69, 0xae, 0xbf, 0xdc, 0xbf, 0x8a, 0x1a, 0x45, 0xe8, 0xbe, 0x7d, 0xa6, 0x73, 0xb8,
    0xde, 0x8f, 0xe7, 0xc4, 0x45, 0xda, 0x86, 0xc4, 0x9b, 0x64, 0x8b, 0x14, 0x6a, 0xb4, 0xf1, 0xaa,
    0x38, 0x01, 0x35, 0x9e, 0x26, 0x69, 0x2c, 0x86, 0x00, 0x6b, 0x4f, 0xa5, 0x36, 0x34, 0x62, 0xa6,
    0x2a, 0x96, 0x68, 0x18, 0xf2, 0x4a, 0xfd, 0xbd, 0x6b, 0x97, 0x8f, 0x4d, 0x8f, 0x89, 0x13, 0xb7,
    0x6c, 0x8e, 0x93, 0xed, 0x0e, 0x0d, 0x48, 0x3e, 0xd7, 0x2f, 0x88, 0xd8, 0xfe, 0xfe, 0x7e, 0x86,
    0x50, 0x95, 0x4f, 0xd1, 0xeb, 0x83, 0x26, 0x34, 0xdb, 0x66, 0x7b, 0x9c, 0x7e, 0x9d, 0x7a, 0x81,
    0x32, 0xea, 0xb6, 0x33, 0xde, 0x3a, 0xa9, 0x59, 0x34, 0x66, 0x3b, 0xaa, 0xba, 0x81, 0x60, 0x48,
    0xb9, 0xd5, 0x81, 0x9c, 0xf8, 0x6c, 0x84, 0x77, 0xff, 0x54, 0x78, 0x26, 0x5f, 0xbe, 0xe8, 0x1e,
    0x36, 0x9f, 0x34, 0x80, 0x5c, 0x45, 0x2c, 0x9b, 0x76, 0xd5, 0x1b, 0x8f, 0xcc, 0xc3, 0xb8, 0xf5
])
PAN115_XOR_CLIENT_KEY = bytes([0x78, 0x06, 0xad, 0x4c, 0x33, 0x86, 0x5d, 0x18, 0x4c, 0x01, 0x3f, 0x46])
PAN115_RSA_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCGhpgMD1okxLnUMCDNLCJwP/P0
UHVlKQWLHPiPCbhgITZHcZim4mgxSWWb0SLDNZL9ta1HlErR6k02xrFyqtYzjDu2
rGInUC0BCZOsln0a7wDwyOA43i5NO8LsNory6fEKbx7aT3Ji8TZCDAfDMbhxvxOf
dPMBDjxP5X3zr7cWgwIDAQAB
-----END PUBLIC KEY-----"""


class Pan115AuthType:
    COOKIE = "cookie"
    QRCODE = "qrcode"
    OPEN = "open"


class Pan115QRCodeStatus:
    WAITING = 0
    SCANNED = 1
    SIGNED_IN = 2
    EXPIRED = -1
    CANCELED = -2


class Pan115TaskStatus:
    FAILED = -1
    PENDING = 0
    DOWNLOADING = 1
    COMPLETED = 2

    NAME_MAP = {
        FAILED: "failed",
        PENDING: "pending",
        DOWNLOADING: "downloading",
        COMPLETED: "completed"
    }


class Py115:
    QRCODE_TOKEN_API = "https://qrcodeapi.115.com/api/1.0/web/1.0/token/"
    QRCODE_STATUS_API = "https://qrcodeapi.115.com/get/status/"
    QRCODE_RESULT_API = "https://passportapi.115.com/app/1.0/{app}/1.0/login/qrcode/"
    QRCODE_IMAGE_API = "https://qrcodeapi.115.com/api/1.0/{app}/1.0/qrcode"
    DOWNLOAD_URL_API = "https://proapi.115.com/app/chrome/downurl"
    OPEN_DEVICE_CODE_API = "https://passportapi.115.com/open/authDeviceCode"
    OPEN_DEVICE_TOKEN_API = "https://passportapi.115.com/open/deviceCodeToToken"
    DEFAULT_QRCODE_SOURCE = "web"
    DEFAULT_SESSION_LIMIT_RATE = 2.0
    DEFAULT_OPEN_LIMIT_RATE = 1.0
    VALID_QRCODE_SOURCES = {
        "web", "android", "ios", "linux", "mac", "windows", "tv",
        "alipaymini", "wechatmini", "qandroid"
    }

    def __init__(self, config=None):
        if isinstance(config, str):
            config = {"cookie": config}
        self.config = dict(config or {})
        self.persist = bool(self.config.pop("_persist", False))
        self.auth_type = (self.config.get("auth_type") or Pan115AuthType.COOKIE).lower()
        self.cookie = self.config.get("cookie")
        self.qrcode_token = self.config.get("qrcode_token")
        self.qrcode_session = self._parse_json_value(self.config.get("qrcode_session"))
        self.qrcode_source = self._normalize_qrcode_source(self.config.get("qrcode_source"))
        self.refresh_token = self.config.get("refresh_token")
        self.access_token = self.config.get("access_token")
        self.user_agent = self.config.get("user_agent")
        self.limit_rate = self._resolve_limit_rate(self.config.get("limit_rate"))
        self.req = None
        self.uid = None
        self.sign = None
        self.err = None
        self._limit_lock = threading.Lock()
        self._last_request_at = 0.0
        self._init_request()

    def _init_request(self):
        req_kwargs = {"session": requests.Session()}
        if self.cookie:
            req_kwargs["cookies"] = self.cookie
        if self.user_agent:
            req_kwargs["headers"] = self.user_agent
        self.req = RequestUtils(**req_kwargs)

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

    def _get_res(self, **kwargs):
        self._wait_limit()
        return self.req.get_res(**kwargs)

    def _post_res(self, **kwargs):
        self._wait_limit()
        return self.req.post_res(**kwargs)

    def login(self):
        if self.auth_type == Pan115AuthType.QRCODE:
            return self._login_by_qrcode()
        if self.auth_type == Pan115AuthType.OPEN:
            return self._login_by_open()
        return self._login_by_cookie()

    def ensure_login(self):
        if self.auth_type == Pan115AuthType.OPEN:
            return self._login_by_open()
        if self.uid and self.sign and self.req:
            return True
        return self.login()

    def _login_by_cookie(self):
        if not self.cookie:
            self.err = "115 cookie is empty"
            return False
        self._init_request()
        if not self.getuid():
            return False
        if not self.getsign():
            return False
        return True

    def _login_by_qrcode(self):
        if self.cookie and self._login_by_cookie():
            return True

        session = self._get_qrcode_session()
        if not session:
            ok, session = self.create_qrcode_session()
            if not ok:
                return False
            self.err = "115 qrcode session created, scan and retry: %s" % self._describe_qrcode_session(session)
            return False

        if session.get("uid") and not session.get("time") and not session.get("sign"):
            ok, cookie = self.get_qrcode_result(session.get("uid"), self.qrcode_source)
            if not ok:
                return False
            self.import_cookie(cookie, clear_qrcode=True)
            return self._login_by_cookie()

        ok, status_payload = self.get_qrcode_status(session)
        if not ok:
            return False
        status = self._extract_qrcode_status(status_payload)
        if status == Pan115QRCodeStatus.SIGNED_IN:
            ok, cookie = self.get_qrcode_result(session.get("uid"), self.qrcode_source)
            if not ok:
                return False
            self.import_cookie(cookie, clear_qrcode=True)
            return self._login_by_cookie()
        if status in [Pan115QRCodeStatus.EXPIRED, Pan115QRCodeStatus.CANCELED]:
            self.clear_qrcode_session()
            ok, session = self.create_qrcode_session()
            if ok:
                self.err = "115 qrcode expired, a new qrcode session was created: %s" % (
                    self._describe_qrcode_session(session)
                )
            return False

        status_text = {
            Pan115QRCodeStatus.WAITING: "waiting_for_scan",
            Pan115QRCodeStatus.SCANNED: "scanned_waiting_confirm"
        }.get(status, "unknown")
        self.err = "115 qrcode login pending (%s): %s" % (status_text, self._describe_qrcode_session(session))
        return False

    def _login_by_open(self):
        if not self.refresh_token and not self.access_token:
            self.err = "115 open auth requires refresh_token or access_token"
            return False
        self.err = "115 open auth is modeled, but V1 APIs still run on session endpoints"
        return False

    def normalize_task(self, task):
        normalized = dict(task)
        raw_status = self._safe_int(
            task.get("status"),
            self._safe_int(task.get("move"), self._safe_int(task.get("download_status"), 0))
        )
        status_msg = str(task.get("status_msg") or "").lower()
        if status_msg in ["finished", "complete", "completed", "success"]:
            task_status = Pan115TaskStatus.COMPLETED
        elif status_msg in ["failed", "error"]:
            task_status = Pan115TaskStatus.FAILED
        else:
            task_status = raw_status
        normalized.update({
            "raw_status": raw_status,
            "status": task_status,
            "status_name": Pan115TaskStatus.NAME_MAP.get(task_status, "unknown"),
            "percentDone": round(self._safe_float(
                task.get("percentDone"),
                self._safe_float(task.get("progress"), 100.0 if task_status == Pan115TaskStatus.COMPLETED else 0.0)
            ), 1),
            "rateDownload": self._safe_int(
                task.get("rateDownload"),
                self._safe_int(task.get("download_speed"), self._safe_int(task.get("speed"), 0))
            ),
            "rateUpload": self._safe_int(
                task.get("rateUpload"),
                self._safe_int(task.get("upload_speed"), 0)
            ),
            "peers": self._safe_int(task.get("peers"), 0),
            "info_hash": task.get("info_hash") or task.get("hash") or task.get("sha1"),
            "file_id": task.get("file_id") or task.get("cid"),
            "name": task.get("name") or task.get("file_name") or task.get("title") or ""
        })
        return normalized

    def import_cookie(self, cookie, clear_qrcode=False):
        self.cookie = self._format_cookie(cookie)
        self.config["cookie"] = self.cookie
        self._init_request()
        if clear_qrcode:
            self.qrcode_token = None
            self.qrcode_session = None
            self.config["qrcode_token"] = ""
            self.config["qrcode_session"] = ""
        self._persist_client_config({
            "cookie": self.cookie,
            "qrcode_token": "" if clear_qrcode else self.config.get("qrcode_token"),
            "qrcode_session": "" if clear_qrcode else self.config.get("qrcode_session")
        })

    def clear_qrcode_session(self):
        self.qrcode_token = None
        self.qrcode_session = None
        self.config["qrcode_token"] = ""
        self.config["qrcode_session"] = ""
        self._persist_client_config({
            "qrcode_token": "",
            "qrcode_session": ""
        })

    def create_qrcode_session(self):
        try:
            response = self._get_res(url=self.QRCODE_TOKEN_API)
            if not response:
                self.err = "115 qrcode token request failed"
                return False, {}
            root_object = response.json()
            if not root_object.get("state"):
                self.err = "Failed to create 115 qrcode session: %s" % (
                    root_object.get("error") or root_object.get("message") or root_object.get("error_msg")
                )
                return False, {}
            data = root_object.get("data") or {}
            session = {
                "uid": data.get("uid"),
                "time": data.get("time"),
                "sign": data.get("sign"),
                "qrcode": data.get("qrcode")
            }
            if not session.get("uid"):
                self.err = "115 qrcode session missing uid"
                return False, {}
            session["qrcode_image"] = self._build_qrcode_image_url(session.get("uid"))
            self.qrcode_token = session.get("uid")
            self.qrcode_session = session
            self.config["qrcode_token"] = self.qrcode_token
            self.config["qrcode_session"] = json.dumps(session, ensure_ascii=False)
            self._persist_client_config({
                "qrcode_token": self.qrcode_token,
                "qrcode_session": self.config.get("qrcode_session")
            })
            return True, session
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 create_qrcode_session exception: %s" % result
        return False, {}

    def get_qrcode_status(self, payload=None):
        try:
            session = payload or self._get_qrcode_session()
            if not session:
                self.err = "115 qrcode session is empty"
                return False, {}
            if not session.get("uid") or not session.get("time") or not session.get("sign"):
                self.err = "115 qrcode session is incomplete, missing uid/time/sign"
                return False, {}
            params = {
                "uid": session.get("uid"),
                "time": session.get("time"),
                "sign": session.get("sign")
            }
            response = self._get_res(url=self.QRCODE_STATUS_API, params=params)
            if not response:
                self.err = "115 qrcode status request failed"
                return False, {}
            root_object = response.json()
            if root_object.get("state") is False:
                self.err = "Failed to get 115 qrcode status: %s" % (
                    root_object.get("error") or root_object.get("message") or root_object.get("error_msg")
                )
                return False, {}
            return True, root_object
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 get_qrcode_status exception: %s" % result
        return False, {}

    def get_qrcode_result(self, uid, app=None):
        try:
            app_name = self._normalize_qrcode_source(app or self.qrcode_source)
            url = self.QRCODE_RESULT_API.format(app=app_name)
            post_data = parse.urlencode({
                "app": app_name,
                "account": uid
            })
            response = self._post_res(url=url, params=post_data.encode("utf-8"))
            if not response:
                self.err = "115 qrcode result request failed"
                return False, ""
            root_object = response.json()
            if root_object.get("state") is False:
                self.err = "Failed to finish 115 qrcode login: %s" % (
                    root_object.get("error") or root_object.get("message") or root_object.get("error_msg")
                )
                return False, ""
            cookie_data = ((root_object.get("data") or {}).get("cookie")
                           or root_object.get("cookie"))
            if not cookie_data:
                self.err = "115 qrcode login response missing cookie"
                return False, ""
            return True, self._format_cookie(cookie_data)
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 get_qrcode_result exception: %s" % result
        return False, ""

    def create_open_device_code(self, client_id, code_challenge, code_challenge_method="sha256"):
        try:
            post_data = parse.urlencode({
                "client_id": client_id,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method
            })
            response = self._post_res(url=self.OPEN_DEVICE_CODE_API, params=post_data.encode("utf-8"))
            if not response:
                self.err = "115 open device code request failed"
                return False, {}
            root_object = response.json()
            if root_object.get("state") is False:
                self.err = "Failed to create 115 open device code: %s" % (
                    root_object.get("error") or root_object.get("message") or root_object.get("error_msg")
                )
                return False, {}
            return True, root_object
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 create_open_device_code exception: %s" % result
        return False, {}

    def exchange_open_access_token(self, uid, code_verifier):
        try:
            post_data = parse.urlencode({
                "uid": uid,
                "code_verifier": code_verifier
            })
            response = self._post_res(url=self.OPEN_DEVICE_TOKEN_API, params=post_data.encode("utf-8"))
            if not response:
                self.err = "115 open access token request failed"
                return False, {}
            root_object = response.json()
            if root_object.get("state") is False:
                self.err = "Failed to exchange 115 open access token: %s" % (
                    root_object.get("error") or root_object.get("message") or root_object.get("error_msg")
                )
                return False, {}
            return True, root_object
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 exchange_open_access_token exception: %s" % result
        return False, {}

    def getdirid(self, tdir):
        if not self.ensure_login():
            return False, ""
        try:
            normalized_path = (tdir or "/").strip() or "/"
            if normalized_path == "/":
                return True, "0"
            response = self._get_res(url="https://webapi.115.com/files/getid", params={"path": normalized_path})
            if response:
                root_object = response.json()
                if not root_object.get("state"):
                    self.err = "Failed to get 115 dir id for %s: %s" % (
                        normalized_path, root_object.get("error") or root_object.get("error_msg")
                    )
                    return False, ""
                dir_id = str(root_object.get("id") or "").strip()
                if dir_id:
                    self.err = None
                    return True, dir_id
            ok, dir_id = self._walk_dir_id(normalized_path)
            if ok and dir_id:
                self.err = None
                return True, dir_id
            self.err = "115 dir id is empty for path: %s" % normalized_path
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 getdirid exception: %s" % result
        return False, ""

    def getsign(self):
        try:
            self.sign = ""
            url = "https://115.com/?ct=offline&ac=space&_=%s" % str(round(time.time() * 1000))
            response = self._get_res(url=url)
            if response:
                root_object = response.json()
                if not root_object.get("state"):
                    self.err = "Failed to get 115 sign: %s" % (
                        root_object.get("error_msg") or root_object.get("error")
                    )
                    return False
                self.sign = root_object.get("sign")
                return bool(self.sign)
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 getsign exception: %s" % result
        return False

    def getuid(self):
        try:
            self.uid = ""
            params = {
                "aid": 1,
                "cid": 0,
                "o": "user_ptime",
                "asc": 0,
                "offset": 0,
                "show_dir": 1,
                "limit": 30,
                "code": "",
                "scid": "",
                "snap": 0,
                "natsort": 1,
                "star": 1,
                "source": "",
                "format": "json"
            }
            response = self._get_res(url="https://webapi.115.com/files", params=params)
            if response:
                root_object = response.json()
                if not root_object.get("state"):
                    self.err = "Failed to get 115 uid: %s" % (
                        root_object.get("error_msg") or root_object.get("error")
                    )
                    return False
                self.uid = root_object.get("uid")
                return bool(self.uid)
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 getuid exception: %s" % result
        return False

    def gettasklist(self, page=1):
        if not self.ensure_login():
            return False, []
        try:
            tasks = []
            current_page = page or 1
            url = "https://115.com/web/lixian/?ct=lixian&ac=task_lists"
            while True:
                post_data = parse.urlencode({
                    "page": current_page,
                    "uid": self.uid,
                    "sign": self.sign,
                    "time": str(round(time.time() * 1000))
                })
                response = self._post_res(url=url, params=post_data.encode("utf-8"))
                if not response:
                    self.err = "115 task list request failed"
                    return False, tasks
                root_object = response.json()
                if not root_object.get("state"):
                    self.err = "Failed to get 115 tasks: %s" % (
                        root_object.get("error") or root_object.get("error_msg")
                    )
                    return False, tasks
                tasks.extend(root_object.get("tasks") or [])
                page_count = self._safe_int(root_object.get("page_count"), current_page)
                count = self._safe_int(root_object.get("count"), len(tasks))
                if count == 0 or current_page >= page_count:
                    break
                current_page += 1
            return True, tasks
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 gettasklist exception: %s" % result
        return False, []

    def addtask(self, tdir, content):
        if not self.ensure_login():
            return False, ""
        try:
            ok, dir_id = self.ensure_dir(tdir)
            if not ok:
                return False, ""
            if not dir_id:
                self.err = "115 addtask target dir id is empty for path: %s" % (tdir or "/")
                return False, ""
            content = self._resolve_content_url(content)
            post_data = parse.urlencode({
                "url": content,
                "savepath": "",
                "wp_path_id": dir_id,
                "uid": self.uid,
                "sign": self.sign,
                "time": str(round(time.time() * 1000))
            })
            response = self._post_res(
                url="https://115.com/web/lixian/?ct=lixian&ac=add_task_url",
                params=post_data.encode("utf-8")
            )
            if response:
                root_object = response.json()
                if not root_object.get("state"):
                    self.err = root_object.get("error_msg") or root_object.get("error")
                    return False, ""
                return True, root_object.get("info_hash")
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 addtask exception: %s" % result
        return False, ""

    def mkdir(self, parent_dir_id, dirname):
        if not self.ensure_login():
            return False, ""
        dirname = (dirname or "").strip()
        if not dirname:
            self.err = "115 mkdir dirname is empty"
            return False, ""
        try:
            post_data = parse.urlencode({
                "pid": parent_dir_id or "0",
                "cname": dirname
            })
            response = self._post_res(
                url="https://webapi.115.com/files/add",
                params=post_data.encode("utf-8")
            )
            if not response:
                self.err = "115 mkdir request failed"
                return False, ""
            root_object = response.json()
            if root_object.get("state") is False:
                error_msg = root_object.get("error") or root_object.get("error_msg") or ""
                if "已存在" in str(error_msg):
                    ok, dir_id = self.find_child_dir_id(parent_dir_id, dirname)
                    if ok and dir_id:
                        self.err = None
                        return True, dir_id
                self.err = "Failed to create 115 dir %s: %s" % (dirname, error_msg)
                return False, ""
            data = root_object.get("data") or {}
            dir_id = str(
                root_object.get("id")
                or data.get("cid")
                or data.get("file_id")
                or data.get("id")
                or ""
            ).strip()
            if not dir_id:
                ok, dir_id = self.find_child_dir_id(parent_dir_id, dirname)
                if not ok or not dir_id:
                    self.err = self.err or ("115 mkdir succeeded but dir id lookup failed for %s" % dirname)
                    return False, ""
            self.err = None
            return True, dir_id
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 mkdir exception: %s" % result
        return False, ""

    def ensure_dir(self, tdir):
        if not self.ensure_login():
            return False, ""
        normalized_path = self._normalize_dir_path(tdir)
        if normalized_path == "/":
            self.err = None
            return True, "0"
        ok, dir_id = self.getdirid(normalized_path)
        if ok and dir_id:
            return True, dir_id
        ok, current_id = self._walk_dir_id(normalized_path, create_missing=True)
        if not ok:
            self.err = self.err or ("Failed to ensure 115 dir: %s" % normalized_path)
            return False, ""
        self.err = None
        return True, current_id

    def deltask(self, thash):
        if not self.ensure_login():
            return False
        try:
            hashes = thash if isinstance(thash, list) else [thash]
            hashes = [value for value in hashes if value]
            if not hashes:
                return True
            payload = {
                "uid": self.uid,
                "sign": self.sign,
                "time": str(round(time.time() * 1000))
            }
            for index, item in enumerate(hashes):
                payload["hash[%s]" % index] = item
            post_data = parse.urlencode(payload)
            response = self._post_res(
                url="https://115.com/web/lixian/?ct=lixian&ac=task_del",
                params=post_data.encode("utf-8")
            )
            if response:
                root_object = response.json()
                if not root_object.get("state"):
                    self.err = root_object.get("error_msg") or root_object.get("error")
                    return False
                return True
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 deltask exception: %s" % result
        return False

    def getiddir(self, tid):
        if not self.ensure_login():
            return False, "/"
        try:
            path = "/"
            url = (
                "https://aps.115.com/natsort/files.php?"
                "aid=1&cid={cid}&o=file_name&asc=1&offset=0&show_dir=1&limit=40&code=&scid=&snap=0"
                "&natsort=1&record_open_time=1&source=&format=json&fc_mix=0&type=&star=&is_share=&suffix="
                "&custom_order=0"
            ).format(cid=tid)
            response = self._get_res(url=url)
            if response:
                root_object = response.json()
                if not root_object.get("state"):
                    self.err = "Failed to get 115 dir path for %s: %s" % (
                        tid, root_object.get("error") or root_object.get("error_msg")
                    )
                    return False, path
                for path_object in root_object.get("path") or []:
                    if path_object.get("cid") == 0:
                        continue
                    path += "%s/" % path_object.get("name")
                if path == "/":
                    self.err = "115 file path not found"
                    return False, path
                return True, path
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 getiddir exception: %s" % result
        return False, "/"

    def listdir(self, cid="0", offset=0, limit=1000):
        if not self.ensure_login():
            return False, []
        try:
            params = {
                "aid": 1,
                "cid": cid or "0",
                "o": "file_name",
                "asc": 1,
                "offset": offset,
                "show_dir": 1,
                "limit": limit,
                "code": "",
                "scid": "",
                "snap": 0,
                "natsort": 1,
                "record_open_time": 1,
                "source": "",
                "format": "json",
                "fc_mix": 0
            }
            response = self._get_res(url="https://webapi.115.com/files", params=params)
            if response:
                root_object = response.json()
                if not root_object.get("state"):
                    self.err = "Failed to list 115 dir %s: %s" % (
                        cid, root_object.get("error") or root_object.get("error_msg")
                    )
                    return False, []
                return True, root_object.get("data") or []
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 listdir exception: %s" % result
        return False, []

    def move(self, file_ids, to_dir_id):
        if not self.ensure_login():
            return False
        try:
            ids = self._normalize_id_list(file_ids)
            if not ids:
                self.err = "115 move requires file_ids"
                return False
            if not to_dir_id:
                self.err = "115 move requires target dir id"
                return False
            post_data = parse.urlencode({
                "fid": ",".join(ids),
                "pid": str(to_dir_id)
            })
            response = self._post_res(
                url="https://webapi.115.com/files/move",
                params=post_data.encode("utf-8")
            )
            if response:
                root_object = response.json()
                if root_object.get("state") is False:
                    self.err = root_object.get("error") or root_object.get("error_msg")
                    return False
                self.err = None
                return True
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 move exception: %s" % result
        return False

    def rename(self, file_id, new_name):
        if not self.ensure_login():
            return False
        try:
            if not file_id or not new_name:
                self.err = "115 rename requires file_id and new_name"
                return False
            post_data = parse.urlencode({
                "fid": str(file_id),
                "file_name": str(new_name)
            })
            response = self._post_res(
                url="https://webapi.115.com/files/edit",
                params=post_data.encode("utf-8")
            )
            if response:
                root_object = response.json()
                if root_object.get("state") is False:
                    self.err = root_object.get("error") or root_object.get("error_msg")
                    return False
                self.err = None
                return True
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 rename exception: %s" % result
        return False

    def delete(self, file_ids):
        if not self.ensure_login():
            return False
        try:
            ids = self._normalize_id_list(file_ids)
            if not ids:
                self.err = "115 delete requires file_ids"
                return False
            payload = {}
            for index, file_id in enumerate(ids):
                payload["fid[%s]" % index] = file_id
            post_data = parse.urlencode(payload)
            response = self._post_res(
                url="https://webapi.115.com/rb/delete",
                params=post_data.encode("utf-8")
            )
            if response:
                root_object = response.json()
                if root_object.get("state") is False:
                    self.err = root_object.get("error") or root_object.get("error_msg")
                    return False
                self.err = None
                return True
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 delete exception: %s" % result
        return False

    def get_download_url(self, pick_code, user_agent=None):
        """
        Resolve a 115 file pick_code to a temporary download URL.

        This mirrors AList's session implementation:
        pick_code -> proapi.115.com/app/chrome/downurl -> decoded URL.
        """
        if not pick_code:
            self.err = "115 download url requires pick_code"
            return False, {}
        if not self.ensure_login():
            return False, {}
        try:
            key = os.urandom(16)
            payload = json.dumps({"pickcode": pick_code}, separators=(",", ":")).encode("utf-8")
            encoded_payload = self._encode_download_payload(payload, key)
            response = self._post_download_url_res(encoded_payload, user_agent=user_agent)
            if not response:
                self.err = "115 download url request failed"
                return False, {}
            root_object = response.json()
            if root_object.get("state") is False:
                self.err = "Failed to get 115 download url: %s" % (
                    root_object.get("error") or root_object.get("message") or root_object.get("error_msg")
                    or root_object.get("errno") or root_object.get("code") or root_object
                )
                return False, {}
            encoded_data = root_object.get("data")
            if not encoded_data:
                self.err = "115 download url response missing data"
                return False, {}
            if not isinstance(encoded_data, str):
                encoded_data = json.dumps(encoded_data, ensure_ascii=False)
            decoded = self._decode_download_payload(encoded_data, key)
            download_data = json.loads(decoded.decode("utf-8"))
            for _, info in (download_data or {}).items():
                url_info = info.get("url") or {}
                download_url = url_info.get("url")
                if download_url and self._safe_int(info.get("file_size"), -1) >= 0:
                    return True, {
                        "url": download_url,
                        "file_name": info.get("file_name"),
                        "file_size": self._safe_int(info.get("file_size"), 0),
                        "pick_code": info.get("pick_code") or pick_code,
                        "headers": {
                            "User-Agent": user_agent or self.user_agent or Config().get_ua()
                        },
                        "raw": info
                    }
            self.err = "115 download url response is empty"
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 get_download_url exception: %s" % result
        return False, {}

    def _resolve_content_url(self, content):
        if not isinstance(content, str):
            return content
        if not re.match(r"^https*://", content):
            return content
        try:
            response = self._get_res(url=content, allow_redirects=False)
            if response is not None and response.headers.get("Location"):
                return response.headers.get("Location")
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
        return content

    def find_child_dir_id(self, parent_dir_id, dirname):
        if not self.ensure_login():
            return False, ""
        dirname = (dirname or "").strip()
        if not dirname:
            self.err = "115 child dir name is empty"
            return False, ""
        try:
            ok, items = self.listdir(cid=parent_dir_id or "0", offset=0, limit=2000)
            if not ok:
                return False, ""
            for item in items:
                item_name = str(item.get("n") or item.get("name") or "").strip()
                item_fid = str(item.get("fid") or "").strip()
                item_cid = str(item.get("cid") or item.get("file_id") or item.get("id") or "").strip()
                is_dir = bool(item_cid and not item_fid)
                item_id = item_cid if is_dir else ""
                if item_name == dirname and is_dir and item_id:
                    self.err = None
                    return True, item_id
            self.err = "115 child dir not found: %s" % dirname
            return False, ""
        except Exception as result:
            ExceptionUtils.exception_traceback(result)
            self.err = "115 find_child_dir_id exception: %s" % result
        return False, ""

    def _walk_dir_id(self, normalized_path, create_missing=False):
        parts = [part for part in self._normalize_dir_path(normalized_path).strip("/").split("/") if part]
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

    @staticmethod
    def _normalize_dir_path(path):
        path = (path or "/").strip()
        if not path:
            return "/"
        if not path.startswith("/"):
            path = "/%s" % path
        path = re.sub(r"/{2,}", "/", path)
        return path.rstrip("/") or "/"

    @staticmethod
    def _normalize_id_list(value):
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        if value is None:
            return []
        return [str(value).strip()] if str(value).strip() else []

    def _post_download_url_res(self, encoded_payload, user_agent=None):
        headers = dict(getattr(self.req, "_headers", {}) or {})
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        if user_agent:
            headers["User-Agent"] = user_agent
        self._wait_limit()
        session = getattr(self.req, "_session", None)
        post_kwargs = {
            "url": self.DOWNLOAD_URL_API,
            "params": {"t": str(int(time.time()))},
            "data": {"data": encoded_payload},
            "verify": False,
            "headers": headers,
            "cookies": getattr(self.req, "_cookies", None),
            "proxies": getattr(self.req, "_proxies", None),
            "timeout": getattr(self.req, "_timeout", 20)
        }
        if session:
            return session.post(**post_kwargs)
        return requests.post(**post_kwargs)

    @classmethod
    def _encode_download_payload(cls, payload, key):
        data = bytearray(key + payload)
        body = bytearray(data[16:])
        cls._xor_transform(body, cls._xor_derive_key(key, 4))
        body.reverse()
        cls._xor_transform(body, PAN115_XOR_CLIENT_KEY)
        data[16:] = body
        public_key = RSA.import_key(PAN115_RSA_PUBLIC_KEY)
        cipher = PKCS1_v1_5.new(public_key)
        block_size = public_key.size_in_bytes() - 11
        encrypted = bytearray()
        for offset in range(0, len(data), block_size):
            encrypted.extend(cipher.encrypt(bytes(data[offset:offset + block_size])))
        return base64.b64encode(bytes(encrypted)).decode("utf-8")

    @classmethod
    def _decode_download_payload(cls, encoded_payload, key):
        data = base64.b64decode(encoded_payload)
        public_key = RSA.import_key(PAN115_RSA_PUBLIC_KEY)
        block_size = public_key.size_in_bytes()
        decrypted = bytearray()
        for offset in range(0, len(data), block_size):
            block = data[offset:offset + block_size]
            value = pow(int.from_bytes(block, "big"), public_key.e, public_key.n)
            plain = value.to_bytes(max((value.bit_length() + 7) // 8, 1), "big")
            index = plain.find(b"\x00")
            if index < 0:
                raise ValueError("115 download payload RSA decode failed")
            decrypted.extend(plain[index + 1:])
        output = bytearray(decrypted[16:])
        cls._xor_transform(output, cls._xor_derive_key(decrypted[:16], 12))
        output.reverse()
        cls._xor_transform(output, cls._xor_derive_key(key, 4))
        return bytes(output)

    @staticmethod
    def _xor_derive_key(seed, size):
        seed = bytes(seed)
        return bytes(
            ((seed[index] + PAN115_XOR_KEY_SEED[size * index]) & 0xff)
            ^ PAN115_XOR_KEY_SEED[size * (size - index - 1)]
            for index in range(size)
        )

    @staticmethod
    def _xor_transform(data, key):
        data_size = len(data)
        key_size = len(key)
        mod = data_size % 4
        for index in range(mod):
            data[index] ^= key[index % key_size]
        for index in range(mod, data_size):
            data[index] ^= key[(index - mod) % key_size]

    def _get_qrcode_session(self):
        session = self.qrcode_session or self._parse_json_value(self.config.get("qrcode_session"))
        if session:
            return session
        if self.qrcode_token:
            return {"uid": self.qrcode_token}
        if self.config.get("qrcode_token"):
            return {"uid": self.config.get("qrcode_token")}
        return {}

    def _describe_qrcode_session(self, session):
        if not session:
            return ""
        return session.get("qrcode") or session.get("qrcode_image") or self._build_qrcode_image_url(session.get("uid"))

    def _extract_qrcode_status(self, payload):
        data = payload.get("data") or {}
        return self._safe_int(data.get("status"), self._safe_int(payload.get("status"), None))

    def _build_qrcode_image_url(self, uid):
        if not uid:
            return ""
        return "%s?uid=%s" % (
            self.QRCODE_IMAGE_API.format(app=self.qrcode_source),
            parse.quote(str(uid))
        )

    def _persist_client_config(self, updates):
        if not updates:
            return
        for key, value in updates.items():
            self.config[key] = value
        if not self.persist:
            return
        cfg = Config().get_config()
        client_cfg = cfg.get("client115") or {}
        changed = False
        for key, value in updates.items():
            if client_cfg.get(key) != value:
                client_cfg[key] = value
                changed = True
        if changed:
            cfg["client115"] = client_cfg
            Config().save_config(cfg)

    def _format_cookie(self, cookie):
        if isinstance(cookie, str):
            return cookie.strip()
        if isinstance(cookie, dict):
            return ";".join(
                "%s=%s" % (key, value) for key, value in cookie.items()
                if value is not None and value != ""
            )
        return ""

    @staticmethod
    def _parse_json_value(value):
        if isinstance(value, dict):
            return value
        if not value or not isinstance(value, str):
            return {}
        value = value.strip()
        if not value:
            return {}
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return {}

    @classmethod
    def _normalize_qrcode_source(cls, source):
        source = (source or cls.DEFAULT_QRCODE_SOURCE).strip().lower()
        return source if source in cls.VALID_QRCODE_SOURCES else cls.DEFAULT_QRCODE_SOURCE

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

    def _resolve_limit_rate(self, value):
        if value is None or value == "":
            if self.auth_type == Pan115AuthType.OPEN:
                return self.DEFAULT_OPEN_LIMIT_RATE
            return self.DEFAULT_SESSION_LIMIT_RATE
        return max(self._safe_float(value, 0.0), 0.0)
