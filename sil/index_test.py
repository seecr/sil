## begin license ##
#
# "SIL"(Seecr Index Lib) makes developing index apps easier
#
# Copyright (C) 2025 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "Seecr Index Lib"
#
# "Seecr Index Lib" is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# "Seecr Index Lib" is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with "Seecr Index Lib"; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
## end license ##

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
        index.search_query("value", sort=[dict(field="field")])

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
        index.search_query("value", sort=[dict(field="error")])

    assert repr(e) == "<ExceptionInfo RuntimeError('Unknown field: error') tblen=3>"


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

    await index.add_record("id_1", dict(field="Aap", number=1, ALL=[1, "value", ""]))
    await index.add_record("id_2", dict(field="Noot", number=2, ALL=[2, "value"]))
    await index.add_record("id_3", dict(field="Mies", number=3, ALL=[3, "value"]))

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

    await index.add_record("id_1", dict(A=1, B="aap", C="boom", ALL=["value"]))
    await index.add_record("id_2", dict(A=2, B="aap", C="roos", ALL=["value"]))
    await index.add_record("id_3", dict(A=3, B="noot", C="boom", ALL=["value"]))
    await index.add_record("id_4", dict(A=4, B="aap", C="boom", ALL=["value"]))
    await index.add_record("id_5", dict(A=5, B="vis", C="boom", ALL=["value"]))

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
