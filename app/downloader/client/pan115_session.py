from app.downloader.client._py115 import Pan115AuthType, Py115
from app.downloader.client.pan115_base import Pan115Provider
from app.downloader.client.pan115_models import Pan115ProviderType


class Pan115SessionProvider(Pan115Provider):
    provider_type = Pan115ProviderType.SESSION

    def __init__(self, config=None, persist=False):
        super().__init__(config=config, persist=persist)
        client_config = dict(self.config)
        provider = self.resolve_provider_type(client_config)
        if provider == Pan115ProviderType.OPEN:
            auth_type = Pan115AuthType.OPEN
        else:
            auth_type = str(client_config.get("auth_type") or "").strip().lower()
            if auth_type not in [Pan115AuthType.COOKIE, Pan115AuthType.QRCODE]:
                auth_type = Pan115AuthType.COOKIE
        client_config["auth_type"] = auth_type
        client_config["_persist"] = self.persist
        self.client = Py115(client_config)

    def login(self):
        ret = self.client.login()
        self.err = self.client.err
        return ret

    def ensure_login(self):
        ret = self.client.ensure_login()
        self.err = self.client.err
        return ret

    def normalize_task(self, task):
        return self.client.normalize_task(task)

    def gettasklist(self, page=1, max_pages=None):
        ret, tasks = self.client.gettasklist(page=page, max_pages=max_pages)
        self.err = self.client.err
        return ret, tasks

    def addtask_urls(self, content, download_dir=None):
        ret, info_hash = self.client.addtask(tdir=download_dir, content=content)
        self.err = self.client.err
        return ret, info_hash

    def deltask(self, thash, delete_file=False):
        ret = self.client.deltask(thash=thash)
        self.err = self.client.err
        return ret

    def getiddir(self, tid):
        ret, path = self.client.getiddir(tid)
        self.err = self.client.err
        return ret, path

    def getdirid(self, path):
        ret, dir_id = self.client.getdirid(path)
        self.err = self.client.err
        return ret, dir_id

    def ensure_dir(self, path):
        ret, dir_id = self.client.ensure_dir(path)
        self.err = self.client.err
        return ret, dir_id

    def listdir(self, cid="0", offset=0, limit=1000):
        ret, items = self.client.listdir(cid=cid, offset=offset, limit=limit)
        self.err = self.client.err
        return ret, items

    def move(self, file_ids, to_dir_id):
        ret = self.client.move(file_ids=file_ids, to_dir_id=to_dir_id)
        self.err = self.client.err
        return ret

    def rename(self, file_id, new_name):
        ret = self.client.rename(file_id=file_id, new_name=new_name)
        self.err = self.client.err
        return ret

    def delete(self, file_ids):
        ret = self.client.delete(file_ids=file_ids)
        self.err = self.client.err
        return ret

    def get_download_url(self, pick_code, user_agent=None):
        ret, link = self.client.get_download_url(pick_code=pick_code, user_agent=user_agent)
        self.err = self.client.err
        return ret, link
