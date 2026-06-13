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
            "remote_path": "/影音库/downloads/movies/movie.mkv",
            "id": "keep",
            "name": "movie.mkv",
            "preserve_task": True,
        }
    ]


def test_normalize_remote_path_strips_115_root_label():
    assert Client115._normalize_remote_path("/根目录/影音库/downloads") == "/影音库/downloads"


def test_local_to_remote_path_uses_download_and_library_roots():
    client = object.__new__(Client115)
    client._client_config = {
        "remote_movie_path": "/影音库/library/movies",
        "remote_tv_path": "/影音库/library/tv",
        "remote_anime_path": "/影音库/library/anime",
    }

    assert client._normalize_remote_path("/根目录/影音库/downloads/movies") == "/影音库/downloads/movies"

    client._local_remote_roots = lambda: [
        ("/mnt/115/downloads", "/影音库/downloads"),
        ("/mnt/115/library/movies", "/影音库/library/movies"),
    ]

    assert client._local_to_remote_path("/mnt/115/downloads/movies/a.mkv") == "/影音库/downloads/movies/a.mkv"
    assert client._local_to_remote_path("/mnt/115/library/movies/大雄兔/a.mkv") == "/影音库/library/movies/大雄兔/a.mkv"


def test_remote_to_local_path_uses_library_roots():
    client = object.__new__(Client115)
    client._local_remote_roots = lambda: [
        ("/mnt/115/library/movies", "/影音库/library/movies"),
    ]

    assert client._remote_to_local_path("/影音库/library/movies/大雄兔/a.mkv") == "/mnt/115/library/movies/大雄兔/a.mkv"


def test_history_tokens_match_task_name_and_title():
    task_tokens = [Client115._history_match_key("肥兔子邦尼 Big Buck Bunny(2008)")]
    history_tokens = [Client115._history_match_key("肥兔子邦尼 Big Buck Bunny 2008 WEB 2160p")]

    assert Client115._history_tokens_match(task_tokens, history_tokens) is True
