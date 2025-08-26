import pytest

from .index import Index
from .indexprofile import IndexProfile
from .indexfield import IndexField


@pytest.fixture
def index(tmp_path):
    return Index(tmp_path)


async def test_create_index(tmp_path):
    assert len(list(tmp_path.glob("*"))) == 0

    index = Index(tmp_path, IndexProfile([]), immediate_commit=True)
    assert set([n.name for n in tmp_path.glob("*")]) == {"index", "taxo"}


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


async def test_sorting_non_sortable_field(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.text(name="field"),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )
    await index.add_record("id_1", dict(field="Aap", ALL="value"))

    with pytest.raises(RuntimeError) as e:
        index.search_query("value", sort="field")

    assert repr(e) == "<ExceptionInfo RuntimeError('Unsortable field: field') tblen=3>"


async def test_sorting_non_existing_field(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.text(name="field"),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )
    await index.add_record("id_1", dict(field="Aap", ALL="value"))

    with pytest.raises(RuntimeError) as e:
        index.search_query("value", sort="error")

    assert repr(e) == "<ExceptionInfo RuntimeError('Unknown field: error') tblen=3>"


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


async def test_drilldown(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="name"),
                IndexField.untokenized(name="year", drilldown=True),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )

    await index.add_record("id_1", dict(name="John", year="2025", ALL="value john"))
    await index.add_record("id_2", dict(name="Jane", year="2025", ALL="value jane"))
    await index.add_record("id_3", dict(name="John", year="2024", ALL="value john"))

    results = index.search_all(drilldown=[dict(name="year")])
    assert results["count"] == 3
    assert "year" in results["drilldown"]
    assert results["drilldown"]["year"] == [("2025", 2), ("2024", 1)]

    results = index.search_by_term("name", "John", drilldown=[dict(name="year")])
    assert results["count"] == 2
    assert "year" in results["drilldown"]
    assert results["drilldown"]["year"] == [("2025", 1), ("2024", 1)]

    results = index.search_query("+value +john", drilldown=[dict(name="year")])
    assert results["count"] == 2
    assert "year" in results["drilldown"]
    assert results["drilldown"]["year"] == [("2025", 1), ("2024", 1)]

    results = index.search_query("value john", drilldown=[dict(name="year")])
    assert results["count"] == 3
    assert "year" in results["drilldown"]
    assert results["drilldown"]["year"] == [("2025", 2), ("2024", 1)]

    index.delete_record("id_3")
    results = index.search_all(drilldown=[dict(name="year")])
    assert "year" in results["drilldown"]
    assert results["drilldown"]["year"] == [("2025", 2)]


async def test_suggest(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="keywords", suggest=True),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )
    await index.add_record(
        "id_1", dict(keywords=["rock", "paper", "scissors"], ALL="value")
    )
    await index.add_record("id_2", dict(keywords=["rack"], ALL="value"))
    await index.add_record("id_3", dict(keywords=["paperwork", "scale"], ALL="value"))

    assert index.suggest("keywords", "") == []
    assert index.suggest("keywords", "r") == ["rock", "rack"]
    assert index.suggest("keywords", "sc") == ["scissors", "scale"]
    assert index.suggest("keywords", "paper") == ["paper", "paperwork"]
    assert index.suggest("keywords", "paperwork") == ["paperwork"]
