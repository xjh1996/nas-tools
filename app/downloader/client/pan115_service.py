from app.downloader.client.pan115_base import Pan115Provider
from app.downloader.client.pan115_models import Pan115ProviderType
from app.downloader.client.pan115_remote_fs import Pan115RemoteFS
from app.downloader.client.pan115_session import Pan115SessionProvider
from config import Config


def normalize_pan115_path(path, default="/media"):
    path = str(path or default).replace("\\", "/").strip()
    if not path:
        path = default
    if not path.startswith("/"):
        path = "/%s" % path
    return "/" if path == "/" else path.rstrip("/")


def join_pan115_path(root, *parts):
    root = normalize_pan115_path(root)
    suffix = "/".join([str(part).strip("/") for part in parts if str(part or "").strip("/")])
    if not suffix:
        return root
    return "%s/%s" % (root.rstrip("/"), suffix)


def resolve_pan115_root(config=None):
    cfg = config if config is not None else (Config().get_config("client115") or {})
    if cfg.get("remote_root_path"):
        return normalize_pan115_path(cfg.get("remote_root_path"))
    for key, suffix in [
        ("webdav_root", ""),
        ("remote_download_path", "downloads"),
        ("remote_movie_path", "library/movies"),
        ("remote_tv_path", "library/tv"),
        ("remote_anime_path", "library/anime")
    ]:
        path = normalize_pan115_path(cfg.get(key), default="")
        if path and path != "/" and path.endswith("/%s" % suffix):
            return normalize_pan115_path(path[:-(len(suffix) + 1)] or "/")
    return normalize_pan115_path(
        cfg.get("webdav_root")
        or cfg.get("remote_download_path")
        or "/media"
    )


def derive_pan115_paths(config=None):
    cfg = dict(config if config is not None else (Config().get_config("client115") or {}))
    root = resolve_pan115_root(cfg)
    derived = {
        "remote_root_path": root,
        "remote_download_path": join_pan115_path(root, "downloads"),
        "remote_library_path": join_pan115_path(root, "library"),
        "remote_movie_path": join_pan115_path(root, "library", "movies"),
        "remote_tv_path": join_pan115_path(root, "library", "tv"),
        "remote_anime_path": join_pan115_path(root, "library", "anime"),
        "webdav_root": root
    }
    return {
        key: normalize_pan115_path(cfg.get(key), default=value) if cfg.get(key) else value
        for key, value in derived.items()
    }


def get_pan115_config():
    cfg = dict(Config().get_config("client115") or {})
    for key, value in derive_pan115_paths(cfg).items():
        if not cfg.get(key):
            cfg[key] = value
    return cfg


def get_pan115_provider(config=None, persist=False):
    cfg = dict(config or get_pan115_config())
    provider_type = Pan115Provider.resolve_provider_type(cfg)
    if provider_type != Pan115ProviderType.SESSION:
        raise ValueError("115 OpenAPI provider is disabled; use session provider")
    return Pan115SessionProvider(cfg, persist=persist)


def get_pan115_remote_fs(config=None, persist=False):
    return Pan115RemoteFS(get_pan115_provider(config=config, persist=persist))
