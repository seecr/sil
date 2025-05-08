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


class IndexFields:
    def __init__(self, fields=None):
        self._fields = fields or []

    @property
    def fields(self):
        return self._fields

    def add_field(self, name, fieldtype, stored=False):
        self._fields.append(
            dict(
                name=name,
                field=fieldtype,
                stored=False,
                storable=fieldtype not in [IntPoint, LongPoint],
                tokenized=False,
            )
        )


class IndexField:
    ID_FIELD = "__id__"

    def __init__(self, name, fieldtype, stored=False, convert=None):
        self._name = name
        self._fieldtype = fieldtype
        self._stored = stored
        self._convert = lambda x: x if convert is None else convert

    def as_doc_field(self, value):
        return self._fieldtype(
            self._name, value, Field.Store.YES if self._stored else Field.Store.NO
        )

    @property
    def name(self):
        return self._name

    @classmethod
    def id_field(cls, record_id):
        return StringField(cls.ID_FIELD, str(record_id), Field.Store.YES)

    @classmethod
    def text(cls, name, stored=False):
        return cls(name, TextField, stored=stored)


class Index:
    def __init__(self, path, fields):
        self._index_path = path / "index"
        self._index_path.mkdir(parents=True, exist_ok=True)

        self._lucene = Lucene(path)
        self._fields = fields

    def shutdown(self):
        self._lucene.shutdown()

    async def add_record(self, record_id, field_data):
        self.delete_record(record_id)

        doc = Document()
        doc.add(IndexField.id_field(record_id))
        for field in self._fields.fields:
            if (value := field_data.get(field.name)) is not None:
                if isinstance(value, list):
                    for each in value:
                        doc.add(field.as_doc_field(each))
                else:
                    doc.add(field.as_doc_field(value))
        self._lucene.writer.addDocument(doc)

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
        return self.search(TermQuery(Term("__id__", record_id)), page=page, limit=limit)

    def search_query(self, query, page=1, limit=20):
        if query == "*":
            query = MatchAllDocsQuery()
        else:
            parser = QueryParser("ALL", self._lucene.analyzer)
            query = parser.parse(str(query))
        return self.search(query, page=page, limit=limit)
