import xml.dom.minidom

import log
from app.helper import IndexerConf
from app.indexer.client._base import _IIndexClient
from app.utils import RequestUtils, ExceptionUtils
from app.utils.types import IndexerType
from config import Config


class Jackett(_IIndexClient):
    schema = "jackett"
    index_type = IndexerType.JACKETT.value
    _client_config = {}

    def __init__(self, config=None):
        super().__init__()
        self._client_config = config or Config().get_config("jackett") or {}
        self.init_config()

    def init_config(self):
        self.host = (self._client_config.get("host") or "").strip()
        if self.host and not self.host.startswith("http"):
            self.host = "http://%s" % self.host
        self.host = self.host.rstrip("/")
        self.api_key = (self._client_config.get("api_key") or "").strip()

    @classmethod
    def match(cls, ctype):
        return True if ctype in [cls.schema, cls.index_type] else False

    def get_status(self):
        if not self.host or not self.api_key:
            return False
        req_url = "%s/api/v2.0/indexers/all/results/torznab/api" % self.host
        try:
            res = RequestUtils(timeout=10).get_res(req_url, params={
                "apikey": self.api_key,
                "t": "caps"
            })
            return bool(res and res.status_code == 200 and "<caps" in res.text)
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error("【%s】连接Jackett出错：%s" % (self.index_type, str(e)))
            return False

    def search(self, order_seq, indexer, key_word, filter_args, match_media, in_from):
        return super().search(order_seq, indexer, key_word, filter_args, match_media, in_from)

    def get_indexers(self):
        if not self.host or not self.api_key:
            return []
        configured = self._client_config.get("indexers") or []
        if isinstance(configured, str):
            configured = [item.strip() for item in configured.splitlines() if item.strip()]
        configured = [str(item).strip() for item in configured if str(item).strip()]
        req_url = "%s/api/v2.0/indexers/all/results/torznab/api" % self.host
        try:
            res = RequestUtils(timeout=10).get_res(req_url, params={
                "apikey": self.api_key,
                "t": "indexers"
            })
            if not res or res.status_code != 200:
                return []
            dom_tree = xml.dom.minidom.parseString(res.text)
            rows = dom_tree.getElementsByTagName("indexer")
        except Exception as e:
            ExceptionUtils.exception_traceback(e)
            log.error("【%s】获取Jackett索引器出错：%s" % (self.index_type, str(e)))
            return []

        indexers = []
        for row in rows:
            indexer_id = str(row.getAttribute("id") or "").strip()
            if not indexer_id or indexer_id.lower() == "all":
                continue
            if row.getAttribute("configured") != "true":
                continue
            if configured and indexer_id not in configured:
                continue
            title_nodes = row.getElementsByTagName("title")
            title = indexer_id
            if title_nodes and title_nodes[0].firstChild:
                title = title_nodes[0].firstChild.nodeValue or indexer_id
            domain = "%s/api/v2.0/indexers/%s/results/torznab/api" % (self.host, indexer_id)
            indexers.append(IndexerConf(datas={
                "id": indexer_id,
                "name": title,
                "domain": domain,
                "search": {},
                "browse": {},
                "torrents": {},
                "category": {}
            }, public=False, builtin=False, pri=0))
        return indexers
