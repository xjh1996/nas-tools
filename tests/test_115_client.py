import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

from config import Config  # noqa: E402

import importlib.util  # noqa: E402


def load_py115():
    module_path = ROOT_PATH / "app" / "downloader" / "client" / "_py115.py"
    spec = importlib.util.spec_from_file_location("py115_test_module", str(module_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_remote_fs(cookie):
    remote_fs_path = ROOT_PATH / "app" / "downloader" / "client" / "pan115_remote_fs.py"
    spec = importlib.util.spec_from_file_location("pan115_remote_fs_test_module", str(remote_fs_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    py115_module = load_py115()
    client = py115_module.Py115({
        "auth_type": "cookie",
        "cookie": cookie
    })

    class Py115ProviderShim:
        err = None

        def ensure_login(self):
            ret = client.ensure_login()
            self.err = client.err
            return ret

        def getdirid(self, path):
            ret, dir_id = client.getdirid(path)
            self.err = client.err
            return ret, dir_id

        def ensure_dir(self, path):
            ret, dir_id = client.ensure_dir(path)
            self.err = client.err
            return ret, dir_id

        def listdir(self, cid="0", offset=0, limit=1000):
            ret, items = client.listdir(cid=cid, offset=offset, limit=limit)
            self.err = client.err
            return ret, items

        def move(self, file_ids, to_dir_id):
            ret = client.move(file_ids=file_ids, to_dir_id=to_dir_id)
            self.err = client.err
            return ret

        def rename(self, file_id, new_name):
            ret = client.rename(file_id=file_id, new_name=new_name)
            self.err = client.err
            return ret

        def delete(self, file_ids):
            ret = client.delete(file_ids=file_ids)
            self.err = client.err
            return ret

        def get_download_url(self, pick_code, user_agent=None):
            ret, link = client.get_download_url(pick_code=pick_code, user_agent=user_agent)
            self.err = client.err
            return ret, link

    return module.Pan115RemoteFS(Py115ProviderShim())


def load_transfer_planner():
    planner_path = ROOT_PATH / "app" / "downloader" / "client" / "pan115_transfer_planner.py"
    spec = importlib.util.spec_from_file_location("pan115_transfer_planner_test_module", str(planner_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_state_path(custom_path=None):
    if custom_path:
        return Path(custom_path)
    temp_path = Path(Config().get_temp_path())
    temp_path.mkdir(parents=True, exist_ok=True)
    return temp_path / "115_client_test.json"


def load_state(state_path):
    if not state_path.exists():
        return {}
    return json.loads(state_path.read_text(encoding="utf-8"))


def resolve_cookie(args, state):
    if args.cookie:
        return args.cookie
    if state.get("cookie"):
        return state.get("cookie")
    return (Config().get_config("client115") or {}).get("cookie")


def save_state(state_path, state):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def get_response_dir(state_path):
    response_dir = state_path.parent / "115_client_test_responses"
    response_dir.mkdir(parents=True, exist_ok=True)
    return response_dir


def sanitize_name(value):
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value)


def save_response(state_path, title, payload):
    response_dir = get_response_dir(state_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    command_name = sanitize_name(title.lower().replace(" ", "_"))
    response_path = response_dir / f"{timestamp}_{command_name}.json"
    latest_path = response_dir / f"latest_{command_name}.json"
    envelope = {
        "title": title,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "payload": payload
    }
    serialized = json.dumps(envelope, ensure_ascii=False, indent=2)
    response_path.write_text(serialized, encoding="utf-8")
    latest_path.write_text(serialized, encoding="utf-8")
    return response_path


def print_result(title, payload):
    state_file = payload.get("state_file")
    if state_file:
        payload["response_file"] = str(save_response(Path(state_file), title, payload))
    print(title)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        print(serialized)
    except UnicodeEncodeError:
        safe_output = serialized.encode("gbk", errors="backslashreplace").decode("gbk")
        print(safe_output)


def build_client(module, auth_type=None, cookie=None, qrcode_source=None, refresh_token=None, access_token=None):
    client_config = {
        "auth_type": auth_type or "cookie",
        "cookie": cookie,
        "qrcode_source": qrcode_source or "web",
        "refresh_token": refresh_token,
        "access_token": access_token
    }
    return module.Py115(client_config)


def cmd_qrcode_create(args):
    module = load_py115()
    client = build_client(module, auth_type="qrcode", qrcode_source=args.qrcode_source)
    ok, session = client.create_qrcode_session()
    state = load_state(args.state_path)
    state["qrcode_source"] = args.qrcode_source
    state["qrcode_session"] = session or {}
    if session:
        state["qrcode_uid"] = session.get("uid")
    save_state(args.state_path, state)
    print_result("115 qrcode create", {
        "ok": ok,
        "err": client.err,
        "state_file": str(args.state_path),
        "uid": (session or {}).get("uid"),
        "qrcode": (session or {}).get("qrcode"),
        "qrcode_image": (session or {}).get("qrcode_image")
    })


def cmd_qrcode_status(args):
    module = load_py115()
    state = load_state(args.state_path)
    session = state.get("qrcode_session") or {}
    client = build_client(module, auth_type="qrcode", qrcode_source=state.get("qrcode_source") or args.qrcode_source)
    ok, payload = client.get_qrcode_status(session)
    print_result("115 qrcode status", {
        "ok": ok,
        "err": client.err,
        "state_file": str(args.state_path),
        "uid": session.get("uid"),
        "status": ((payload or {}).get("data") or {}).get("status"),
        "payload": payload
    })


def cmd_qrcode_exchange(args):
    module = load_py115()
    state = load_state(args.state_path)
    session = state.get("qrcode_session") or {}
    uid = args.uid or session.get("uid") or state.get("qrcode_uid")
    source = state.get("qrcode_source") or args.qrcode_source
    client = build_client(module, auth_type="qrcode", qrcode_source=source)
    ok, cookie = client.get_qrcode_result(uid, source)
    payload = {
        "ok": ok,
        "err": client.err,
        "state_file": str(args.state_path),
        "uid": uid,
        "cookie_len": len(cookie or ""),
        "cookie_keys": [part.split("=")[0] for part in (cookie or "").split(";") if "=" in part]
    }
    if ok:
        state["cookie"] = cookie
        state["last_exchange_uid"] = uid
        save_state(args.state_path, state)
    print_result("115 qrcode exchange", payload)


def cmd_cookie_login(args):
    module = load_py115()
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    client = build_client(module, auth_type="cookie", cookie=cookie)
    ok = client.login()
    payload = {
        "ok": ok,
        "err": client.err,
        "uid": client.uid,
        "sign_ok": bool(client.sign),
        "state_file": str(args.state_path)
    }
    print_result("115 cookie login", payload)


def cmd_listdir(args):
    module = load_py115()
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    client = build_client(module, auth_type="cookie", cookie=cookie)
    ok, items = client.listdir(cid=args.cid, offset=args.offset, limit=args.limit)
    payload = {
        "ok": ok,
        "err": client.err,
        "cid": args.cid,
        "offset": args.offset,
        "limit": args.limit,
        "count": len(items) if ok else 0,
        "items": items if args.show_items else [],
        "state_file": str(args.state_path)
    }
    print_result("115 listdir", payload)


def cmd_gettasklist(args):
    module = load_py115()
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    client = build_client(module, auth_type="cookie", cookie=cookie)
    ok, tasks = client.gettasklist(page=args.page)
    payload = {
        "ok": ok,
        "err": client.err,
        "page": args.page,
        "count": len(tasks) if ok else 0,
        "tasks": tasks if args.show_tasks else [],
        "state_file": str(args.state_path)
    }
    print_result("115 gettasklist", payload)


def _find_task_by_hash(tasks, info_hash):
    target = (info_hash or "").strip().lower()
    for task in tasks or []:
        task_hash = str(task.get("info_hash") or task.get("hash") or "").strip().lower()
        if task_hash == target:
            return task
    return {}


def cmd_gettask(args):
    module = load_py115()
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    client = build_client(module, auth_type="cookie", cookie=cookie)
    ok, tasks = client.gettasklist(page=args.page)
    task = _find_task_by_hash(tasks if ok else [], args.info_hash)
    payload = {
        "ok": ok and bool(task),
        "err": None if ok and task else (client.err or "115 task not found"),
        "page": args.page,
        "info_hash": args.info_hash,
        "task": task,
        "state_file": str(args.state_path)
    }
    print_result("115 gettask", payload)


def cmd_wait_task(args):
    module = load_py115()
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    client = build_client(module, auth_type="cookie", cookie=cookie)
    deadline = time.time() + args.timeout
    last_task = {}
    while time.time() <= deadline:
        ok, tasks = client.gettasklist(page=1)
        if not ok:
            payload = {
                "ok": False,
                "err": client.err,
                "info_hash": args.info_hash,
                "task": last_task,
                "state_file": str(args.state_path)
            }
            print_result("115 wait task", payload)
            return
        task = _find_task_by_hash(tasks, args.info_hash)
        if task:
            last_task = task
            status = int(task.get("status") or 0)
            percent = float(task.get("percentDone") or 0)
            if status == args.target_status or percent >= args.target_percent:
                payload = {
                    "ok": True,
                    "err": None,
                    "info_hash": args.info_hash,
                    "target_status": args.target_status,
                    "target_percent": args.target_percent,
                    "task": task,
                    "state_file": str(args.state_path)
                }
                print_result("115 wait task", payload)
                return
        time.sleep(args.interval)
    payload = {
        "ok": False,
        "err": "115 wait task timeout",
        "info_hash": args.info_hash,
        "target_status": args.target_status,
        "target_percent": args.target_percent,
        "task": last_task,
        "state_file": str(args.state_path)
    }
    print_result("115 wait task", payload)


def cmd_getdirid(args):
    module = load_py115()
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    client = build_client(module, auth_type="cookie", cookie=cookie)
    ok, dir_id = client.getdirid(args.path)
    payload = {
        "ok": ok,
        "err": client.err,
        "path": args.path,
        "dir_id": dir_id,
        "state_file": str(args.state_path)
    }
    print_result("115 getdirid", payload)


def cmd_ensure_dir(args):
    module = load_py115()
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    client = build_client(module, auth_type="cookie", cookie=cookie)
    ok, dir_id = client.ensure_dir(args.path)
    payload = {
        "ok": ok,
        "err": client.err,
        "path": args.path,
        "dir_id": dir_id,
        "state_file": str(args.state_path)
    }
    print_result("115 ensure dir", payload)


def cmd_addtask(args):
    module = load_py115()
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    client = build_client(module, auth_type="cookie", cookie=cookie)
    dir_ok, dir_id = client.ensure_dir(args.target_path)
    if not dir_ok:
        payload = {
            "ok": False,
            "err": client.err,
            "target_path": args.target_path,
            "resolved_dir_id": dir_id,
            "content": args.content,
            "state_file": str(args.state_path)
        }
        print_result("115 addtask", payload)
        return
    ok, info_hash = client.addtask(args.target_path, args.content)
    payload = {
        "ok": ok,
        "err": client.err,
        "target_path": args.target_path,
        "resolved_dir_id": dir_id,
        "content": args.content,
        "info_hash": info_hash,
        "state_file": str(args.state_path)
    }
    print_result("115 addtask", payload)


def cmd_listdir_path(args):
    module = load_py115()
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    client = build_client(module, auth_type="cookie", cookie=cookie)
    dir_ok, dir_id = client.getdirid(args.path)
    if not dir_ok:
        payload = {
            "ok": False,
            "err": client.err,
            "path": args.path,
            "dir_id": dir_id,
            "state_file": str(args.state_path)
        }
        print_result("115 listdir path", payload)
        return
    ok, items = client.listdir(cid=dir_id, offset=args.offset, limit=args.limit)
    payload = {
        "ok": ok,
        "err": client.err,
        "path": args.path,
        "dir_id": dir_id,
        "offset": args.offset,
        "limit": args.limit,
        "count": len(items) if ok else 0,
        "items": items if args.show_items else [],
        "state_file": str(args.state_path)
    }
    print_result("115 listdir path", payload)


def cmd_move(args):
    module = load_py115()
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    client = build_client(module, auth_type="cookie", cookie=cookie)
    dir_ok, dir_id = client.ensure_dir(args.target_path)
    payload = {
        "ok": False,
        "err": client.err,
        "file_ids": args.file_id,
        "target_path": args.target_path,
        "target_dir_id": dir_id,
        "execute": args.execute,
        "state_file": str(args.state_path)
    }
    if not dir_ok:
        print_result("115 move", payload)
        return
    if not args.execute:
        payload["ok"] = True
        payload["dry_run"] = True
        payload["err"] = None
        print_result("115 move", payload)
        return
    ret = client.move(file_ids=args.file_id, to_dir_id=dir_id)
    payload["ok"] = ret
    payload["err"] = client.err
    print_result("115 move", payload)


def cmd_rename(args):
    module = load_py115()
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    client = build_client(module, auth_type="cookie", cookie=cookie)
    payload = {
        "ok": False,
        "err": None,
        "file_id": args.file_id,
        "new_name": args.new_name,
        "execute": args.execute,
        "state_file": str(args.state_path)
    }
    if not args.execute:
        payload["ok"] = True
        payload["dry_run"] = True
        print_result("115 rename", payload)
        return
    ret = client.rename(file_id=args.file_id, new_name=args.new_name)
    payload["ok"] = ret
    payload["err"] = client.err
    print_result("115 rename", payload)


def cmd_delete(args):
    module = load_py115()
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    client = build_client(module, auth_type="cookie", cookie=cookie)
    payload = {
        "ok": False,
        "err": None,
        "file_ids": args.file_id,
        "execute": args.execute,
        "state_file": str(args.state_path)
    }
    if not args.execute:
        payload["ok"] = True
        payload["dry_run"] = True
        print_result("115 delete", payload)
        return
    ret = client.delete(file_ids=args.file_id)
    payload["ok"] = ret
    payload["err"] = client.err
    print_result("115 delete", payload)


def cmd_remote_stat(args):
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    fs = build_remote_fs(cookie)
    ok, item = fs.stat(args.path)
    print_result("115 remote stat", {
        "ok": ok,
        "err": fs.err,
        "path": args.path,
        "item": item,
        "state_file": str(args.state_path)
    })


def cmd_remote_list(args):
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    fs = build_remote_fs(cookie)
    ok, items = fs.listdir(args.path, offset=args.offset, limit=args.limit)
    print_result("115 remote list", {
        "ok": ok,
        "err": fs.err,
        "path": args.path,
        "offset": args.offset,
        "limit": args.limit,
        "count": len(items) if ok else 0,
        "items": items if args.show_items else [],
        "state_file": str(args.state_path)
    })


def cmd_remote_walk(args):
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    fs = build_remote_fs(cookie)
    ok, items = fs.walk(args.path, max_depth=args.max_depth)
    print_result("115 remote walk", {
        "ok": ok,
        "err": fs.err,
        "path": args.path,
        "max_depth": args.max_depth,
        "count": len(items) if ok else 0,
        "items": items if args.show_items else [],
        "state_file": str(args.state_path)
    })


def cmd_remote_move_path(args):
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    fs = build_remote_fs(cookie)
    ok, plan = fs.move_path(
        args.source_path,
        args.target_path,
        execute=args.execute,
        overwrite=args.overwrite
    )
    print_result("115 remote move path", {
        "ok": ok,
        "err": fs.err,
        "source_path": args.source_path,
        "target_path": args.target_path,
        "execute": args.execute,
        "overwrite": args.overwrite,
        "plan": plan,
        "state_file": str(args.state_path)
    })


def cmd_remote_delete_path(args):
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    fs = build_remote_fs(cookie)
    ok, plan = fs.delete_path(args.path, execute=args.execute)
    print_result("115 remote delete path", {
        "ok": ok,
        "err": fs.err,
        "path": args.path,
        "execute": args.execute,
        "plan": plan,
        "state_file": str(args.state_path)
    })


def cmd_remote_download_url(args):
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    fs = build_remote_fs(cookie)
    ok, link = fs.download_url(args.path, user_agent=args.user_agent)
    safe_link = dict(link or {})
    if safe_link.get("url") and not args.show_url:
        safe_link["url_prefix"] = safe_link.get("url")[:80]
        safe_link["url"] = "<hidden; pass --show-url to print>"
        raw = dict(safe_link.get("raw") or {})
        raw_url = dict(raw.get("url") or {})
        if raw_url.get("url"):
            raw_url["url_prefix"] = raw_url.get("url")[:80]
            raw_url["url"] = "<hidden; pass --show-url to print>"
            raw["url"] = raw_url
            safe_link["raw"] = raw
    print_result("115 remote download url", {
        "ok": ok,
        "err": fs.err,
        "path": args.path,
        "show_url": args.show_url,
        "link": safe_link,
        "state_file": str(args.state_path)
    })


def cmd_remote_plan(args):
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    fs = build_remote_fs(cookie)
    planner_module = load_transfer_planner()
    planner = planner_module.Pan115TransferPlanner(fs, config=Config().get_config())
    media_info = {
        "type": args.media_type,
        "title": args.title,
        "year": args.year,
        "season": args.season,
        "episode": args.episode,
        "part": args.part,
        "videoFormat": args.video_format,
        "releaseGroup": args.release_group,
        "tmdbid": args.tmdbid
    }
    ok, plans = planner.plan(
        source_path=args.source_path,
        media_info=media_info,
        library_root=args.library_root,
        execute=args.execute,
        overwrite=args.overwrite
    )
    print_result("115 remote transfer plan", {
        "ok": ok,
        "err": planner.err,
        "source_path": args.source_path,
        "library_root": args.library_root,
        "execute": args.execute,
        "overwrite": args.overwrite,
        "media_info": media_info,
        "count": len(plans),
        "plans": plans,
        "state_file": str(args.state_path)
    })


def _join_remote_path(parent, name):
    parent = _strip_115_root_name(parent)
    if parent == "/根目录":
        parent = "/"
    elif parent.startswith("/根目录/"):
        parent = parent[len("/根目录"):]
    name = (name or "").replace("\\", "/").strip("/")
    if not parent:
        parent = "/"
    if parent == "/":
        return "/%s" % name if name else "/"
    return "%s/%s" % (parent, name) if name else parent


def _strip_115_root_name(path):
    path = (path or "/").replace("\\", "/").rstrip("/")
    if path == "/根目录":
        return "/"
    if path.startswith("/根目录/"):
        return path[len("/根目录"):]
    return path or "/"


def _resolve_task_source_path(client, task):
    task = client.normalize_task(task)
    name = task.get("name")
    file_id = task.get("file_id")
    if file_id:
        ok, file_path = client.getiddir(file_id)
        if ok and file_path and file_path != "/":
            file_path = _strip_115_root_name(file_path)
            if not name or file_path.endswith("/%s" % name) or file_path == name:
                return file_path
            return _join_remote_path(file_path, name)
    parent_id = task.get("wp_path_id") or task.get("dir_id")
    if parent_id:
        ok, parent_path = client.getiddir(parent_id)
        if ok and parent_path:
            return _join_remote_path(parent_path, name)
    return ""


def cmd_remote_plan_task(args):
    module = load_py115()
    state = load_state(args.state_path)
    cookie = resolve_cookie(args, state)
    client = build_client(module, auth_type="cookie", cookie=cookie)
    ok, tasks = client.gettasklist(page=args.page)
    if not ok:
        print_result("115 remote task transfer plan", {
            "ok": False,
            "err": client.err,
            "info_hash": args.info_hash,
            "state_file": str(args.state_path)
        })
        return
    task = _find_task_by_hash(tasks, args.info_hash)
    if not task:
        print_result("115 remote task transfer plan", {
            "ok": False,
            "err": "115 task not found",
            "info_hash": args.info_hash,
            "state_file": str(args.state_path)
        })
        return
    source_path = _resolve_task_source_path(client, task)
    if not source_path:
        print_result("115 remote task transfer plan", {
            "ok": False,
            "err": client.err or "failed to resolve task source path",
            "info_hash": args.info_hash,
            "task": task,
            "state_file": str(args.state_path)
        })
        return

    fs = build_remote_fs(cookie)
    planner_module = load_transfer_planner()
    planner = planner_module.Pan115TransferPlanner(fs, config=Config().get_config())
    media_info = {
        "type": args.media_type,
        "title": args.title or task.get("name"),
        "year": args.year,
        "season": args.season,
        "episode": args.episode,
        "part": args.part,
        "videoFormat": args.video_format,
        "releaseGroup": args.release_group,
        "tmdbid": args.tmdbid
    }
    ok, plans = planner.plan(
        source_path=source_path,
        media_info=media_info,
        library_root=args.library_root,
        execute=args.execute,
        overwrite=args.overwrite
    )
    print_result("115 remote task transfer plan", {
        "ok": ok,
        "err": planner.err,
        "info_hash": args.info_hash,
        "source_path": source_path,
        "library_root": args.library_root,
        "execute": args.execute,
        "overwrite": args.overwrite,
        "media_info": media_info,
        "task": task,
        "count": len(plans),
        "plans": plans,
        "state_file": str(args.state_path)
    })


def cmd_alist_open_get_token(args):
    print_result("alist 115 get token", {
        "ok": False,
        "err": "OpenAPI route is intentionally disabled; use session/cookie client instead.",
        "uid": args.uid,
        "state_file": str(args.state_path)
    })


def cmd_alist_open_auth_device_code(args):
    print_result("alist 115 auth device code", {
        "ok": False,
        "err": "OpenAPI route is intentionally disabled; use session/cookie client instead.",
        "app_id": args.app_id or "",
        "state_file": str(args.state_path)
    })


def cmd_full_check(args):
    module = load_py115()
    state = load_state(args.state_path)
    source = state.get("qrcode_source") or args.qrcode_source
    cookie = resolve_cookie(args, state)
    if not cookie:
        session = state.get("qrcode_session") or {}
        uid = args.uid or session.get("uid") or state.get("qrcode_uid")
        if uid:
            exchange_client = build_client(module, auth_type="qrcode", qrcode_source=source)
            ok, cookie = exchange_client.get_qrcode_result(uid, source)
            if ok:
                state["cookie"] = cookie
                state["last_exchange_uid"] = uid
                save_state(args.state_path, state)
            else:
                print_result("115 full check", {
                    "ok": False,
                    "step": "exchange",
                    "err": exchange_client.err,
                    "uid": uid,
                    "state_file": str(args.state_path)
                })
                return

    client = build_client(module, auth_type="cookie", cookie=cookie)
    login_ok = client.login()
    if not login_ok:
        print_result("115 full check", {
            "ok": False,
            "step": "login",
            "err": client.err,
            "state_file": str(args.state_path)
        })
        return

    dir_ok, items = client.listdir(cid=args.cid, offset=args.offset, limit=args.limit)
    print_result("115 full check", {
        "ok": dir_ok,
        "step": "listdir",
        "err": client.err,
        "uid": client.uid,
        "sign_ok": bool(client.sign),
        "cid": args.cid,
        "count": len(items) if dir_ok else 0,
        "items": items if args.show_items else [],
        "state_file": str(args.state_path)
    })


def build_parser():
    parser = argparse.ArgumentParser(description="Standalone 115 client test helper")
    parser.add_argument("--state-path", help="persistent state file path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("qrcode-create", help="create a new qrcode session")
    create_parser.add_argument("--qrcode-source", default="web")
    create_parser.set_defaults(func=cmd_qrcode_create)

    status_parser = subparsers.add_parser("qrcode-status", help="check qrcode session status")
    status_parser.add_argument("--qrcode-source", default="web")
    status_parser.set_defaults(func=cmd_qrcode_status)

    exchange_parser = subparsers.add_parser("qrcode-exchange", help="exchange a scanned qrcode uid to cookie")
    exchange_parser.add_argument("--uid", help="qrcode uid; defaults to state file")
    exchange_parser.add_argument("--qrcode-source", default="web")
    exchange_parser.set_defaults(func=cmd_qrcode_exchange)

    login_parser = subparsers.add_parser("cookie-login", help="verify cookie login")
    login_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    login_parser.set_defaults(func=cmd_cookie_login)

    listdir_parser = subparsers.add_parser("listdir", help="call listdir with saved cookie")
    listdir_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    listdir_parser.add_argument("--cid", default="0")
    listdir_parser.add_argument("--offset", type=int, default=0)
    listdir_parser.add_argument("--limit", type=int, default=5)
    listdir_parser.add_argument("--show-items", action="store_true")
    listdir_parser.set_defaults(func=cmd_listdir)

    tasklist_parser = subparsers.add_parser("gettasklist", help="call gettasklist with saved cookie")
    tasklist_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    tasklist_parser.add_argument("--page", type=int, default=1)
    tasklist_parser.add_argument("--show-tasks", action="store_true")
    tasklist_parser.set_defaults(func=cmd_gettasklist)

    gettask_parser = subparsers.add_parser("gettask", help="find a task by info_hash")
    gettask_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    gettask_parser.add_argument("--page", type=int, default=1)
    gettask_parser.add_argument("--info-hash", required=True)
    gettask_parser.set_defaults(func=cmd_gettask)

    wait_task_parser = subparsers.add_parser("wait-task", help="poll a task until target status or timeout")
    wait_task_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    wait_task_parser.add_argument("--info-hash", required=True)
    wait_task_parser.add_argument("--target-status", type=int, default=2)
    wait_task_parser.add_argument("--target-percent", type=float, default=100.0)
    wait_task_parser.add_argument("--interval", type=int, default=10)
    wait_task_parser.add_argument("--timeout", type=int, default=600)
    wait_task_parser.set_defaults(func=cmd_wait_task)

    getdirid_parser = subparsers.add_parser("getdirid", help="resolve a 115 path to dir id")
    getdirid_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    getdirid_parser.add_argument("--path", default="/")
    getdirid_parser.set_defaults(func=cmd_getdirid)

    ensure_dir_parser = subparsers.add_parser("ensure-dir", help="ensure a 115 directory exists")
    ensure_dir_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    ensure_dir_parser.add_argument("--path", required=True)
    ensure_dir_parser.set_defaults(func=cmd_ensure_dir)

    addtask_parser = subparsers.add_parser("addtask", help="create a 115 offline task")
    addtask_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    addtask_parser.add_argument("--target-path", required=True, help="115 target directory path")
    addtask_parser.add_argument("--content", required=True, help="magnet or http/https url")
    addtask_parser.set_defaults(func=cmd_addtask)

    listdir_path_parser = subparsers.add_parser("listdir-path", help="resolve a 115 path and list its items")
    listdir_path_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    listdir_path_parser.add_argument("--path", required=True)
    listdir_path_parser.add_argument("--offset", type=int, default=0)
    listdir_path_parser.add_argument("--limit", type=int, default=20)
    listdir_path_parser.add_argument("--show-items", action="store_true")
    listdir_path_parser.set_defaults(func=cmd_listdir_path)

    move_parser = subparsers.add_parser("move", help="move 115 file ids to a target path; dry-run by default")
    move_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    move_parser.add_argument("--file-id", action="append", required=True, help="115 file/folder id; repeatable")
    move_parser.add_argument("--target-path", required=True, help="115 target directory path, created if missing")
    move_parser.add_argument("--execute", action="store_true", help="actually mutate 115 remote files")
    move_parser.set_defaults(func=cmd_move)

    rename_parser = subparsers.add_parser("rename", help="rename a 115 file id; dry-run by default")
    rename_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    rename_parser.add_argument("--file-id", required=True)
    rename_parser.add_argument("--new-name", required=True)
    rename_parser.add_argument("--execute", action="store_true", help="actually mutate 115 remote files")
    rename_parser.set_defaults(func=cmd_rename)

    delete_parser = subparsers.add_parser("delete", help="delete 115 file ids; dry-run by default")
    delete_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    delete_parser.add_argument("--file-id", action="append", required=True, help="115 file/folder id; repeatable")
    delete_parser.add_argument("--execute", action="store_true", help="actually mutate 115 remote files")
    delete_parser.set_defaults(func=cmd_delete)

    remote_stat_parser = subparsers.add_parser("remote-stat", help="stat a 115 remote path")
    remote_stat_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    remote_stat_parser.add_argument("--path", required=True)
    remote_stat_parser.set_defaults(func=cmd_remote_stat)

    remote_list_parser = subparsers.add_parser("remote-list", help="list a 115 remote path through RemoteFS")
    remote_list_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    remote_list_parser.add_argument("--path", default="/")
    remote_list_parser.add_argument("--offset", type=int, default=0)
    remote_list_parser.add_argument("--limit", type=int, default=20)
    remote_list_parser.add_argument("--show-items", action="store_true")
    remote_list_parser.set_defaults(func=cmd_remote_list)

    remote_walk_parser = subparsers.add_parser("remote-walk", help="walk a 115 remote path through RemoteFS")
    remote_walk_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    remote_walk_parser.add_argument("--path", default="/")
    remote_walk_parser.add_argument("--max-depth", type=int)
    remote_walk_parser.add_argument("--show-items", action="store_true")
    remote_walk_parser.set_defaults(func=cmd_remote_walk)

    remote_move_parser = subparsers.add_parser("remote-move-path", help="move a remote path; dry-run by default")
    remote_move_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    remote_move_parser.add_argument("--source-path", required=True)
    remote_move_parser.add_argument("--target-path", required=True)
    remote_move_parser.add_argument("--execute", action="store_true", help="actually mutate 115 remote files")
    remote_move_parser.add_argument("--overwrite", action="store_true", help="delete existing target before moving")
    remote_move_parser.set_defaults(func=cmd_remote_move_path)

    remote_delete_parser = subparsers.add_parser("remote-delete-path", help="delete a remote path; dry-run by default")
    remote_delete_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    remote_delete_parser.add_argument("--path", required=True)
    remote_delete_parser.add_argument("--execute", action="store_true", help="actually mutate 115 remote files")
    remote_delete_parser.set_defaults(func=cmd_remote_delete_path)

    remote_download_url_parser = subparsers.add_parser(
        "remote-download-url",
        help="resolve a 115 remote file path to a temporary download URL"
    )
    remote_download_url_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    remote_download_url_parser.add_argument("--path", required=True)
    remote_download_url_parser.add_argument("--user-agent")
    remote_download_url_parser.add_argument("--show-url", action="store_true", help="print full temporary URL")
    remote_download_url_parser.set_defaults(func=cmd_remote_download_url)

    remote_plan_parser = subparsers.add_parser("remote-plan", help="build a 115 remote transfer plan; dry-run by default")
    remote_plan_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    remote_plan_parser.add_argument("--source-path", required=True)
    remote_plan_parser.add_argument("--library-root", required=True)
    remote_plan_parser.add_argument("--media-type", default="movie", choices=["movie", "tv", "anime"])
    remote_plan_parser.add_argument("--title", required=True)
    remote_plan_parser.add_argument("--year")
    remote_plan_parser.add_argument("--season")
    remote_plan_parser.add_argument("--episode")
    remote_plan_parser.add_argument("--part")
    remote_plan_parser.add_argument("--video-format")
    remote_plan_parser.add_argument("--release-group")
    remote_plan_parser.add_argument("--tmdbid")
    remote_plan_parser.add_argument("--execute", action="store_true", help="actually mutate 115 remote files")
    remote_plan_parser.add_argument("--overwrite", action="store_true", help="delete existing target before moving")
    remote_plan_parser.set_defaults(func=cmd_remote_plan)

    remote_plan_task_parser = subparsers.add_parser(
        "remote-plan-task",
        help="build a 115 remote transfer plan from an offline task; dry-run by default"
    )
    remote_plan_task_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    remote_plan_task_parser.add_argument("--info-hash", required=True)
    remote_plan_task_parser.add_argument("--page", type=int, default=1)
    remote_plan_task_parser.add_argument("--library-root", required=True)
    remote_plan_task_parser.add_argument("--media-type", default="movie", choices=["movie", "tv", "anime"])
    remote_plan_task_parser.add_argument("--title", help="defaults to 115 task name")
    remote_plan_task_parser.add_argument("--year")
    remote_plan_task_parser.add_argument("--season")
    remote_plan_task_parser.add_argument("--episode")
    remote_plan_task_parser.add_argument("--part")
    remote_plan_task_parser.add_argument("--video-format")
    remote_plan_task_parser.add_argument("--release-group")
    remote_plan_task_parser.add_argument("--tmdbid")
    remote_plan_task_parser.add_argument("--execute", action="store_true", help="actually mutate 115 remote files")
    remote_plan_task_parser.add_argument("--overwrite", action="store_true", help="delete existing target before moving")
    remote_plan_task_parser.set_defaults(func=cmd_remote_plan_task)

    alist_token_parser = subparsers.add_parser(
        "alist-open-get-token",
        help="disabled research command; OpenAPI is not used by the session client"
    )
    alist_token_parser.add_argument("--uid", required=True)
    alist_token_parser.add_argument("--code-verifier", required=True)
    alist_token_parser.set_defaults(func=cmd_alist_open_get_token)

    alist_auth_parser = subparsers.add_parser(
        "alist-open-auth-device-code",
        help="disabled research command; OpenAPI is not used by the session client"
    )
    alist_auth_parser.add_argument("--app-id", default="")
    alist_auth_parser.set_defaults(func=cmd_alist_open_auth_device_code)

    full_parser = subparsers.add_parser("full-check", help="exchange cookie if needed, then login and listdir")
    full_parser.add_argument("--uid", help="qrcode uid; defaults to state file")
    full_parser.add_argument("--cookie", help="cookie string; defaults to state file")
    full_parser.add_argument("--qrcode-source", default="web")
    full_parser.add_argument("--cid", default="0")
    full_parser.add_argument("--offset", type=int, default=0)
    full_parser.add_argument("--limit", type=int, default=5)
    full_parser.add_argument("--show-items", action="store_true")
    full_parser.set_defaults(func=cmd_full_check)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.state_path = get_state_path(args.state_path)
    args.func(args)


if __name__ == "__main__":
    main()
