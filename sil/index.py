import lucene

from org.apache.lucene.index import Term
from org.apache.lucene.document import (
    Document,
    Field,
    StringField,
    TextField,
    IntPoint,
    LongPoint,
)
from org.apache.lucene.search import (
    TermQuery,
    IndexSearcher,
    MatchAllDocsQuery,
    BooleanQuery,
    BooleanClause,
)
from org.apache.lucene.queryparser.classic import QueryParser

from .lucene import Lucene


def ensure_current_thread_attached():
    if (vmEnv := lucene.getVMEnv()).isCurrentThreadAttached() is False:
        vmEnv.attachCurrentThread()


class IndexProfile:
    def __init__(self, fields=None):
        self._fields = fields or []

        unqualified_fields = [f for f in self._fields if f.is_unqualified]
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
        return self._fields


class IndexField:
    ID_FIELD = "__id__"

    def __init__(self, name, fieldtype, stored=False, unqualified=False):
        self._name = name
        self._fieldtype = fieldtype
        self._stored = stored
        self._unqualified = unqualified

    def as_doc_field(self, value):
        if self._unqualified and isinstance(value, list):
            value = " ".join(value)
        return self._fieldtype(
            self._name, value, Field.Store.YES if self._stored else Field.Store.NO
        )

    @property
    def name(self):
        return self._name

    @property
    def is_unqualified(self):
        return self._unqualified

    @classmethod
    def id_field(cls, record_id):
        return StringField(cls.ID_FIELD, str(record_id), Field.Store.YES)

    @classmethod
    def text(cls, name, stored=False):
        return cls(name, TextField, stored=stored)

    @classmethod
    def unqualified(cls, name):
        return cls(name, TextField, unqualified=True)


class Index:
    def __init__(self, path, profile, commit_timeout=10, immediate_commit=False):
        self._index_path = path / "index"
        self._index_path.mkdir(parents=True, exist_ok=True)

        self._lucene = Lucene(path, commit_timeout=commit_timeout)
        self._profile = profile
        self._immediate_commit = immediate_commit

    def shutdown(self):
        self._lucene.shutdown()

    async def add_record(self, record_id, field_data):
        self.delete_record(record_id)

        doc = Document()
        doc.add(IndexField.id_field(record_id))
        for field in self._profile.fields:
            if (value := field_data.get(field.name)) is not None:
                if isinstance(value, list):
                    for each in value:
                        doc.add(field.as_doc_field(each))
                else:
                    doc.add(field.as_doc_field(value))
        self._lucene.writer.addDocument(doc)
        if self._immediate_commit:
            self._lucene.commit()

    def delete_record(self, record_id):
        ensure_current_thread_attached()
        self._lucene.writer.deleteDocuments(Term(IndexField.ID_FIELD, record_id))

    def search(self, query, page=1, limit=20, sortedby=None):
        skipRecords = (page - 1) * limit

        searcher = self._lucene.searcher
        hits = searcher.search(query, skipRecords + limit).scoreDocs
        count = len(hits)

        storedFields = searcher.storedFields()
        results = [
            storedFields.document(hits[i].doc)
            for i in range(skipRecords, min(skipRecords + limit, count))
        ]

        return dict(count=count, docs=results)

    def search_all(self, profile_id, page=1, limit=20):
        return self.search(MatchAllDocsQuery(), page=page, limit=limit)

    def search_by_id(self, record_id, page=1, limit=20):
        return self.search(
            TermQuery(Term(IndexField.ID_FIELD, record_id)), page=page, limit=limit
        )

    def search_query(self, query, page=1, limit=20):
        if query == "*":
            query = MatchAllDocsQuery()
        else:
            parser = QueryParser(self._profile.unqualified.name, self._lucene.analyzer)
            query = parser.parse(str(query))
        return self.search(query, page=page, limit=limit)
