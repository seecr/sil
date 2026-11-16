## begin license ##
#
# "SIL"(Seecr Index Lib) makes developing index apps easier
#
# Copyright (C) 2025-2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "Seecr Index Lib"
#
# "Seecr Index Lib" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
#
## end license ##

import pytest
import tantivy

from .index import Index
from .indexfield import IndexField
from .indexprofile import IndexProfile


@pytest.fixture
def index(tmp_path):
    return Index(tmp_path)


async def test_create_index(tmp_path):
    assert len(list(tmp_path.glob("*"))) == 0

    Index(tmp_path, IndexProfile([]), immediate_commit=True)
    assert set([n.name for n in tmp_path.glob("*")]) == {"index"}


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

    index.add_record(
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
    index.add_record("id_1", dict(field="Aap", ALL="value"))

    with pytest.raises(RuntimeError) as e:
        index.search_query("value", sort=[dict(field="field")])

    assert str(e.value) == "Unsortable field: field"


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
    index.add_record("id_1", dict(field="Aap", ALL="value"))

    with pytest.raises(RuntimeError) as e:
        index.search_query("value", sort=[dict(field="error")])

    assert str(e.value) == "Unknown field: error"


async def test_sorting(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.text(name="field", sortable=True),
                IndexField.int(name="number", sortable=True),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )

    index.add_record("id_1", dict(field="Aap", number=1, ALL=[1, "value", ""]))
    index.add_record("id_2", dict(field="Noot", number=2, ALL=[2, "value"]))
    index.add_record("id_3", dict(field="Mies", number=3, ALL=[3, "value"]))

    results = index.search_query("value")
    ids = [hit["__id__"] for hit in results["docs"]]
    assert ids == ["id_1", "id_2", "id_3"]

    results = index.search_query("value", sort=[dict(field="field")])
    ids = [hit["__id__"] for hit in results["docs"]]
    assert ids == ["id_1", "id_3", "id_2"]

    results = index.search_query("value", sort=[dict(field="field", reverse=True)])
    ids = [hit["__id__"] for hit in results["docs"]]
    assert ids == ["id_2", "id_3", "id_1"]

    results = index.search_query("value", sort=[dict(field="number")])
    ids = [hit["__id__"] for hit in results["docs"]]
    assert ids == ["id_1", "id_2", "id_3"]

    results = index.search_query("value", sort=[dict(field="number", reverse=True)])
    ids = [hit["__id__"] for hit in results["docs"]]
    assert ids == ["id_3", "id_2", "id_1"]


async def test_multi_sort(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.int(name="A", sortable=True),
                IndexField.text(name="B", sortable=True),
                IndexField.text(name="C", sortable=True),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )

    index.add_record("id_1", dict(A=1, B="aap", C="boom", ALL=["value"]))
    index.add_record("id_2", dict(A=2, B="aap", C="roos", ALL=["value"]))
    index.add_record("id_3", dict(A=3, B="noot", C="boom", ALL=["value"]))
    index.add_record("id_4", dict(A=4, B="aap", C="boom", ALL=["value"]))
    index.add_record("id_5", dict(A=5, B="vis", C="boom", ALL=["value"]))

    results = index.search_query("value", sort=[dict(field="B")])
    ids = [hit["__id__"] for hit in results["docs"]]
    assert ids == ["id_1", "id_2", "id_4", "id_3", "id_5"]

    results = index.search_query("value", sort="B")
    ids = [hit["__id__"] for hit in results["docs"]]
    assert ids == ["id_1", "id_2", "id_4", "id_3", "id_5"]

    results = index.search_query("value", sort=[dict(field="B", reverse=True)])
    ids = [hit["__id__"] for hit in results["docs"]]
    assert ids == ["id_5", "id_3", "id_1", "id_2", "id_4"]

    results = index.search_query("value", sort=[dict(field="B"), dict(field="C")])
    ids = [hit["__id__"] for hit in results["docs"]]
    assert ids == ["id_1", "id_4", "id_2", "id_3", "id_5"]

    results = index.search_query("value", sort=["B", "C"])
    ids = [hit["__id__"] for hit in results["docs"]]
    assert ids == ["id_1", "id_4", "id_2", "id_3", "id_5"]


async def test_drilldown_no_records(tmp_path):
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
    results = index.search_all(drilldown=[dict(name="year")])
    assert results["count"] == 0


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

    index.add_record("id_1", dict(name="John", year="2025", ALL="value john"))
    index.add_record("id_2", dict(name="Jane", year="2024", ALL="value jane"))
    index.add_record("id_3", dict(name="John", year="2024", ALL="value john"))

    results = index.search_all(drilldown=[dict(name="year")])
    assert results["count"] == 3
    assert "year" in results["drilldown"]
    assert results["drilldown"]["year"] == [("2024", 2), ("2025", 1)]

    results = index.search_by_term("name", "John", drilldown=[dict(name="year")])
    assert results["count"] == 2
    assert "year" in results["drilldown"]
    assert results["drilldown"]["year"] == [("2024", 1), ("2025", 1)]

    results = index.search_query("+value +john", drilldown=[dict(name="year")])
    assert results["count"] == 2
    assert "year" in results["drilldown"]
    assert results["drilldown"]["year"] == [("2024", 1), ("2025", 1)]

    results = index.search_query("value john", drilldown=[dict(name="year")])
    assert results["count"] == 3
    assert "year" in results["drilldown"]
    assert results["drilldown"]["year"] == [("2024", 2), ("2025", 1)]

    index.delete_record("id_3")
    results = index.search_all(drilldown=[dict(name="year")])
    assert "year" in results["drilldown"]
    assert results["drilldown"]["year"] == [("2024", 1), ("2025", 1)]


async def test_drilldown_empty_paths(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="drill", drilldown=True),
            ]
        ),
        immediate_commit=True,
    )

    index.add_record("id_1", dict(drill="path1"))
    index.add_record("id_2", dict(drill=""))

    results = index.search_all(drilldown=[dict(name="drill")])
    assert results["count"] == 2
    assert results["drilldown"]["drill"] == [("path1", 1)]


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
    index.add_record("id_1", dict(keywords=["rock", "paper", "scissors"], ALL="value"))
    index.add_record("id_2", dict(keywords=["rack"], ALL="value"))
    index.add_record("id_3", dict(keywords=["paperwork", "scale"], ALL="value"))

    assert index.suggest("keywords", "") == []
    assert index.suggest("keywords", "r") == ["rock", "rack"]
    assert index.suggest("keywords", "sc") == ["scissors", "scale"]
    assert index.suggest("keywords", "paper") == ["paper", "paperwork"]
    assert index.suggest("keywords", "paperwork") == ["paperwork"]


