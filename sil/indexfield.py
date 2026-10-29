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

from org.apache.lucene.document import (
    Field,
    SortedDocValuesField,
    NumericDocValuesField,
    StringField,
    TextField,
    IntField,
)
from org.apache.lucene.search import SortField
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
        suggest=False,
    ):
        self._name = name
        self._fieldtype = fieldtype
        self._stored = stored
        self._sortable = sortable
        self._drilldown = drilldown
        self._unqualified = unqualified
        self._suggest = suggest

    def as_doc_field(self, values):
        if values == []:
            return []

        if self._unqualified:
            values_as_text = (
                " ".join(str(v) for v in values) if isinstance(values, list) else values
            )
            return [TextField(self._name, values_as_text, Field.Store.NO)]

        field_values = []
        for nr, value in enumerate(values):
            field_values.append(
                self._fieldtype(
                    self._name,
                    value,
                    Field.Store.YES if self._stored else Field.Store.NO,
                )
            )
            # a sort field allows one value per document: sort on the first one
            if self._sortable and nr == 0:
                if self._fieldtype == IntField:
                    field_values.append(
                        NumericDocValuesField(f"sort_{self._name}", value)
                    )
                else:
                    field_values.append(
                        SortedDocValuesField(f"sort_{self._name}", BytesRef(value))
                    )
            if self._drilldown and value:
                field_values.append(FacetField(self.facet_dimension, value))

        return field_values

    def as_sort_field(self, reverse=False):
        sort_type = SortField.Type.STRING
        if self._fieldtype == IntField:
            sort_type = SortField.Type.INT
        return SortField(f"sort_{self._name}", sort_type, reverse)

    @property
    def name(self):
        return self._name

    @property
    def facet_dimension(self):
        return f"facet_{self._name}"

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

    @property
    def is_suggest(self):
        return self._suggest

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
    def int(cls, name, **kwargs):
        return cls(name, IntField, **kwargs)

    @classmethod
    def unqualified(cls, name):
        return cls(name, TextField, unqualified=True)
