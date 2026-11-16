## begin license ##
#
# "SIL"(Seecr Index Lib) makes developing index apps easier
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "Seecr Index Lib"
#
# "Seecr Index Lib" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
#
## end license ##

import tarfile
from pathlib import Path

import tantivy

from .engine import Engine

# An index as a process left it that was killed right after a commit (from swindl's
# crash test): its last commit has opstamp 7685, and so do the deletes of that commit
# in three of its segments. Item:10ae2db8... is in one of those.
FIXTURE = Path(__file__).parent / "testdata" / "restart-opstamp.tar.gz"
UPDATED = [
    "Item:10ae2db8-4018-479f-b75d-15bd0d1b17c5",
    "Item:cf2a4386-6002-41c3-8e88-880f360a5734",
    "Item:082ea4b7-d9c2-4f9f-a7be-6f7e2fb9e376",
    "Item:0373b739-d670-4af4-8943-13b84f64127a",
    "Item:46d05fa6-90dc-487f-9356-97d01e0bbf2a",
    "Item:847db750-fa9e-4c60-9b36-a3ff5f0f2ccc",
    "Item:1fdc889f-5cde-428b-8331-a5719c35115b",
    "Item:28363d6c-3d40-4222-bb99-29d7dfe8ebce",
]


def test_updates_after_a_restart_leave_no_duplicates(tmp_path):
    """A new tantivy writer gives its first operation the opstamp of the last commit,
    which that commit's deletes have too. A merge then took such a delete for one it
    had applied already: the old version of an updated document came back next to
    the new one. The engine commits once when it opens its writer, to move past it."""
    with tarfile.open(FIXTURE) as tar:
        tar.extractall(tmp_path, filter="data")
    path = tmp_path / "index"
    engine = Engine(path, tantivy.Index.open(str(path)).schema)
    for qid in UPDATED:  # updates, each committed: merges happen meanwhile
        engine.delete_term("__id__", qid)
        doc = tantivy.Document()
        doc.add_text("__id__", qid)
        doc.add_integer("__seq__", 1)
        engine.add_document(doc)
        engine.commit()
    engine.shutdown()  # waits for the merges

    index = tantivy.Index.open(str(path))
    searcher = index.searcher()
    for qid in UPDATED:
        query = tantivy.Query.term_query(index.schema, "__id__", qid)
        assert searcher.search(query, limit=10).count == 1, qid