async def test_sortfields(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="keywords"),
            ]
        ),
        immediate_commit=True,
    )
    assert index.sortfields == []
    index.shutdown()

    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="keywords", sortable=True),
            ]
        ),
        immediate_commit=True,
    )
    assert index.sortfields == ["keywords"]


async def test_drilldown_sees_new_values_after_a_commit(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="year", drilldown=True),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )
    index.add_record("id_1", dict(year="2025", ALL="value"))

    results = index.search_all(drilldown=[dict(name="year")])
    assert results["drilldown"]["year"] == [("2025", 1)]

    index.add_record("id_2", dict(year="2024", ALL="value"))
    results = index.search_all(drilldown=[dict(name="year")])
    assert results["drilldown"]["year"] == [("2024", 1), ("2025", 1)]


async def test_suggest_without_duplicates_and_cleared_by_delete_all(tmp_path):
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
    for _ in range(3):  # the same record indexed again
        index.add_record("id_1", dict(keywords=["rock"], ALL="value"))
    assert index.suggest("keywords", "ro") == ["rock"]

    index.delete_all()
    assert index.suggest("keywords", "ro") == []


async def test_commit_task_survives_an_error():
    import asyncio

    from .commit import Commit

    class Target:
        calls = 0

        def commit(self):
            Target.calls += 1
            if Target.calls == 1:
                raise RuntimeError("disk full")

    commit = Commit(timeout=0.01)
    commit.add_target(Target())
    task = commit.as_task()
    await asyncio.sleep(0.1)
    assert not task.done()
    assert Target.calls > 1
    task.cancel()


