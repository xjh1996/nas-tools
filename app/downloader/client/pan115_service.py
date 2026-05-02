from app.downloader.client.pan115_base import Pan115Provider
from app.downloader.client.pan115_models import Pan115ProviderType
from app.downloader.client.pan115_remote_fs import Pan115RemoteFS
from app.downloader.client.pan115_session import Pan115SessionProvider
from config import Config


def get_pan115_config():
    return Config().get_config("client115") or {}


def get_pan115_provider(config=None, persist=False):
    cfg = dict(config or get_pan115_config())
    provider_type = Pan115Provider.resolve_provider_type(cfg)
    if provider_type != Pan115ProviderType.SESSION:
        raise ValueError("115 OpenAPI provider is disabled; use session provider")
    return Pan115SessionProvider(cfg, persist=persist)


def get_pan115_remote_fs(config=None, persist=False):
    return Pan115RemoteFS(get_pan115_provider(config=config, persist=persist))
