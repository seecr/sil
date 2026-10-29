## begin license ##
#
# "SIL"(Seecr Index Lib) makes developing index apps easier
#
# Copyright (C) 2025-2026 Seecr (Seek You Too B.V.) https://seecr.nl
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

from .utils import ensure_current_thread_attached, mkdir

from org.apache.lucene.index import Term
from org.apache.lucene.document import Document
from org.apache.lucene.search import (
    TermQuery,
    MatchAllDocsQuery,
    Sort,
)

from org.apache.lucene.queryparser.classic import QueryParser

from .lucene import Lucene
from .commit import Commit
from .indexfield import IndexField
from .suggester import Suggester
from .drilldown import Drilldown

import logging

logger = logging.getLogger(__name__)


class Index:
    def __init__(self, path, profile, commit_timeout=10, immediate_commit=False):
        self._commit = Commit(timeout=commit_timeout)
        self._immediate_commit = immediate_commit
        self._profile = profile

        self._index_path = mkdir(path / "index")
        self._lucene = Lucene(self._index_path)
        self._drilldown = Drilldown(path)

        # the taxonomy is committed before the index, so a refreshed index reader
        # never refers to categories that are not committed yet
        self._commit.add_target(self._drilldown)
        self._commit.add_target(self._lucene)

        self._suggesters = {}

        for field in self._profile.suggest_fields():
            suggester = Suggester(path / "suggest", field.name)
            self._suggesters[field.name] = suggester
            self._commit.add_target(suggester)

        self._commit_task = None
        if not immediate_commit and commit_timeout > 0:
            self._commit_task = self._commit.as_task()
            logger.info(f"Index: auto-commit interval: {commit_timeout}")
        else:
            logger.info("Index: auto-commit disabled")

    @property
    def sortfields(self):
        return [field.name for field in self._profile.sortable_fields()]

    def shutdown(self):
        if self._commit_task is not None:
            logger.info("Index: Cancelling auto-commit")
            self._commit_task.cancel()
        self._lucene.shutdown()

        self._drilldown.close()
        for suggester in self._suggesters.values():
            suggester.close()

    def commit(self, immediate_commit=False):
        if immediate_commit or self._immediate_commit:
            self._commit.do()

    def add_record(self, record_id, field_data):
        self._delete_record(record_id)

        doc = Document()
        doc.add(IndexField.id_field(record_id))
        for field in self._profile.fields:
            if (value := field_data.get(field.name)) is not None:
                value_as_list = value if isinstance(value, list) else [value]
                if field.is_suggest:
                    for each in value_as_list:
                        self._suggesters[field.name].add(each)

                for field_value in field.as_doc_field(value_as_list):
                    doc.add(field_value)

        self._lucene.writer.addDocument(self._drilldown.build(doc))

        self.commit()

    def _delete_record(self, record_id):
        ensure_current_thread_attached()
        self._lucene.writer.deleteDocuments(Term(IndexField.ID_FIELD, record_id))

    def delete_record(self, record_id, immediate_commit=False):
        self._delete_record(record_id)
        self.commit(immediate_commit)

    def delete_all(self):
        ensure_current_thread_attached()
        self._lucene.writer.deleteAll()
        for suggester in self._suggesters.values():
            suggester.clear()
        self.commit()

    def search(self, query, page=1, limit=20, sort=None, drilldown=None):
        ensure_current_thread_attached()

        skipRecords = (page - 1) * limit

        searcher = self._lucene.searcher
        sorting = Sort.RELEVANCE
        if sort is not None:
            if isinstance(sort, str):
                sort = [sort]
            sort_fields = []
            for each in sort:
                if isinstance(each, str):
                    field_name = each
                    reverse = False
                else:
                    field_name = each["field"]
                    reverse = each.get("reverse", False)

                if (field := self._profile.get(field_name)) is None:
                    raise RuntimeError(f"Unknown field: {field_name}")

                if not field.is_sortable:
                    raise RuntimeError(f"Unsortable field: {field_name}")

                sort_fields.append(field.as_sort_field(reverse=reverse))
            sorting = Sort(sort_fields)

        results = searcher.search(query, skipRecords + limit, sorting)

        total = searcher.count(query)
        hits = results.scoreDocs

        storedFields = searcher.storedFields()
        query_results = [
            storedFields.document(hits[i].doc)
            for i in range(skipRecords, min(skipRecords + limit, total))
        ]

        drilldown_results = (
            {}
            if drilldown is None
            else self._drilldown.execute(searcher, query, drilldown)
        )

        return dict(count=total, docs=query_results, drilldown=drilldown_results)

    def search_all(self, *args, **kwargs):
        ensure_current_thread_attached()
        return self.search(MatchAllDocsQuery(), *args, **kwargs)

    def search_by_id(self, record_id, page=1, limit=20):
        ensure_current_thread_attached()
        return self.search(
            TermQuery(Term(IndexField.ID_FIELD, record_id)), page=page, limit=limit
        )

    def search_by_term(self, field, value, *args, **kwargs):
        ensure_current_thread_attached()
        return self.search(TermQuery(Term(field, value)), *args, **kwargs)

    def parse_query(self, query):
        ensure_current_thread_attached()

        if query == "*":
            query = MatchAllDocsQuery()
        else:
            parser = QueryParser(self._profile.unqualified.name, self._lucene.analyzer)
            query = parser.parse(str(query))
        return query

    def search_query(self, query, *args, **kwargs):
        parsed_query = self.parse_query(query)
        return self.search(parsed_query, *args, **kwargs)

    def suggest(self, field, value):
        suggester = self._suggesters[field]
        return suggester.suggest(value)
