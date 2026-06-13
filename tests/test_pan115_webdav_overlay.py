import os
import tempfile

from web import pan115_webdav


class FakeConfig:
    def __init__(self, config_dir):
        self._config_dir = config_dir

    def get_config_path(self):
        return self._config_dir


def test_overlay_path_stays_under_config_dir(monkeypatch):
    with tempfile.TemporaryDirectory() as config_dir:
        monkeypatch.setattr(pan115_webdav, "Config", lambda: FakeConfig(config_dir))

        overlay_path = pan115_webdav._overlay_path("/影音库/library/movie.nfo")
        assert overlay_path == os.path.join(
            config_dir,
            pan115_webdav.OVERLAY_DIR,
            "影音库",
            "library",
            "movie.nfo",
        )

        escaped_path = pan115_webdav._overlay_path("/影音库/../../outside.nfo")
        assert escaped_path == os.path.join(config_dir, pan115_webdav.OVERLAY_DIR, "outside.nfo")


def test_overlay_item_and_children(monkeypatch):
    with tempfile.TemporaryDirectory() as config_dir:
        monkeypatch.setattr(pan115_webdav, "Config", lambda: FakeConfig(config_dir))

        overlay_path = pan115_webdav._overlay_path("/影音库/library/movie.nfo")
        os.makedirs(os.path.dirname(overlay_path), exist_ok=True)
        with open(overlay_path, "wb") as target:
            target.write(b"<movie />")

        item = pan115_webdav._overlay_item("/影音库/library/movie.nfo")
        assert item["name"] == "movie.nfo"
        assert item["is_file"] is True
        assert item["size"] == 9

        children = pan115_webdav._overlay_children("/影音库/library")
        assert [child["name"] for child in children] == ["movie.nfo"]