async def test_suggest_on_empty_index(tmp_path):
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
    assert index.suggest("keywords", "ro") == []


async def test_drilldown_with_several_values(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="keywords", drilldown=True),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )
    index.add_record("id_1", dict(keywords=["rock", "paper"], ALL="value"))
    index.add_record("id_2", dict(keywords=["rock"], ALL="value"))

    results = index.search_all(drilldown=[dict(name="keywords")])
    assert results["drilldown"]["keywords"] == [("rock", 2), ("paper", 1)]


async def test_sorting_with_several_values_uses_the_first(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="authors", sortable=True),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )
    index.add_record("id_1", dict(authors=["Noot", "Aap"], ALL="value"))
    index.add_record("id_2", dict(authors=["Mies"], ALL="value"))

    results = index.search_query("value", sort=[dict(field="authors")])
    assert [hit["__id__"] for hit in results["docs"]] == ["id_2", "id_1"]


async def test_invalid_query_syntax_is_searched_literally(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [IndexField.text(name="title"), IndexField.unqualified(name="ALL")]
        ),
        immediate_commit=True,
    )
    index.add_record("id_1", dict(title="rock", ALL="rock and roll"))

    for query in ['"rock', "rock)", "rock:", "(rock"]:
        assert index.search_query(query)["count"] == 1, query


async def test_search_while_committing_in_another_thread(tmp_path):
    import threading

    from .utils import ensure_current_thread_attached

    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="year", drilldown=True),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )
    index.add_record("id_0", dict(year="2000", ALL="value"))
    errors = []

    def search():
        ensure_current_thread_attached()
        try:
            for _ in range(200):
                index.search_query("value", drilldown=[dict(name="year")])
        except Exception as e:
            errors.append(e)

    thread = threading.Thread(target=search)
    thread.start()
    for nr in range(1, 50):  # every add commits and refreshes the readers
        index.add_record(f"id_{nr}", dict(year=str(2000 + nr % 5), ALL="value"))
    thread.join()

    assert errors == []
    assert index.search_query("value")["count"] == 50


def _ids(results):
    return [hit["__id__"] for hit in results["docs"]]


async def test_prefix_query(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.text(name="title"),
                IndexField.untokenized(name="name"),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )
    index.add_record("id_1", dict(title="Rock and Roll", name="John", ALL="rock"))
    index.add_record("id_2", dict(title="Rocket", name="Jane", ALL="rocket"))

    assert _ids(index.search_query("roc*")) == ["id_1", "id_2"]
    assert _ids(index.search_query("ROCK*")) == ["id_1", "id_2"]
    assert _ids(index.search_query("title:rock*")) == ["id_1", "id_2"]
    assert _ids(index.search_query("title:rocke*")) == ["id_2"]
    assert _ids(index.search_query("name:Jo*")) == ["id_1"]
    assert _ids(index.search_query('"rock*"')) == ["id_1"]  # not in a phrase


async def test_query_language(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="name"),
                IndexField.int(name="number"),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )
    index.add_record("id_1", dict(name="John", number=1, ALL="rock and roll"))
    index.add_record("id_2", dict(name="Jane", number=2, ALL="rock"))

    assert _ids(index.search_query("name:John")) == ["id_1"]
    assert _ids(index.search_query("number:2")) == ["id_2"]
    assert _ids(index.search_query("number:[1 TO 2]")) == ["id_1", "id_2"]
    assert _ids(index.search_query("rock -roll")) == ["id_2"]
    assert _ids(index.search_query('"and roll"')) == ["id_1"]
    assert _ids(index.search_query("*")) == ["id_1", "id_2"]
    # an unknown field: searched literally
    assert index.search_query("unknown:rock")["count"] == 2


