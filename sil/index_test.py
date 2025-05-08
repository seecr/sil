import pytest

from .index import Index, IndexFields


class Dict(dict):
    def __getattribute__(self, key):
        if key in self:
            return self[key]
        return dict.__getattribute__(self, key)

    def __setattr__(self, key, value):
        self[key] = value


@pytest.fixture
def index(tmp_path):
    return Index(tmp_path)


async def test_create_index(tmp_path):
    assert len(list(tmp_path.glob("*"))) == 0
    Index(tmp_path, IndexFields())
    assert len(list(tmp_path.glob("*"))) == 2
