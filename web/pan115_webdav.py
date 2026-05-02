import posixpath
from email.utils import formatdate
from urllib.parse import quote, unquote, urlparse
from xml.sax.saxutils import escape

from flask import Blueprint, make_response, redirect, request

from app.downloader.client.pan115_service import get_pan115_remote_fs
from config import Config


pan115_webdav_bp = Blueprint("pan115_webdav", __name__)

DAV_METHODS = ["OPTIONS", "PROPFIND", "HEAD", "GET", "MKCOL", "DELETE", "MOVE", "PUT"]


@pan115_webdav_bp.route("/", defaults={"req_path": ""}, methods=DAV_METHODS)
@pan115_webdav_bp.route("/<path:req_path>", methods=DAV_METHODS)
def pan115_webdav(req_path):
    cfg = _config()
    if not _truthy(cfg.get("webdav_enabled")):
        return _plain("115 WebDAV is disabled", 404)
    if not _check_auth(cfg):
        return _auth_required()

    method = request.method.upper()
    if method == "OPTIONS":
        return _options()
    if method == "PUT":
        return _plain("115 WebDAV PUT is not implemented yet", 501)

    readonly = _truthy(cfg.get("webdav_readonly"), default=True)
    try:
        fs = get_pan115_remote_fs(config=cfg)
    except Exception as err:
        return _plain(err, 503)
    remote_path = _remote_path(cfg, req_path)
    if not remote_path:
        return _plain("Path escapes configured 115 WebDAV root", 400)

    if method == "PROPFIND":
        return _propfind(fs, cfg, remote_path, req_path)
    if method in ["GET", "HEAD"]:
        return _get_or_head(fs, remote_path)
    if readonly:
        return _plain("115 WebDAV is readonly", 403)
    if method == "MKCOL":
        return _mkcol(fs, remote_path)
    if method == "DELETE":
        return _delete(fs, remote_path)
    if method == "MOVE":
        return _move(fs, cfg, remote_path)
    return _plain("Method not allowed", 405)


def _config():
    return Config().get_config("client115") or {}


def _check_auth(cfg):
    user = str(cfg.get("webdav_user") or "")
    password = str(cfg.get("webdav_password") or "")
    if not user and not password:
        return True
    auth = request.authorization
    if not auth:
        return False
    return auth.username == user and auth.password == password


def _auth_required():
    resp = _plain("Authentication required", 401)
    resp.headers["WWW-Authenticate"] = 'Basic realm="nas-tools 115 WebDAV"'
    return resp


def _options():
    resp = make_response("", 200)
    _dav_headers(resp)
    return resp


def _propfind(fs, cfg, remote_path, req_path):
    depth = request.headers.get("Depth", "1")
    ret, item = fs.stat(remote_path)
    if not ret:
        return _plain(fs.err or "Not found", 404)

    rows = [(_href(req_path, item.get("is_dir")), item)]
    if item.get("is_dir") and depth != "0":
        ret, items = fs.listdir(remote_path)
        if not ret:
            return _plain(fs.err or "List failed", 500)
        for child in items:
            child_req_path = _child_req_path(req_path, child.get("name"))
            rows.append((_href(child_req_path, child.get("is_dir")), child))

    xml = ['<?xml version="1.0" encoding="utf-8"?>', '<D:multistatus xmlns:D="DAV:">']
    for href, row in rows:
        xml.append(_prop_response(href, row))
    xml.append("</D:multistatus>")
    resp = make_response("\n".join(xml), 207)
    resp.headers["Content-Type"] = "application/xml; charset=utf-8"
    _dav_headers(resp)
    return resp


def _get_or_head(fs, remote_path):
    ret, item = fs.stat(remote_path)
    if not ret:
        return _plain(fs.err or "Not found", 404)
    if item.get("is_dir"):
        if request.method.upper() == "HEAD":
            resp = make_response("", 200)
        else:
            ret, items = fs.listdir(remote_path)
            if not ret:
                return _plain(fs.err or "List failed", 500)
            body = "\n".join([child.get("name") or "" for child in items])
            resp = make_response(body, 200)
            resp.headers["Content-Type"] = "text/plain; charset=utf-8"
        _dav_headers(resp)
        return resp

    download_url = None
    if hasattr(fs, "download_url"):
        ret, link = fs.download_url(remote_path, user_agent=request.headers.get("User-Agent"))
        if ret:
            download_url = link.get("url") if isinstance(link, dict) else link
    if download_url:
        return redirect(download_url, code=302)
    return _plain(fs.err or "115 download URL resolve failed", 502)