async def test_int_ranges(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="name"),
                IndexField.int(name="number", sortable=True),
                IndexField.int(name="numbers"),  # more than one value
            ]
        ),
        immediate_commit=True,
    )
    for nr in range(1, 6):
        index.add_record(
            f"id_{nr}", dict(name=f"n{nr}", number=nr * 10, numbers=[nr, nr + 100])
        )

    assert _ids(index.search_query("number:[20 TO 40]")) == ["id_2", "id_3", "id_4"]
    assert _ids(index.search_query("number:{20 TO 40}")) == ["id_3"]
    assert _ids(index.search_query("number:[20 TO 40}")) == ["id_2", "id_3"]
    assert _ids(index.search_query("number:[40 TO *]")) == ["id_4", "id_5"]
    assert _ids(index.search_query("number:[* TO 10]")) == ["id_1"]
    assert _ids(index.search_query("numbers:[103 TO 104]")) == ["id_3", "id_4"]
    assert _ids(index.search_query("numbers:[2 TO 2]")) == ["id_2"]
    assert _ids(index.search_query("number:[20 TO 40] AND name:n3")) == ["id_3"]
    assert _ids(index.search_query("(number:{40 TO *]) OR (number:[40 TO 40] AND "
                                   "name:{n3 TO *])")) == ["id_4", "id_5"]


async def test_int_field_is_fast(tmp_path):
    """An int field is a fast field too, so tantivy answers a range on it from the
    field's column instead of walking the terms (16 ms against 0.6 ms for 120,000
    documents). tantivy only orders on a fast field: ordering on the field itself
    shows it is one."""
    index = Index(
        path=tmp_path,
        profile=IndexProfile([IndexField.int(name="number")]),
        immediate_commit=True,
    )
    for nr in (3, 1, 2):
        index.add_record(f"id_{nr}", dict(number=nr))
    searcher = index._engine.searcher()
    query = index.parse_query("number:[1 TO 2]")
    result = searcher.search(getattr(query, "query", query), limit=10,
                             order_by_field="number", order=tantivy.Order.Asc)
    assert [order for order, _ in result.hits] == [1, 2]


async def test_search_by_term(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="name"),
                IndexField.int(name="number"),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )
    index.add_record("id_1", dict(name="John", number=1, ALL="value"))
    index.add_record("id_2", dict(name="Jane", number=2, ALL="value"))

    assert _ids(index.search_by_term("number", 2)) == ["id_2"]
    assert _ids(index.search_by_term("number", "2")) == ["id_2"]
    assert _ids(index.search_by_term("name", "Jane")) == ["id_2"]
    assert index.search_by_term("unknown", "Jane")["count"] == 0
    assert _ids(index.search_by_id("id_1")) == ["id_1"]

    query = index.all_of(index.parse_query("value"), index.term_query("name", "John"))
    assert _ids(index.search(query)) == ["id_1"]


async def test_stored_fields(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="__id__"),  # as swindl does
                IndexField.untokenized(name="tags", stored=True),
                IndexField.text(name="secret"),
            ]
        ),
        immediate_commit=True,
    )
    index.add_record("Thing:1", {"__id__": "1", "tags": ["a", "b"], "secret": "x"})

    [hit] = index.search_all()["docs"]
    assert hit == {"__id__": "Thing:1", "tags": "a"}
    assert hit.get_values("tags") == ["a", "b"]
    assert _ids(index.search_by_term("__id__", "1")) == ["Thing:1"]

    index.add_record("Thing:1", {"__id__": "1", "tags": ["c"]})
    assert index.search_all()["count"] == 1
    index.delete_record("Thing:1")
    assert index.search_all()["count"] == 0


