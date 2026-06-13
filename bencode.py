def bdecode(data):
    if isinstance(data, str):
        data = data.encode()
    parser = _Parser(data)
    value = parser.parse()
    if parser.pos != len(parser.data):
        raise ValueError("trailing data after bencode value")
    return value


class _Parser:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def parse(self):
        if self.pos >= len(self.data):
            raise ValueError("unexpected end of bencode data")
        ch = self.data[self.pos:self.pos + 1]
        if ch == b"i":
            return self._int()
        if ch == b"l":
            return self._list()
        if ch == b"d":
            return self._dict()
        if b"0" <= ch <= b"9":
            return self._bytes()
        raise ValueError("invalid bencode token")

    def _int(self):
        self.pos += 1
        end = self.data.index(b"e", self.pos)
        raw = self.data[self.pos:end]
        self.pos = end + 1
        return int(raw)

    def _list(self):
        self.pos += 1
        values = []
        while self.data[self.pos:self.pos + 1] != b"e":
            values.append(self.parse())
        self.pos += 1
        return values

    def _dict(self):
        self.pos += 1
        values = {}
        while self.data[self.pos:self.pos + 1] != b"e":
            key = self._bytes()
            try:
                key = key.decode()
            except UnicodeDecodeError:
                pass
            values[key] = self.parse()
        self.pos += 1
        return values

    def _bytes(self):
        colon = self.data.index(b":", self.pos)
        length = int(self.data[self.pos:colon])
        start = colon + 1
        end = start + length
        self.pos = end
        return self.data[start:end]
