from app.downloader.client.client115 import Client115


class FakeClient115(Client115):
    def __init__(self):
        self._transfer_roots = ["/影音库/downloads"]

    def get_completed_torrents(self, **kwargs):
        return [
            {
                "path": "/根目录/影音库/downloads/movies",
                "name": "movie.mkv",
                "info_hash": "keep",
            },
            {
                "path": "/根目录/云下载/old",
                "name": "old.mkv",
                "info_hash": "skip",
            },
        ]

    @staticmethod
    def get_replace_path(path):
        return path.replace("/根目录/影音库/downloads", "/mnt/115/downloads")


def test_set_torrents_status_does_not_delete_task():
    calls = []

    class DownClient:
        def deltask(self, thash):
            calls.append(thash)
            return True

    client = object.__new__(Client115)
    client.downclient = DownClient()

    assert client.set_torrents_status(ids="hash") is False
    assert calls == []


def test_transfer_tasks_are_limited_to_configured_download_root():
    client = FakeClient115()

    assert client.get_transfer_task() == [
        {
            "path": "/mnt/115/downloads/movies/movie.mkv",
            "id": "keep",
        }
    ]


def test_normalize_remote_path_strips_115_root_label():
    assert Client115._normalize_remote_path("/根目录/影音库/downloads") == "/影音库/downloads"
