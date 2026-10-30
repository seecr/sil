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

import tantivy

from .engine import Engine
from .utils import mkdir, next_seq

WORD = "word"  # the suggestion as it was added
WORDS = "words"  # the suggestion split into lowercased words, to match on
SEQ = "seq"  # when it was added: suggestions are given in that order

# the same as the "default" tokenizer, to split what is typed the same way
_analyzer = (
    tantivy.TextAnalyzerBuilder(tantivy.Tokenizer.simple())
    .filter(tantivy.Filter.remove_long(40))
    .filter(tantivy.Filter.lowercase())
    .build()
)


def _schema():
    builder = tantivy.SchemaBuilder()
    builder.add_text_field(WORD, stored=True, tokenizer_name="raw")
    builder.add_text_field(WORDS, tokenizer_name="default")
    builder.add_integer_field(SEQ, fast=True)
    return builder.build()


class Suggester:
    """Suggests the words added to it whose words start with what is typed, like
    Lucene's AnalyzingInfixSuggester: "yo" suggests "New York". The last word
    typed may be incomplete, the ones before it must match a whole word."""

    LIMIT = 10

    def __init__(self, path, name):
        self._path = mkdir(path / name)
        self._schema = _schema()
        self._engine = Engine(self._path, self._schema)

    def add(self, word):
        word = str(word)
        # replaces an existing entry for the same word: no duplicates when a record
        # is indexed again
        self._engine.delete_term(WORD, word)
        doc = tantivy.Document()
        doc.add_text(WORD, word)
        doc.add_text(WORDS, word)
        doc.add_integer(SEQ, next_seq())
        self._engine.add_document(doc)

    def clear(self):
        """Remove all suggestions (used before rebuilding the index)."""
        self._engine.delete_all()

    def suggest(self, word):
        if not (tokens := _analyzer.analyze(str(word))):
            return []

        *complete, last = tokens
        queries = [tantivy.Query.term_query(self._schema, WORDS, t) for t in complete]
        # tokens are letters and digits only, nothing to escape in the regex
        queries.append(tantivy.Query.regex_query(self._schema, WORDS, f"{last}.*"))
        query = tantivy.Query.boolean_query(
            [(tantivy.Occur.Should, query) for query in queries]
        )

        searcher = self._engine.searcher()
        result = searcher.search(
            query,
            limit=self.LIMIT,
            count=False,
            order_by_field=SEQ,
            order=tantivy.Order.Asc,
        )
        return [searcher.doc(address)[WORD][0] for _, address in result.hits]

    def commit(self):
        self._engine.commit()

    def close(self):
        self._engine.shutdown()