def _mkcol(fs, remote_path):
    if fs.exists(remote_path):
        return _plain("Collection already exists", 405)
    ret, _ = fs.ensure_dir(remote_path)
    if not ret:
        return _plain(fs.err or "MKCOL failed", 409)
    resp = make_response("", 201)
    _dav_headers(resp)
    return resp


def _delete(fs, remote_path):
    ret, plan = fs.delete_path(remote_path, execute=True)
    if not ret:
        return _plain(plan.get("error") or fs.err or "DELETE failed", 404)
    resp = make_response("", 204)
    _dav_headers(resp)
    return resp


def _move(fs, cfg, remote_path):
    destination = request.headers.get("Destination")
    if not destination:
        return _plain("Missing Destination header", 400)
    target_req_path = _destination_req_path(destination)
    if target_req_path is None:
        return _plain("Destination must stay under /dav/115", 400)
    target_path = _remote_path(cfg, target_req_path)
    if not target_path:
        return _plain("Destination escapes configured 115 WebDAV root", 400)
    overwrite = request.headers.get("Overwrite", "T").upper() != "F"
    ret, plan = fs.move_path(remote_path, target_path, execute=True, overwrite=overwrite)
    if not ret:
        status = 412 if plan.get("target_exists") else 409
        return _plain(plan.get("error") or fs.err or "MOVE failed", status)
    resp = make_response("", 201)
    _dav_headers(resp)
    return resp


def _prop_response(href, item):
    is_dir = bool(item.get("is_dir"))
    size = int(item.get("size") or 0)
    display_name = item.get("name") or ""
    if href.rstrip("/") == "/dav/115":
        display_name = ""
    resourcetype = "<D:collection/>" if is_dir else ""
    length = "" if is_dir else "<D:getcontentlength>%s</D:getcontentlength>" % size
    modified = formatdate(usegmt=True)
    return """<D:response>
<D:href>{href}</D:href>
<D:propstat>
<D:prop>
<D:displayname>{display_name}</D:displayname>
<D:resourcetype>{resourcetype}</D:resourcetype>
{length}
<D:getlastmodified>{modified}</D:getlastmodified>
</D:prop>
<D:status>HTTP/1.1 200 OK</D:status>
</D:propstat>
</D:response>""".format(
        href=escape(href),
        display_name=escape(display_name),
        resourcetype=resourcetype,
        length=length,
        modified=modified
    )


def _remote_path(cfg, req_path):
    root = _normalize_remote_root(cfg.get("webdav_root") or "/")
    req_path = unquote(req_path or "").replace("\\", "/").strip("/")
    if not req_path:
        return root
    remote_path = posixpath.normpath(posixpath.join(root, req_path))
    if root != "/" and remote_path != root and not remote_path.startswith("%s/" % root.rstrip("/")):
        return None
    return remote_path


def _normalize_remote_root(path):
    path = str(path or "/").replace("\\", "/").strip()
    if not path.startswith("/"):
        path = "/%s" % path
    return posixpath.normpath(path) if path != "/" else "/"


def _href(req_path, is_dir=False):
    req_path = (req_path or "").replace("\\", "/").strip("/")
    href = "/dav/115"
    if req_path:
        href = "%s/%s" % (href, quote(req_path, safe="/"))
    if is_dir and not href.endswith("/"):
        href = "%s/" % href
    return href


def _child_req_path(parent_req_path, child_name):
    parent_req_path = (parent_req_path or "").strip("/")
    child_name = str(child_name or "").strip("/")
    if not parent_req_path:
        return child_name
    return "%s/%s" % (parent_req_path, child_name)


def _destination_req_path(destination):
    parsed = urlparse(destination)
    path = unquote(parsed.path or destination).replace("\\", "/")
    marker = "/dav/115"
    if path == marker:
        return ""
    if path.startswith("%s/" % marker):
        return path[len(marker):].strip("/")
    return None


def _dav_headers(resp):
    resp.headers["DAV"] = "1, 2"
    resp.headers["Allow"] = ", ".join(DAV_METHODS)
    resp.headers["MS-Author-Via"] = "DAV"
    return resp


def _plain(message, status):
    resp = make_response(str(message or ""), status)
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    _dav_headers(resp)
    return resp


def _truthy(value, default=False):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ["1", "true", "yes", "on"]
