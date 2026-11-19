## begin license ##
#
# "SIL"(Seecr Index Lib) makes developing index apps easier
#
# Copyright (C) 2025-2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "Seecr Index Lib"
#
# "Seecr Index Lib" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
#
## end license ##

import hashlib

import tantivy

# The kinds of field. These replace the Lucene field classes (StringField,
# TextField and IntField) that used to be passed as fieldtype.
UNTOKENIZED = "untokenized"  # the value as one term, exact match only
TEXT = "text"  # the value split into lowercased words
INT = "int"  # a (64 bit) integer

# StandardAnalyzer in Lucene; tantivy's "default" tokenizer is the closest: it
# splits on everything that is not a letter or a digit and lowercases
TEXT_TOKENIZER = "default"
UNTOKENIZED_TOKENIZER = "raw"

# The words of a text the way TEXT_TOKENIZER makes them: tantivy's "default" is the
# simple tokenizer, words longer than 40 bytes left out, lowercased. Used to analyse
# terms of a query (CQL) as the field was indexed; change both together.
text_analyzer = (
    tantivy.TextAnalyzerBuilder(tantivy.Tokenizer.simple())
    .filter(tantivy.Filter.remove_long(40))
    .filter(tantivy.Filter.lowercase())
    .build()
)

# Between the levels of a hierarchical value, as it is given and searched for:
# ("hbo:product", "bachelorThesis") is the term "hbo:product>bachelorThesis"
PATH_SEPARATOR = ">"
# Between the levels in the drilldown column: a character no level contains, so the
# levels can be told apart again when counting
FACET_PATH_SEPARATOR = "\x1f"


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
        hierarchical=False,
    ):
        if fieldtype not in (UNTOKENIZED, TEXT, INT):
            raise ValueError(f"Unknown field type: {fieldtype!r}")
        if hierarchical and not (
            fieldtype == UNTOKENIZED and drilldown and not unqualified
        ):
            raise ValueError("Only an untokenized drilldown field can be hierarchical")
        if hierarchical and (sortable or stored or suggest):
            raise ValueError(
                "A hierarchical field can not be sortable, stored or suggest"
            )
        self._name = name
        self._fieldtype = fieldtype
        self._stored = stored
        self._sortable = sortable
        self._drilldown = drilldown
        self._unqualified = unqualified
        self._suggest = suggest
        self._hierarchical = hierarchical

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
                # tantivy sorts on a text column some 30 times slower than on an int
                # column: the first 8 bytes of the value as an int sort the same way,
                # and Index._sorted_hits sorts on those first (see sort_prefix)
                builder.add_integer_field(
                    self.sort_prefix_field_name, indexed=True, fast=True
                )
                # and a hash of the whole value: hits with the same prefix and the
                # same hash have the same value, without reading their documents
                builder.add_integer_field(self.sort_hash_field_name, fast=True)

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

        if self._hierarchical:
            # every level of every path: a term query on "a" finds "a>b" too, and
            # the drilldown counts each level. A level shared by two values of one
            # document is added once, so the document counts once for it.
            paths = {}
            for value in values:
                path = as_path(value)
                for depth in range(1, len(path) + 1):
                    paths[tuple(path[:depth])] = None
            for path in paths:
                doc.add_text(self._name, PATH_SEPARATOR.join(path))
                doc.add_text(self.facet_dimension, FACET_PATH_SEPARATOR.join(path))
            return

        for nr, value in enumerate(values):
            self._add_value(doc, self._name, value)
            # a sort field allows one value per document: sort on the first one
            if self._sortable and nr == 0:
                self._add_sort_value(doc, value)
            if self._drilldown and value:
                doc.add_text(self.facet_dimension, str(value))

    def add_missing_sort_value(self, doc):
        """A document without a value sorts as Lucene sorted it: first (an empty
        string) or as 0 for an int field."""
        self._add_sort_value(doc, self.missing_sort_value)

    def _add_sort_value(self, doc, value):
        self._add_value(doc, self.sort_field_name, value)
        if self.has_sort_prefix:
            doc.add_integer(self.sort_prefix_field_name, sort_prefix(str(value)))
            doc.add_integer(self.sort_hash_field_name, sort_hash(str(value)))

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
        otherwise. A text field is not analyzed here (as a Lucene TermQuery). A path
        in a hierarchical field may be given as a tuple or list of levels."""
        if self._fieldtype == INT:
            return int(value)
        if self._hierarchical:
            return PATH_SEPARATOR.join(as_path(value))
        return str(value)

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
    def sort_prefix_field_name(self):
        return f"sortprefix_{self._name}"

    @property
    def sort_hash_field_name(self):
        return f"sorthash_{self._name}"

    @property
    def has_sort_prefix(self):
        """A sortable text or untokenized field: sorted on its prefix first."""
        return self._sortable and self._fieldtype != INT

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
    def is_hierarchical(self):
        return self._hierarchical

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


def as_path(value):
    """A hierarchical value as a list of levels: a tuple or list is a path, a string
    is split on ">" ("hbo:product>bachelorThesis"). Empty levels are left out."""
    if isinstance(value, (list, tuple)):
        levels = [str(level) for level in value]
    else:
        levels = str(value).split(PATH_SEPARATOR)
    return [level for level in levels if level != ""]


def sort_prefix(text):
    """The first 8 bytes (UTF-8) of text as a signed 64 bit int that sorts as the text
    does: tantivy orders text by its bytes. Texts with the same first 8 bytes get the
    same number; Index._sorted_hits puts those in order on the whole text."""
    prefix = text.encode("utf-8")[:8].ljust(8, b"\0")
    return int.from_bytes(prefix, "big") - 2**63


def sort_hash(text):
    """A 64 bit hash of text (the same in every process, unlike hash()): two texts
    with the same prefix and the same hash are taken to be the same."""
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)