async def test_paging_sorted_with_equal_values(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="group", sortable=True),
                IndexField.int(name="number", sortable=True),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )
    for nr in range(20):
        index.add_record(
            f"id_{nr:02}", dict(group="ab"[nr % 2], number=nr % 3, ALL="value")
        )
    index.add_record("id_none", dict(ALL="value"))  # sorts first, as in Lucene

    sort = [dict(field="group"), dict(field="number", reverse=True)]
    everything = _ids(index.search_query("value", sort=sort, limit=100))
    paged = []
    for page in range(1, 6):
        paged += _ids(index.search_query("value", sort=sort, page=page, limit=5))
    assert paged == everything
    assert everything[:5] == ["id_none", "id_02", "id_08", "id_14", "id_04"]

    paged = []
    for page in range(1, 4):
        paged += _ids(index.search_all(page=page, limit=8))
    assert paged == sorted(paged[:-1]) + ["id_none"]


async def test_paging_with_equal_scores_oldest_first(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile([IndexField.unqualified(name="ALL")]),
        immediate_commit=True,
    )
    for nr in range(25):
        index.add_record(f"id_{nr:02}", dict(ALL="value"))
    index.add_record("id_05", dict(ALL="value"))  # updated: now the newest

    paged = []
    for page in range(1, 5):
        paged += _ids(index.search_query("value", page=page, limit=7))
    expected = [f"id_{nr:02}" for nr in range(25) if nr != 5] + ["id_05"]
    assert paged == expected


async def test_reopen_and_changed_profile(tmp_path):
    profile = IndexProfile(
        [IndexField.text(name="title"), IndexField.unqualified(name="ALL")]
    )
    index = Index(tmp_path, profile, immediate_commit=True)
    index.add_record("id_1", dict(title="rock", ALL="rock"))
    index.shutdown()

    index = Index(tmp_path, profile, immediate_commit=True)
    assert not index.needs_reindex
    assert index.search_query("rock")["count"] == 1
    index.shutdown()

    profile = IndexProfile(
        [
            IndexField.text(name="title", sortable=True),
            IndexField.unqualified(name="ALL"),
        ]
    )
    index = Index(tmp_path, profile, immediate_commit=True)
    assert index.needs_reindex
    assert index.search_query("rock")["count"] == 0


async def test_shutdown_commits(tmp_path):
    profile = IndexProfile([IndexField.unqualified(name="ALL")])
    index = Index(tmp_path, profile, commit_timeout=0)
    index.add_record("id_1", dict(ALL="rock"))
    assert index.search_query("rock")["count"] == 0  # not committed yet
    index.shutdown()

    index = Index(tmp_path, profile, commit_timeout=0)
    assert index.search_query("rock")["count"] == 1


async def test_suggest_infix(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile([IndexField.untokenized(name="place", suggest=True)]),
        immediate_commit=True,
    )
    index.add_record("id_1", dict(place="New York"))
    index.add_record("id_2", dict(place="York"))
    index.add_record("id_3", dict(place="Newcastle"))

    assert index.suggest("place", "yo") == ["New York", "York"]
    assert index.suggest("place", "new") == ["New York", "Newcastle"]
    assert index.suggest("place", "new yo") == ["New York", "York"]


async def test_listings_in_insertion_order(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="parent"),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )
    for nr in range(30):
        index.add_record(f"id_{nr:02}", dict(parent="p1", ALL="value"))
    expected = [f"id_{nr:02}" for nr in range(30)]

    paged = []
    for page in range(1, 5):
        paged += _ids(index.search_by_term("parent", "p1", page=page, limit=8))
    assert paged == expected

    query = index.all_of(index.parse_query("*"), index.term_query("parent", "p1"))
    assert _ids(index.search(query, limit=100)) == expected


