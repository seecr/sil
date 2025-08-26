from .utils import ensure_current_thread_attached, mkdir

from org.apache.lucene.index import Term
from org.apache.lucene.document import Document
from org.apache.lucene.search import (
    TermQuery,
    MatchAllDocsQuery,
    Sort,
    SortField,
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
        self._commit.add_target(self._lucene)

        self._drilldown = Drilldown(path)
        self._commit.add_target(self._drilldown)

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

    def shutdown(self):
        if self._commit_task is not None:
            logger.info("Index: Cancelling auto-commit")
            self._commit_task.cancel()
        self._lucene.shutdown()
        for suggester in self._suggesters.values():
            suggester.close()

    def commit(self, immediate_commit=False):
        if immediate_commit or self._immediate_commit:
            self._commit.do()

    async def add_record(self, record_id, field_data):
        self._delete_record(record_id)

        doc = Document()
        doc.add(IndexField.id_field(record_id))
        for field in self._profile.fields:
            if (value := field_data.get(field.name)) is not None:
                value_as_list = value if isinstance(value, list) else [value]
                if field.is_suggest:
                    for each in value_as_list:
                        self._suggesters[field.name].add(each)

                for each in value_as_list:
                    for field_value in field.as_doc_field(each):
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
        self.commit()

    def search(
        self, query, page=1, limit=20, sort=None, sort_reverse=False, drilldown=None
    ):
        skipRecords = (page - 1) * limit

        searcher = self._lucene.searcher
        sorting = Sort.RELEVANCE
        if sort is not None:
            if (field := self._profile.get(sort)) is None:
                raise RuntimeError(f"Unknown field: {sort}")

            if not field.is_sortable:
                raise RuntimeError(f"Unsortable field: {sort}")
            sort_type = SortField.Type.STRING
            sort_field = SortField(f"sort_{sort}", sort_type, sort_reverse)
            sorting = Sort([sort_field])

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
        return self.search(MatchAllDocsQuery(), *args, **kwargs)

    def search_by_id(self, record_id, page=1, limit=20):
        return self.search(
            TermQuery(Term(IndexField.ID_FIELD, record_id)), page=page, limit=limit
        )

    def search_by_term(self, field, value, *args, **kwargs):
        return self.search(TermQuery(Term(field, value)), *args, **kwargs)

    def search_query(self, query, *args, **kwargs):
        if query == "*":
            query = MatchAllDocsQuery()
        else:
            parser = QueryParser(self._profile.unqualified.name, self._lucene.analyzer)
            query = parser.parse(str(query))
        return self.search(query, *args, **kwargs)

    def suggest(self, field, value):
        suggester = self._suggesters[field]
        return suggester.suggest(value)
