import lucene

from org.apache.lucene.index import Term
from org.apache.lucene.document import (
    Document,
    Field,
    StringField,
    TextField,
    IntPoint,
    LongPoint,
    SortedDocValuesField,
)
from org.apache.lucene.search import (
    TermQuery,
    IndexSearcher,
    MatchAllDocsQuery,
    BooleanQuery,
    BooleanClause,
    Sort,
    SortField,
)
from org.apache.lucene.util import BytesRef
from org.apache.lucene.queryparser.classic import QueryParser

from .lucene import Lucene


def ensure_current_thread_attached():
    if (vmEnv := lucene.getVMEnv()).isCurrentThreadAttached() is False:
        vmEnv.attachCurrentThread()


class IndexProfile:
    def __init__(self, fields):
        self._fields = {field.name: field for field in fields}

        unqualified_fields = [f for f in fields if f.is_unqualified]
        if len(unqualified_fields) > 1:
            raise RuntimeError("Multiple unqualified fields")
        self._unqualified_field = (
            unqualified_fields[0] if len(unqualified_fields) == 1 else None
        )

    @property
    def unqualified(self):
        return self._unqualified_field

    @property
    def fields(self):
        return list(self._fields.values())

    def get(self, name):
        return self._fields.get(name)


class IndexField:
    ID_FIELD = "__id__"

    def __init__(
        self, name, fieldtype, stored=False, sortable=False, unqualified=False
    ):
        self._name = name
        self._fieldtype = fieldtype
        self._stored = stored
        self._sortable = sortable
        self._unqualified = unqualified

    def as_doc_field(self, value):
        if self._unqualified and isinstance(value, list):
            value = " ".join(value)

        field_values = []
        field_values.append(
            self._fieldtype(
                self._name, value, Field.Store.YES if self._stored else Field.Store.NO
            )
        )
        if self._sortable:
            field_values.append(
                SortedDocValuesField(f"sort_{self._name}", BytesRef(value))
            )

        return field_values

    @property
    def name(self):
        return self._name

    @property
    def is_sortable(self):
        return self._sortable

    @property
    def field_type(self):
        return self._fieldtype

    @property
    def is_unqualified(self):
        return self._unqualified

    @classmethod
    def id_field(cls, record_id):
        return StringField(cls.ID_FIELD, str(record_id), Field.Store.YES)

    @classmethod
    def text(cls, name, **kwargs):
        return cls(name, TextField, **kwargs)

    @classmethod
    def unqualified(cls, name):
        return cls(name, TextField, unqualified=True)


class Index:
    def __init__(self, path, profile, commit_timeout=10, immediate_commit=False):
        self._index_path = path / "index"
        self._index_path.mkdir(parents=True, exist_ok=True)

        self._lucene = Lucene(
            path, commit_timeout=0 if immediate_commit else commit_timeout
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
        self._lucene.writer.addDocument(doc)
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

    def search(self, query, page=1, limit=20, sort=None, sort_reverse=False):
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

        return dict(count=total, docs=results)

    def search_all(self, profile_id, page=1, limit=20):
        return self.search(MatchAllDocsQuery(), page=page, limit=limit)

    def search_by_id(self, record_id, page=1, limit=20):
        return self.search(
            TermQuery(Term(IndexField.ID_FIELD, record_id)), page=page, limit=limit
        )

    def search_query(self, query, page=1, limit=20, sort=None, sort_reverse=False):
        if query == "*":
            query = MatchAllDocsQuery()
        else:
            parser = QueryParser(self._profile.unqualified.name, self._lucene.analyzer)
            query = parser.parse(str(query))
        return self.search(
            query, page=page, limit=limit, sort=sort, sort_reverse=sort_reverse
        )
