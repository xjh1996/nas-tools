import hashlib

from app.utils.torrent import Torrent


def test_content_to_magnet_converts_torrent_bytes():
    info = b"d4:name4:test12:piece lengthi16384e6:pieces20:00000000000000000000e"
    content = b"d8:announce14:http://tracker4:info" + info + b"e"

    magnet = Torrent.content_to_magnet(content)

    assert f"btih:{hashlib.sha1(info).hexdigest()}" in magnet
    assert "dn=test" in magnet
