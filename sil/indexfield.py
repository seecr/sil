from org.apache.lucene.document import (
    Field,
    SortedDocValuesField,
    StringField,
    TextField,
)
from org.apache.lucene.util import BytesRef
from org.apache.lucene.facet import FacetField


class IndexField:
    ID_FIELD = "__id__"

    def __init__(
        self,
        name,
        fieldtype,
        stored=False,
        sortable=False,
        unqualified=False,
        drilldown=False,
    ):
        self._name = name
        self._fieldtype = fieldtype
        self._stored = stored
        self._sortable = sortable
        self._drilldown = drilldown
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
        if self._drilldown:
            field_values.append(FacetField(f"facet_{self._name}", value))

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

    @property
    def is_drilldown(self):
        return self._drilldown

    @classmethod
    def id_field(cls, record_id):
        return StringField(cls.ID_FIELD, str(record_id), Field.Store.YES)

    @classmethod
    def untokenized(cls, name, **kwargs):
        return cls(name, StringField, **kwargs)

    @classmethod
    def text(cls, name, **kwargs):
        return cls(name, TextField, **kwargs)

    @classmethod
    def unqualified(cls, name):
        return cls(name, TextField, unqualified=True)