async def test_sorting_matches_sorting_everything(tmp_path):
    import random

    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="a", sortable=True),
                IndexField.int(name="b", sortable=True),
                IndexField.untokenized(name="c", sortable=True),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=False,
        commit_timeout=0,
    )
    rnd = random.Random(42)
    records = {}
    for nr in range(300):
        data = dict(a=rnd.choice("xyz"), b=rnd.randint(0, 3), c=rnd.choice("pq"))
        if nr % 17 == 0:
            del data["a"]
        records[f"id_{nr:03}"] = data
        index.add_record(f"id_{nr:03}", dict(data, ALL="value"))
    index.commit(immediate_commit=True)

    order = list(records)  # insertion order
    for sort in (
        [dict(field="a")],
        [dict(field="a", reverse=True), dict(field="b")],
        [dict(field="b", reverse=True), dict(field="c"), dict(field="a")],
    ):
        expected = sorted(order)  # ids in insertion order
        for key in reversed(sort):
            missing = 0 if key["field"] == "b" else ""
            expected.sort(
                key=lambda i: records[i].get(key["field"], missing),
                reverse=key.get("reverse", False),
            )
        for limit in (7, 50):
            paged = []
            for page in range(1, 300 // limit + 2):
                paged += _ids(index.search_all(sort=sort, page=page, limit=limit))
            assert paged == expected, (sort, limit)


@pytest.mark.parametrize("in_python", [1000, 3])
async def test_sorting_text_with_the_same_first_bytes(tmp_path, monkeypatch, in_python):
    """Text is sorted on its first 8 bytes (as an int: fast) and then on the whole
    value. Values that only differ after 8 bytes, across page boundaries, in both
    directions and with a second sort field, still come out right; also when a group
    with the same prefix is too large to sort in Python (in_python=3)."""
    import random

    from . import index as index_module

    for name in "PREFIX_GROUP", "PREFIX_GROUP_WITH_NEXT_KEYS", "PREFIX_GROUP_VALUES":
        monkeypatch.setattr(index_module, name, in_python)
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="name", sortable=True),
                IndexField.int(name="year", sortable=True),
                IndexField.text(name="title", sortable=True),
            ]
        ),
        immediate_commit=False,
        commit_timeout=0,
    )
    names = ["the beatles", "the beat happening", "the beach boys", "the beat",
             "the beatles anthology", "théo", "the", "zz", "The Beatles", "ëa",
             "the beatlez"]  # fmt: skip
    rnd = random.Random(7)
    records = {}
    for nr in range(400):
        data = dict(name=rnd.choice(names), year=rnd.randint(0, 4),
                    title=rnd.choice(names))  # fmt: skip
        if nr % 13 == 0:
            del data["name"]
        records[f"id_{nr:03}"] = data
        index.add_record(f"id_{nr:03}", data)
    index.commit(immediate_commit=True)

    for sort in (
        [dict(field="name")],
        [dict(field="name", reverse=True)],
        [dict(field="name"), dict(field="year", reverse=True)],
        [dict(field="year"), dict(field="name", reverse=True), dict(field="title")],
    ):
        expected = list(records)
        for key in reversed(sort):
            missing = 0 if key["field"] == "year" else ""
            expected.sort(
                key=lambda i: records[i].get(key["field"], missing),
                reverse=key.get("reverse", False),
            )
        for limit in (5, 33, 400):
            paged = []
            for page in range(1, 400 // limit + 2):
                paged += _ids(index.search_all(sort=sort, page=page, limit=limit))
            assert paged == expected, (sort, limit)


def test_sort_prefix_sorts_as_the_text():
    from .indexfield import sort_hash, sort_prefix

    texts = ["", "a", "ab", "abcdefgh", "abcdefghz", "b", "é", "z" * 9, "\u20ac"]
    assert sorted(texts, key=sort_prefix) == sorted(texts)
    assert sort_prefix("abcdefgh") == sort_prefix("abcdefghz")
    assert sort_hash("abcdefgh") != sort_hash("abcdefghz")
    assert sort_hash("é") == sort_hash("é")


async def test_large_limit_and_pages_past_the_end(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="name", sortable=True),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )
    assert index.search_all(limit=10**12)["count"] == 0
    for nr in range(3):
        index.add_record(f"id_{nr}", dict(name=f"n{nr}", ALL="value"))

    for search in (
        lambda **kw: index.search_all(**kw),
        lambda **kw: index.search_query("value", **kw),
        lambda **kw: index.search_query("value", sort="name", **kw),
    ):
        assert _ids(search(limit=10**12)) == ["id_0", "id_1", "id_2"]
        result = search(page=5, limit=2)
        assert (result["count"], result["docs"]) == (3, [])
        assert search(limit=0)["docs"] == []


