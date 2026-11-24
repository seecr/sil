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

from dataclasses import replace

import pytest

from .cql import Boolean, CqlError, SearchClause, parse, rewrite, to_cql
from .index import Index
from .indexfield import IndexField
from .indexprofile import IndexProfile


def test_parse_search_clauses():
    assert parse("fiets") == SearchClause("fiets")
    assert parse('"fiets band"') == SearchClause("fiets band")
    assert parse(r'"zeg \"hoi\""') == SearchClause('zeg "hoi"')
    assert parse("title = fiets") == SearchClause("fiets", "title", "=")
    assert parse('untokenized.type exact "a>b"') == SearchClause(
        "a>b", "untokenized.type", "exact"
    )
    assert parse("year>=2010") == SearchClause("2010", "year", ">=")
    assert parse("title =/boost=2 fiets") == SearchClause("fiets", "title", "=", 2.0)


def test_or_binds_weakest_as_in_cqlparser():
    a, b, c = SearchClause("a"), SearchClause("b"), SearchClause("c")
    assert parse("a OR b AND c") == Boolean("or", a, Boolean("and", b, c))
    assert parse("a AND b OR c") == Boolean("or", Boolean("and", a, b), c)
    assert parse("a and b not c") == Boolean("not", Boolean("and", a, b), c)
    assert parse("a AND (b OR c)") == Boolean("and", a, Boolean("or", b, c))


@pytest.mark.parametrize(
    "cql",
    [
        "",
        "   ",
        '"open',
        "(a",
        "a)",
        "a AND",
        "title =",
        "a b",
        "title any fiets",
        "title <> fiets",
        "a prox b",
        "a AND/x b",
        "title =/relevant fiets",
        "> dc = http://purl.org/dc fiets",
    ],
)
def test_errors(cql):
    with pytest.raises(CqlError):
        parse(cql)


def test_to_cql_and_rewrite():
    tree = parse('a OR b AND title exact "x y"')
    assert to_cql(tree) == 'a OR (b AND title exact "x y")'
    assert parse(to_cql(tree)) == tree

    renamed = rewrite(
        tree,
        lambda c: replace(c, index="untokenized.title") if c.index == "title" else c,
    )
    assert to_cql(renamed) == 'a OR (b AND untokenized.title exact "x y")'


@pytest.fixture
def index(tmp_path):
    index = Index(
        tmp_path,
        IndexProfile(
            [
                IndexField.unqualified("__all__"),
                IndexField.text("title"),
                IndexField.untokenized("untokenized.organisation", drilldown=True),
                IndexField.untokenized(
                    "untokenized.type", drilldown=True, hierarchical=True
                ),
                IndexField.int("year"),
            ]
        ),
        immediate_commit=True,
    )

    def add(id, title, organisation, type, year):
        index.add_record(
            id,
            {
                "__all__": title,
                "title": title,
                "untokenized.organisation": organisation,
                "untokenized.type": type,
                "year": year,
            },
        )

    add("1", "De fiets van Acme", "Acme", ("vehicle", "bicycle"), 2009)
    add("2", "Fietsband en auto", "Globex", ("vehicle", "car"), 2015)
    add("3", "Auto zonder fiets", "Acme ICT", ("vehicle", "bicycle"), 2020)
    add("4", "Boten", "Globex", "boat", 2021)
    return index


def ids(index, cql, **kwargs):
    return sorted(hit["__id__"] for hit in index.search_cql(cql, **kwargs)["docs"])


def test_unqualified_terms(index):
    assert ids(index, "*") == ["1", "2", "3", "4"]
    assert ids(index, "fiets") == ["1", "3"]
    assert ids(index, "FIETS") == ["1", "3"]
    assert ids(index, '"auto zonder"') == ["3"]
    assert ids(index, '"zonder auto"') == []
    assert ids(index, "fiets*") == ["1", "2", "3"]
    # meresco-lucene: "x*" with one letter is not a prefix but the term "x"
    assert ids(index, "f*") == []


def test_booleans(index):
    assert ids(index, "fiets AND auto") == ["3"]
    assert ids(index, "fiets OR boten") == ["1", "3", "4"]
    assert ids(index, "fiets NOT auto") == ["1"]
    assert ids(index, "boten OR fiets AND auto") == ["3", "4"]
    assert ids(index, "(boten OR fiets) AND auto") == ["3"]


def test_fields(index):
    assert ids(index, "title = Fiets") == ["1", "3"]
    assert ids(index, 'title = "de fiets"') == ["1"]
    # exact: the term as it is, not analysed
    assert ids(index, "title exact fiets") == ["1", "3"]
    assert ids(index, "title exact Fiets") == []
    # untokenized: "=" is exact too; case matters
    assert ids(index, "untokenized.organisation = Acme") == ["1"]
    assert ids(index, 'untokenized.organisation exact "Acme ICT"') == ["3"]
    assert ids(index, "untokenized.organisation == acme") == []


def test_hierarchical_paths(index):
    assert ids(index, 'untokenized.type exact "vehicle"') == ["1", "2", "3"]
    assert ids(index, 'untokenized.type exact "vehicle>bicycle"') == ["1", "3"]


def test_ranges_on_int_fields(index):
    assert ids(index, "year >= 2015") == ["2", "3", "4"]
    assert ids(index, "year > 2015") == ["3", "4"]
    assert ids(index, "year <= 2015") == ["1", "2"]
    assert ids(index, "year < 2015") == ["1"]
    assert ids(index, "year = 2015") == ["2"]
    assert ids(index, "year >= 2010 AND year <= 2020 AND fiets") == ["3"]
    with pytest.raises(CqlError):
        index.cql_query("year >= twenty")
    with pytest.raises(CqlError):
        index.cql_query("title >= a")


def test_unknown_index_matches_nothing(index):
    assert ids(index, "unknown = fiets") == []
    assert ids(index, "unknown = fiets OR boten") == ["4"]
    assert ids(index, "unknown >= 3") == []


def test_a_term_without_words_is_left_out(index):
    # as meresco-lucene: an empty phrase query is dropped from the boolean query
    assert ids(index, 'fiets AND title = "*"') == ["1", "3"]
    assert ids(index, 'title = "*"') == []


def test_boost(index):
    hits = index.search_cql("title = fiets OR title =/boost=10 auto")["docs"]
    assert [hit["__id__"] for hit in hits][:2] in (["3", "2"], ["2", "3"])
    assert {hit["__id__"] for hit in hits} == {"1", "2", "3"}
    assert hits[-1]["__id__"] == "1"


def test_exact_terms_are_ordered_as_added(index):
    query = index.cql_query(
        'untokenized.organisation exact Globex OR untokenized.type exact "vehicle"'
    )
    assert query.constant_score
    hits = index.search(query)["docs"]
    assert [hit["__id__"] for hit in hits] == ["1", "2", "3", "4"]


def test_with_drilldown_and_a_parsed_tree(index):
    tree = parse("fiets OR boten")
    result = index.search_cql(
        tree, drilldown=[{"name": "untokenized.type", "count": 0}]
    )
    assert result["count"] == 3
    assert result["drilldown"]["untokenized.type"] == [
        ("vehicle", 2, [("bicycle", 2, [])]),
        ("boat", 1, []),
    ]
