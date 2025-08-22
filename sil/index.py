import lucene

from org.apache.lucene.index import Term
from org.apache.lucene.document import Document
from org.apache.lucene.search import (
    TermQuery,
    IndexSearcher,
    MatchAllDocsQuery,
    BooleanQuery,
    BooleanClause,
    Sort,
    SortField,
)
from org.apache.lucene.store import FSDirectory
from org.apache.lucene.util import BytesRef

from org.apache.lucene.facet import (
    FacetField,
    FacetsConfig,
    FacetsCollector,
    DrillDownQuery,
)
from org.apache.lucene.facet.taxonomy import FastTaxonomyFacetCounts
from org.apache.lucene.facet.taxonomy.directory import (
    DirectoryTaxonomyWriter,
    DirectoryTaxonomyReader,
)
from org.apache.lucene.queryparser.classic import QueryParser
from java.nio.file import Paths

from .lucene import Lucene
from .indexfield import IndexField


def ensure_current_thread_attached():
    if (vmEnv := lucene.getVMEnv()).isCurrentThreadAttached() is False:
        vmEnv.attachCurrentThread()


class Index:
    def __init__(self, path, profile, commit_timeout=10, immediate_commit=False):
        self._index_path = path / "index"
        self._index_path.mkdir(parents=True, exist_ok=True)

        self._taxo_path = path / "taxo"
        self._taxo_path.mkdir(parents=True, exist_ok=True)
        self._taxo_dir = FSDirectory.open(Paths.get(self._taxo_path.as_posix()))
        self._taxowriter = DirectoryTaxonomyWriter(self._taxo_dir)

        self._facets_config = FacetsConfig()

        self._lucene = Lucene(
            self._index_path, commit_timeout=0 if immediate_commit else commit_timeout
        )

        self._profile = profile
        self._immediate_commit = immediate_commit

    def shutdown(self):
        self._lucene.shutdown()

    async def add_record(self, record_id, field_data):
        self._delete_record(record_id)

        doc = Document()
        doc.add(IndexField.id_field(record_id))

        for field in self._profile.fields:
            if (value := field_data.get(field.name)) is not None:
                if isinstance(value, list):
                    for each in value:
                        for field_value in field.as_doc_field(each):
                            doc.add(field_value)
                else:
                    for field_value in field.as_doc_field(value):
                        doc.add(field_value)

        self._lucene.writer.addDocument(
            self._facets_config.build(self._taxowriter, doc)
        )

        self._taxowriter.commit()

        if self._immediate_commit:
            self._lucene.commit()

    def _delete_record(self, record_id):
        ensure_current_thread_attached()
        self._lucene.writer.deleteDocuments(Term(IndexField.ID_FIELD, record_id))

    def delete_record(self, record_id, immediate_commit=False):
        self._delete_record(record_id)
        if immediate_commit or self._immediate_commit:
            self._lucene.commit()

    def delete_all(self):
        ensure_current_thread_attached()
        self._lucene.writer.deleteAll()
        if self._immediate_commit:
            self._lucene.commit()

    def search(
        self, query, page=1, limit=20, sort=None, sort_reverse=False, drilldown=None
    ):
        drilldown = drilldown or []
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
        results = [
            storedFields.document(hits[i].doc)
            for i in range(skipRecords, min(skipRecords + limit, total))
        ]

        drilldown_results = {}
        if len(drilldown) > 0:
            collector = FacetsCollector()
            searcher.search(query, collector)

            taxoReader = DirectoryTaxonomyReader(self._taxo_dir)
            facets = FastTaxonomyFacetCounts(taxoReader, self._facets_config, collector)

            for field in drilldown:
                name = field["name"]
                count = field.get("count", 10)

                if (
                    facet_result := facets.getTopChildren(count, f"facet_{name}")
                ) is not None:
                    drilldown_results[name] = [
                        (i.label, i.count) for i in facet_result.labelValues
                    ]

        return dict(count=total, docs=results, drilldown=drilldown_results)

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
