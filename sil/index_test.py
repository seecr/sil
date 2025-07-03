import pytest

from .index import Index, IndexProfile, IndexField


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
    try:
        index = Index(tmp_path, IndexProfile())
        assert len(list(tmp_path.glob("*"))) == 2
    finally:
        index.shutdown()


async def test_indexfields_unqualified(tmp_path):
    ifs = IndexProfile([IndexField.text(name="field_1")])
    assert ifs.unqualified is None

    ifs = IndexProfile(
        [IndexField.text(name="field_1"), IndexField.unqualified(name="ALL")]
    )
    assert ifs.unqualified.name == "ALL"

    with pytest.raises(RuntimeError) as e:
        IndexProfile(
            [
                IndexField.text(name="field_1"),
                IndexField.unqualified(name="ALL"),
                IndexField.unqualified(name="AGAIN"),
            ]
        )
    assert (
        repr(e) == "<ExceptionInfo RuntimeError('Multiple unqualified fields') tblen=2>"
    )