async def test_writer_opened_on_first_change(tmp_path):
    index = Index(
        path=tmp_path,
        profile=IndexProfile(
            [
                IndexField.untokenized(name="k", suggest=True),
                IndexField.unqualified(name="ALL"),
            ]
        ),
        immediate_commit=True,
    )
    assert index._engine._writer is None
    assert index.search_query("value")["count"] == 0
    assert index._engine._writer is None
    index.add_record("id_1", dict(k="a", ALL="value"))
    assert index._engine._writer is not None
    index.shutdown()
    with pytest.raises(RuntimeError):
        index.add_record("id_2", dict(ALL="value"))


class _Commits:
    """A commit target that counts the commits of an index."""

    def __init__(self):
        self.count = 0

    def commit(self):
        self.count += 1


def _counted_index(tmp_path, immediate_commit=True):
    index = Index(
        path=tmp_path,
        profile=IndexProfile([IndexField.unqualified(name="ALL")]),
        immediate_commit=immediate_commit,
        commit_timeout=0,
    )
    commits = _Commits()
    index._commit.add_target(commits)
    return index, commits


async def test_deferred_commit_commits_once_at_the_end(tmp_path):
    index, commits = _counted_index(tmp_path)
    with index.deferred_commit():
        for nr in range(5):
            index.add_record(f"id_{nr}", dict(ALL="value"))
        assert commits.count == 0
        assert index.search_query("value")["count"] == 0  # not yet
    assert commits.count == 1
    assert index.search_query("value")["count"] == 5

    index.add_record("id_5", dict(ALL="value"))  # after the block: as before
    assert commits.count == 2


async def test_deferred_commit_nested_commits_at_the_outermost(tmp_path):
    index, commits = _counted_index(tmp_path)
    with index.deferred_commit():
        with index.deferred_commit():
            index.add_record("id_1", dict(ALL="value"))
        assert commits.count == 0
        index.add_record("id_2", dict(ALL="value"))
    assert commits.count == 1


async def test_deferred_commit_commits_when_it_raises(tmp_path):
    index, commits = _counted_index(tmp_path)
    with pytest.raises(ValueError):
        with index.deferred_commit():
            index.add_record("id_1", dict(ALL="value"))
            raise ValueError("oops")
    assert commits.count == 1
    assert index.search_query("value")["count"] == 1


async def test_deferred_commit_without_changes_does_not_commit(tmp_path):
    index, commits = _counted_index(tmp_path)
    with index.deferred_commit():
        pass
    assert commits.count == 0


async def test_deferred_commit_does_not_put_off_an_explicit_commit(tmp_path):
    index, commits = _counted_index(tmp_path)
    index.add_record("id_1", dict(ALL="value"))
    assert commits.count == 1
    with index.deferred_commit():
        index.delete_record("id_1", immediate_commit=True)
        assert commits.count == 2
        assert index.search_query("value")["count"] == 0
        index.delete_record("id_2")  # an implicit one waits
        assert commits.count == 2
    assert commits.count == 3


async def test_deferred_commit_leaves_auto_commit_alone(tmp_path):
    index, commits = _counted_index(tmp_path, immediate_commit=False)
    with index.deferred_commit():
        index.add_record("id_1", dict(ALL="value"))
    assert commits.count == 0  # the auto-commit does it
