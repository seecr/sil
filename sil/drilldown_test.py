## begin license ##
#
# "SIL"(Seecr Indexing Lib) provides a search index on tantivy
#
# Copyright (C) 2025-2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "sil"
#
# "sil" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
#
## end license ##

import pytest

from .index import Index
from .indexfield import IndexField
from .indexprofile import IndexProfile

BACHELOR = "info:eu-repo/semantics/bachelorThesis"
MASTER = "info:eu-repo/semantics/masterThesis"


@pytest.fixture
def index(tmp_path):
    index = Index(
        tmp_path,
        IndexProfile(
            [
                IndexField.unqualified("ALL"),
                IndexField.untokenized("type", drilldown=True, hierarchical=True),
            ]
        ),
        immediate_commit=True,
    )
    # a path as a tuple, as a string with ">", and several paths in a list
    index.add_record("1", {"ALL": "fiets", "type": ("hbo:product", BACHELOR)})
    index.add_record("2", {"ALL": "fiets", "type": f"hbo:product>{BACHELOR}"})
    index.add_record("3", {"ALL": "fiets", "type": ("hbo:product", MASTER)})
    index.add_record("4", {"ALL": "auto", "type": "hbo:datasets"})
    index.add_record(
        "5",
        {"ALL": "auto", "type": [("hbo:product", BACHELOR), ("hbo:product", MASTER)]},
    )
    return index


def test_hierarchical_drilldown_is_a_tree(index):
    result = index.search_query("fiets", drilldown=[{"name": "type"}])
    assert result["count"] == 3
    assert result["drilldown"] == {
        "type": [
            ("hbo:product", 3, [(BACHELOR, 2, []), (MASTER, 1, [])]),
        ]
    }


def test_a_document_counts_once_for_a_level_its_paths_share(index):
    result = index.search_all(drilldown=[{"name": "type"}])
    assert result["drilldown"]["type"] == [
        ("hbo:product", 4, [(BACHELOR, 3, []), (MASTER, 2, [])]),
        ("hbo:datasets", 1, []),
    ]


def test_path_and_depth(index):
    result = index.search_all(drilldown=[{"name": "type", "path": ["hbo:product"]}])
    assert result["drilldown"]["type"] == [(BACHELOR, 3, []), (MASTER, 2, [])]

    result = index.search_all(drilldown=[{"name": "type", "path": "hbo:product"}])
    assert result["drilldown"]["type"] == [(BACHELOR, 3, []), (MASTER, 2, [])]

    result = index.search_all(drilldown=[{"name": "type", "depth": 1}])
    assert result["drilldown"]["type"] == [
        ("hbo:product", 4, []),
        ("hbo:datasets", 1, []),
    ]

    result = index.search_all(drilldown=[{"name": "type", "path": ["hbo:unknown"]}])
    assert result["drilldown"] == {}


def test_count_is_per_level(index):
    result = index.search_all(drilldown=[{"name": "type", "count": 1}])
    assert result["drilldown"]["type"] == [("hbo:product", 4, [(BACHELOR, 3, [])])]

    result = index.search_all(drilldown=[{"name": "type", "count": 0}])
    assert len(result["drilldown"]["type"][0][2]) == 2


def test_term_query_on_a_level_finds_the_levels_below(index):
    assert index.search_by_term("type", "hbo:product")["count"] == 4
    assert index.search_by_term("type", f"hbo:product>{MASTER}")["count"] == 2
    assert index.search_by_term("type", ("hbo:product", MASTER))["count"] == 2
    assert index.search_by_term("type", MASTER)["count"] == 0
    query = Index.all_of(
        index.parse_query("fiets"), index.term_query("type", f"hbo:product>{BACHELOR}")
    )
    assert index.search(query)["count"] == 2


def test_update_and_delete_change_the_counts(index):
    index.add_record("4", {"ALL": "auto", "type": ("hbo:product", MASTER)})
    index.delete_record("5", immediate_commit=True)
    result = index.search_all(drilldown=[{"name": "type"}])
    assert result["drilldown"]["type"] == [
        ("hbo:product", 4, [(BACHELOR, 2, []), (MASTER, 2, [])]),
    ]


def test_count_zero_gives_all_values_of_a_flat_field(tmp_path):
    index = Index(
        tmp_path,
        IndexProfile([IndexField.untokenized("year", drilldown=True)]),
        immediate_commit=True,
    )
    for year in range(2000, 2015):
        index.add_record(str(year), {"year": str(year)})
    assert (
        len(index.search_all(drilldown=[{"name": "year"}])["drilldown"]["year"]) == 10
    )
    result = index.search_all(drilldown=[{"name": "year", "count": 0}])
    assert len(result["drilldown"]["year"]) == 15


def test_only_an_untokenized_drilldown_field_can_be_hierarchical():
    with pytest.raises(ValueError):
        IndexField.untokenized("type", hierarchical=True)
    with pytest.raises(ValueError):
        IndexField.text("type", drilldown=True, hierarchical=True)
    with pytest.raises(ValueError):
        IndexField.untokenized("type", drilldown=True, hierarchical=True, sortable=True)
