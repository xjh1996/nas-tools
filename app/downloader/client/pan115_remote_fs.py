import posixpath


class Pan115RemoteFS:
    """
    115 remote filesystem adapter.

    This layer intentionally exposes file-system-like primitives without
    leaking 115 API field names into higher-level media transfer code.
    """

    def __init__(self, provider):
        self.provider = provider
        self.err = None

    def ensure_login(self):
        ret = self.provider.ensure_login()
        self.err = self.provider.err
        return ret

    def normalize_path(self, path):
        path = (path or "/").replace("\\", "/").strip()
        if not path:
            return "/"
        if not path.startswith("/"):
            path = "/%s" % path
        return posixpath.normpath(path) if path != "/" else "/"

    def dirname(self, path):
        path = self.normalize_path(path)
        parent = posixpath.dirname(path)
        return parent or "/"

    def basename(self, path):
        path = self.normalize_path(path)
        return "" if path == "/" else posixpath.basename(path)

    def ensure_dir(self, path):
        ret, dir_id = self.provider.ensure_dir(self.normalize_path(path))
        self.err = self.provider.err
        return ret, dir_id

    def listdir_id(self, cid="0", offset=0, limit=1000):
        ret, items = self.provider.listdir(cid=cid or "0", offset=offset, limit=limit)
        self.err = self.provider.err
        if not ret:
            return False, []
        return True, [self.normalize_item(item) for item in items or []]

    def listdir(self, path="/", offset=0, limit=1000):
        path = self.normalize_path(path)
        ret, dir_id = self.provider.getdirid(path)
        self.err = self.provider.err
        if not ret:
            return False, []
        ret, items = self.listdir_id(cid=dir_id, offset=offset, limit=limit)
        if not ret:
            return False, []
        for item in items:
            item["path"] = self.join(path, item.get("name"))
            item["parent_path"] = path
        return True, items

    def stat(self, path):
        path = self.normalize_path(path)
        if path == "/":
            return True, {
                "id": "0",
                "name": "",
                "path": "/",
                "parent_path": "/",
                "is_dir": True,
                "is_file": False,
                "size": 0,
                "raw": {}
            }
        parent_path = self.dirname(path)
        name = self.basename(path)
        ret, items = self.listdir(parent_path)
        if not ret:
            return False, {}
        for item in items:
            if item.get("name") == name:
                item["path"] = path
                return True, item
        self.err = "115 remote path not found: %s" % path
        return False, {}

    def exists(self, path):
        ret, _ = self.stat(path)
        return ret

    def isdir(self, path):
        ret, item = self.stat(path)
        return bool(ret and item.get("is_dir"))

    def isfile(self, path):
        ret, item = self.stat(path)
        return bool(ret and item.get("is_file"))

    def getsize(self, path):
        ret, item = self.stat(path)
        if not ret:
            return 0
        return int(item.get("size") or 0)

    def walk(self, path="/", max_depth=None):
        path = self.normalize_path(path)
        ret, items = self.listdir(path)
        if not ret:
            return False, []
        rows = []
        self._walk_items(path, items, rows, depth=0, max_depth=max_depth)
        return True, rows

    def move_id(self, file_ids, target_dir):
        ret, dir_id = self.ensure_dir(target_dir)
        if not ret:
            return False
        ret = self.provider.move(file_ids=file_ids, to_dir_id=dir_id)
        self.err = self.provider.err
        return ret

    def rename_id(self, file_id, new_name):
        ret = self.provider.rename(file_id=file_id, new_name=new_name)
        self.err = self.provider.err
        return ret

    def delete_id(self, file_ids):
        ret = self.provider.delete(file_ids=file_ids)
        self.err = self.provider.err
        return ret

    def move_path(self, source_path, target_path, execute=False):
        source_path = self.normalize_path(source_path)
        target_path = self.normalize_path(target_path)
        ret, source = self.stat(source_path)
        if not ret:
            return False, self._plan("move", source_path, target_path, execute, error=self.err)
        target_dir = self.dirname(target_path)
        target_name = self.basename(target_path)
        ret, target_dir_id = self.ensure_dir(target_dir)
        if not ret:
            return False, self._plan("move", source_path, target_path, execute, error=self.err)

        plan = self._plan(
            "move",
            source_path,
            target_path,
            execute,
            source=source,
            target_dir=target_dir,
            target_dir_id=target_dir_id,
            rename=source.get("name") != target_name
        )
        if not execute:
            return True, plan

        if not self.move_id(source.get("id"), target_dir):
            plan["error"] = self.err
            return False, plan
        if source.get("name") != target_name and not self.rename_id(source.get("id"), target_name):
            plan["error"] = self.err
            return False, plan
        plan["executed"] = True
        return True, plan

    def delete_path(self, path, execute=False):
        path = self.normalize_path(path)
        ret, item = self.stat(path)
        if not ret:
            return False, self._plan("delete", path, None, execute, error=self.err)
        plan = self._plan("delete", path, None, execute, source=item)
        if not execute:
            return True, plan
        ret = self.delete_id(item.get("id"))
        plan["executed"] = ret
        plan["error"] = self.err
        return ret, plan

    def normalize_item(self, item):
        item = dict(item or {})
        name = str(
            item.get("n")
            or item.get("name")
            or item.get("fn")
            or item.get("file_name")
            or ""
        ).strip()
        file_id = str(item.get("fid") or item.get("file_id") or item.get("id") or "").strip()
        dir_id = str(item.get("cid") or "").strip()
        is_session_dir = bool(dir_id and not file_id)
        is_open_dir = str(item.get("fc") or "") == "0" and bool(file_id)
        is_dir = is_session_dir or is_open_dir or bool(item.get("is_dir"))
        item_id = dir_id if is_session_dir else file_id
        return {
            "id": item_id,
            "file_id": file_id,
            "dir_id": dir_id,
            "name": name,
            "is_dir": is_dir,
            "is_file": not is_dir,
            "size": self._safe_int(item.get("s") or item.get("size") or item.get("file_size"), 0),
            "sha1": item.get("sha") or item.get("sha1"),
            "pick_code": item.get("pc") or item.get("pick_code"),
            "raw": item
        }

    def join(self, *parts):
        normalized_parts = []
        for part in parts:
            if part is None:
                continue
            part = str(part).replace("\\", "/").strip("/")
            if part:
                normalized_parts.append(part)
        if not normalized_parts:
            return "/"
        return "/%s" % "/".join(normalized_parts)

    def _walk_items(self, parent_path, items, rows, depth, max_depth):
        for item in items:
            rows.append(item)
            if not item.get("is_dir"):
                continue
            if max_depth is not None and depth >= max_depth:
                continue
            item_path = item.get("path") or self.join(parent_path, item.get("name"))
            ret, child_items = self.listdir(item_path)
            if ret:
                self._walk_items(item_path, child_items, rows, depth + 1, max_depth)

    @staticmethod
    def _plan(action, source_path, target_path, execute, **kwargs):
        plan = {
            "action": action,
            "source_path": source_path,
            "target_path": target_path,
            "execute": execute,
            "executed": False
        }
        plan.update(kwargs)
        return plan

    @staticmethod
    def _safe_int(value, default=0):
        try:
            if value is None or value == "":
                return default
            return int(float(value))
        except (TypeError, ValueError):
            return default
