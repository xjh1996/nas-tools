from abc import ABC, abstractmethod

from app.downloader.client.pan115_models import Pan115ProviderType


class Pan115Provider(ABC):
    provider_type = None

    def __init__(self, config=None, persist=False):
        self.config = dict(config or {})
        self.persist = persist
        self.err = None

    @classmethod
    def resolve_provider_type(cls, config):
        cfg = dict(config or {})
        provider = str(cfg.get("provider") or "").strip().lower()
        if provider in [Pan115ProviderType.SESSION, Pan115ProviderType.OPEN]:
            return provider

        legacy_auth_type = str(cfg.get("auth_type") or "").strip().lower()
        if legacy_auth_type == "open":
            return Pan115ProviderType.OPEN
        return Pan115ProviderType.SESSION

    @abstractmethod
    def login(self):
        raise NotImplementedError

    @abstractmethod
    def ensure_login(self):
        raise NotImplementedError

    @abstractmethod
    def normalize_task(self, task):
        raise NotImplementedError

    @abstractmethod
    def gettasklist(self, page=1, max_pages=None):
        raise NotImplementedError

    @abstractmethod
    def addtask_urls(self, content, download_dir=None):
        raise NotImplementedError

    @abstractmethod
    def deltask(self, thash, delete_file=False):
        raise NotImplementedError

    @abstractmethod
    def getiddir(self, tid):
        raise NotImplementedError

    @abstractmethod
    def getdirid(self, path):
        raise NotImplementedError

    @abstractmethod
    def ensure_dir(self, path):
        raise NotImplementedError

    @abstractmethod
    def listdir(self, cid="0", offset=0, limit=1000):
        raise NotImplementedError

    @abstractmethod
    def move(self, file_ids, to_dir_id):
        raise NotImplementedError

    @abstractmethod
    def rename(self, file_id, new_name):
        raise NotImplementedError

    @abstractmethod
    def delete(self, file_ids):
        raise NotImplementedError
