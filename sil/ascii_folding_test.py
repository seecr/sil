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


def profile(ascii_folding=True):
    return IndexProfile(
        [
            IndexField.unqualified("ALL", ascii_folding=ascii_folding),
            IndexField.text("title", ascii_folding=ascii_folding),
        ]
    )


def add(index):
    index.add_record("1", {"ALL": "Café de Paris", "title": "Café de Paris"})
    index.add_record("2", {"ALL": "École Straße", "title": "École Straße"})


def ids(result):
    return sorted(hit["__id__"] for hit in result["docs"])


def test_accents_are_folded(tmp_path):
    index = Index(tmp_path, profile(), immediate_commit=True)
    add(index)
    for query in ["cafe", "café", "CAFÉ", "title:cafe", "title:Café"]:
        assert ids(index.search_query(query)) == ["1"], query
    assert ids(index.search_query("strasse")) == ["2"]
    assert ids(index.search_query("ecol*")) == ["2"]
    assert ids(index.search_query("écol*")) == ["2"]
    assert ids(index.search_query('"ecole strasse"')) == ["2"]


def test_accents_are_folded_in_cql(tmp_path):
    index = Index(tmp_path, profile(), immediate_commit=True)
    add(index)
    assert ids(index.search_cql("cafe")) == ["1"]
    assert ids(index.search_cql("title = École")) == ["2"]
    assert ids(index.search_cql("écol*")) == ["2"]
    assert ids(index.search_cql('title = "ecole strasse"')) == ["2"]


def test_without_ascii_folding_accents_count(tmp_path):
    index = Index(tmp_path, profile(ascii_folding=False), immediate_commit=True)
    add(index)
    assert ids(index.search_query("café")) == ["1"]
    assert ids(index.search_query("cafe")) == []
    assert ids(index.search_cql("cafe")) == []


def test_the_tokenizer_is_there_after_reopening(tmp_path):
    index = Index(tmp_path, profile(), immediate_commit=True)
    add(index)
    index.shutdown()

    index = Index(tmp_path, profile(), immediate_commit=True)
    assert not index.needs_reindex
    assert ids(index.search_query("cafe")) == ["1"]
    index.add_record("3", {"ALL": "Crème brûlée", "title": "Crème brûlée"})
    assert ids(index.search_query("creme brulee")) == ["3"]


def test_switching_ascii_folding_needs_a_reindex(tmp_path):
    Index(tmp_path, profile(ascii_folding=False), immediate_commit=True).shutdown()
    index = Index(tmp_path, profile(ascii_folding=True), immediate_commit=True)
    assert index.needs_reindex


def test_only_text_fields_fold():
    with pytest.raises(ValueError):
        IndexField.untokenized("code", ascii_folding=True)
    with pytest.raises(ValueError):
        IndexField.int("year", ascii_folding=True)
