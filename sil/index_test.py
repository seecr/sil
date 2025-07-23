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
        index = Index(tmp_path, IndexProfile([]))
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


async def test_add_search_delete(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [IndexField.text(name="field_1"), IndexField.unqualified(name="ALL")]
        ),
        immediate_commit=True,
    )

    results = index.search_query("contents")
    assert results["count"] == 0

    await index.add_record(
        "id_1", dict(field_1="Contents of field 1", ALL="Contents of field 1")
    )

    results = index.search_query("contents")
    assert results["count"] == 1

    index.delete_record("id_1")
    results = index.search_query("contents")
    assert results["count"] == 0


async def test_sorting(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.text(name="field", sortable=True),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )

    await index.add_record("id_1", dict(field="Aap", ALL="value"))
    await index.add_record("id_2", dict(field="Noot", ALL="value"))
    await index.add_record("id_3", dict(field="Mies", ALL="value"))

    results = index.search_query("value")
    ids = [hit["__id__"] for hit in results["docs"]]
    assert ids == ["id_1", "id_2", "id_3"]

    results = index.search_query("value", sort="field")
    ids = [hit["__id__"] for hit in results["docs"]]
    assert ids == ["id_1", "id_3", "id_2"]

    results = index.search_query("value", sort="field", sort_reverse=True)
    ids = [hit["__id__"] for hit in results["docs"]]
    assert ids == ["id_2", "id_3", "id_1"]
