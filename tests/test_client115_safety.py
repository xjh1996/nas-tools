import tempfile

from app.downloader.client.client115 import Client115
from app.utils.types import MediaType


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


def test_extract_title_year_candidates_from_mixed_title():
    candidates = Client115._extract_title_year_candidates(
        "肥兔子邦尼 Big Buck Bunny(2008 荷兰)[WEB][4000x2250]"
    )

    assert candidates == [("Big Buck Bunny", "2008")]


def test_wait_for_path_returns_false_for_missing_path():
    assert Client115._wait_for_path("/tmp/nas-tools-missing-path-for-test", attempts=1, interval=0) is False


class FakeMovieMedia:
    type = MediaType.MOVIE
    category = "动画电影"


class FakeFileTransfer:
    _movie_category_flag = False

    @staticmethod
    def _FileTransfer__get_best_target_path(mtype, in_path=None, size=0):
        return "/tmp/nas-tools-test-library/movies"

    @staticmethod
    def get_moive_dest_path(media):
        return "大雄兔 (2008)", "大雄兔 (2008)"


def test_build_remote_movie_target_respects_disabled_category():
    client = object.__new__(Client115)
    client._local_remote_roots = lambda: [
        ("/tmp/nas-tools-test-downloads", "/影音库/downloads"),
        ("/tmp/nas-tools-test-library/movies", "/影音库/library/movies"),
    ]

    with tempfile.NamedTemporaryFile(dir="/tmp", suffix=".mp4") as source:
        target = client._build_remote_target_path(
            FakeFileTransfer(),
            FakeMovieMedia(),
            "/tmp/nas-tools-test-downloads/movie",
            source.name,
        )

    assert target == "/影音库/library/movies/大雄兔 (2008)/大雄兔 (2008).mp4"


def test_build_remote_movie_target_respects_enabled_category():
    class CategorizedFileTransfer(FakeFileTransfer):
        _movie_category_flag = True

    client = object.__new__(Client115)
    client._local_remote_roots = lambda: [
        ("/tmp/nas-tools-test-downloads", "/影音库/downloads"),
        ("/tmp/nas-tools-test-library/movies", "/影音库/library/movies"),
    ]

    with tempfile.NamedTemporaryFile(dir="/tmp", suffix=".mp4") as source:
        target = client._build_remote_target_path(
            CategorizedFileTransfer(),
            FakeMovieMedia(),
            "/tmp/nas-tools-test-downloads/movie",
            source.name,
        )

    assert target == "/影音库/library/movies/动画电影/大雄兔 (2008)/大雄兔 (2008).mp4"
