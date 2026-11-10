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

# The kinds of field. These replace the Lucene field classes (StringField,
# TextField and IntField) that used to be passed as fieldtype.
UNTOKENIZED = "untokenized"  # the value as one term, exact match only
TEXT = "text"  # the value split into lowercased words
INT = "int"  # a (64 bit) integer

# StandardAnalyzer in Lucene; tantivy's "default" tokenizer is the closest: it
# splits on everything that is not a letter or a digit and lowercases
TEXT_TOKENIZER = "default"
UNTOKENIZED_TOKENIZER = "raw"


class IndexField:
    ID_FIELD = "__id__"
    SEQ_FIELD = "__seq__"  # insertion order: orders hits that otherwise tie

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
        if fieldtype not in (UNTOKENIZED, TEXT, INT):
            raise ValueError(f"Unknown field type: {fieldtype!r}")
        self._name = name
        self._fieldtype = fieldtype
        self._stored = stored
        self._sortable = sortable
        self._drilldown = drilldown
        self._unqualified = unqualified
        self._suggest = suggest

    def add_to_schema(self, builder):
        if self._unqualified:
            builder.add_text_field(self._name, tokenizer_name=TEXT_TOKENIZER)
            return

        if self._fieldtype == INT:
            # fast as well: tantivy answers a range query ("number:[1 TO 5]") from the
            # fast field's column, not by walking the terms of the index (16 ms
            # against 0.6 ms for 120,000 documents). Changing it changes the schema:
            # an existing index is recreated empty and needs a reindex.
            builder.add_integer_field(
                self._name, stored=self._stored, indexed=True, fast=True
            )
        else:
            builder.add_text_field(
                self._name,
                stored=self._stored,
                tokenizer_name=(
                    TEXT_TOKENIZER if self._fieldtype == TEXT else UNTOKENIZED_TOKENIZER
                ),
            )

        if self._sortable:
            # a fast (column) field to sort on; stored and indexed as well, for
            # sorting on more than one field (see Index._sorted_hits)
            if self._fieldtype == INT:
                builder.add_integer_field(
                    self.sort_field_name, stored=True, indexed=True, fast=True
                )
            else:
                builder.add_text_field(
                    self.sort_field_name,
                    stored=True,
                    fast=True,
                    tokenizer_name=UNTOKENIZED_TOKENIZER,
                )

        if self._drilldown:
            # counted with a terms aggregation over this fast field
            builder.add_text_field(
                self.facet_dimension,
                fast=True,
                tokenizer_name=UNTOKENIZED_TOKENIZER,
                index_option="basic",
            )

    def add_to_doc(self, doc, values):
        if values == []:
            return

        if self._unqualified:
            values_as_text = (
                " ".join(str(v) for v in values) if isinstance(values, list) else values
            )
            doc.add_text(self._name, values_as_text)
            return

        for nr, value in enumerate(values):
            self._add_value(doc, self._name, value)
            # a sort field allows one value per document: sort on the first one
            if self._sortable and nr == 0:
                self._add_value(doc, self.sort_field_name, value)
            if self._drilldown and value:
                doc.add_text(self.facet_dimension, str(value))

    def add_missing_sort_value(self, doc):
        """A document without a value sorts as Lucene sorted it: first (an empty
        string) or as 0 for an int field."""
        self._add_value(doc, self.sort_field_name, self.missing_sort_value)

    @property
    def missing_sort_value(self):
        return 0 if self._fieldtype == INT else ""

    def _add_value(self, doc, name, value):
        if self._fieldtype == INT:
            doc.add_integer(name, int(value))
        else:
            doc.add_text(name, str(value))

    def term_value(self, value):
        """A value as the term to look for: an int for an int field, a string
        otherwise. A text field is not analyzed here (as a Lucene TermQuery)."""
        return int(value) if self._fieldtype == INT else str(value)

    @property
    def name(self):
        return self._name

    @property
    def facet_dimension(self):
        return f"facet_{self._name}"

    @property
    def sort_field_name(self):
        return f"sort_{self._name}"

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

    @property
    def is_stored(self):
        return self._stored

    @classmethod
    def untokenized(cls, name, **kwargs):
        return cls(name, UNTOKENIZED, **kwargs)

    @classmethod
    def text(cls, name, **kwargs):
        return cls(name, TEXT, **kwargs)

    @classmethod
    def int(cls, name, **kwargs):
        return cls(name, INT, **kwargs)

    @classmethod
    def unqualified(cls, name):
        return cls(name, TEXT, unqualified=True)
