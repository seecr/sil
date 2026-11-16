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

import logging
import re
from contextlib import contextmanager

import tantivy

from .commit import Commit
from .drilldown import Drilldown
from .engine import Engine
from .indexfield import INT, TEXT, UNTOKENIZED, IndexField
from .suggester import Suggester
from .utils import ensure_current_thread_attached, mkdir, next_seq

logger = logging.getLogger(__name__)

ID_FIELD = IndexField.ID_FIELD
SEQ_FIELD = IndexField.SEQ_FIELD

# characters with a meaning in the query language; replaced by a space to search
# for a query with invalid syntax literally
_QUERY_SYNTAX = re.compile(r'[+\-&|!(){}\[\]^"~*?:\\/]')
# a word ending in *, optionally with a field: "roc*", "title:roc*"
_PREFIX_QUERY = re.compile(r"(^|[\s(+\-])((?:([\w.]+):)?)(\w+)\*(?=$|[\s)])")


class Hit(dict):
    """A document found: its stored fields with their first value (as Lucene's
    Document.get); get_values(name) gives all values of a field."""

    def __init__(self, fields):
        super().__init__((name, values[0]) for name, values in fields.items() if values)
        self._fields = fields

    def get_values(self, name):
        return list(self._fields.get(name, []))


class Query:
    """A query to give to Index.search, made by Index.parse_query, term_query or
    all_of.

    constant_score: every document found scores the same (a match all query or
    exact terms). Lucene then gave the hits in the order they were added; tantivy
    is told to do the same, so listings stay in a stable order.
    """

    def __init__(self, query, constant_score=False):
        self.query = query
        self.constant_score = constant_score

    def __repr__(self):
        return f"Query({self.query!r}, constant_score={self.constant_score})"


def _unwrap(query):
    """A Query, or a tantivy query (always ordered on score)."""
    if isinstance(query, Query):
        return query.query, query.constant_score
    return query, False


# Hits with the same score as the last one of a page are ordered on age. To find
# them it looks this far ahead at most (see _hits_by_relevance).
SCORE_TIES_LOOKAHEAD = 8192


class Index:
    def __init__(self, path, profile, commit_timeout=10, immediate_commit=False):
        self._commit = Commit(timeout=commit_timeout)
        self._immediate_commit = immediate_commit
        # deferred_commit: how deep, and whether a commit was put off
        self._deferred = 0
        self._commit_pending = False
        self._profile = profile

        self._schema, self._field_names = self._build_schema()
        self._stored_fields = {ID_FIELD} | {
            field.name for field in self._profile.fields if field.is_stored
        }

        self._index_path = mkdir(path / "index")
        self._engine = Engine(self._index_path, self._schema)
        self._drilldown = Drilldown(self._profile)
        self._commit.add_target(self._engine)

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

    def _build_schema(self):
        builder = tantivy.SchemaBuilder()
        builder.add_text_field(ID_FIELD, stored=True, tokenizer_name="raw")
        builder.add_integer_field(SEQ_FIELD, fast=True)
        for field in self._profile.fields:
            if field.name == SEQ_FIELD:
                raise ValueError(f"Reserved field name: {SEQ_FIELD}")
            if field.name == ID_FIELD:
                # (swindl indexes the object's id under this name.) Its values are
                # added to the id field, after the record id, so a hit's
                # "__id__" is still the record id.
                if (
                    field.field_type != UNTOKENIZED
                    or field.is_sortable
                    or (field.is_drilldown or field.is_unqualified)
                ):
                    raise ValueError(
                        f"{ID_FIELD} can only be a plain untokenized field"
                    )
                continue
            field.add_to_schema(builder)
        schema = builder.build()
        names = {ID_FIELD} | {field.name for field in self._profile.fields}
        return schema, names

    @property
    def sortfields(self):
        return [field.name for field in self._profile.sortable_fields()]

    @property
    def needs_reindex(self):
        """True if an existing index had to be recreated because the profile
        changed (see Engine)."""
        return self._engine.recreated

    def shutdown(self):
        if self._commit_task is not None:
            logger.info("Index: Cancelling auto-commit")
            self._commit_task.cancel()
        self._engine.shutdown()
        for suggester in self._suggesters.values():
            suggester.close()

    def commit(self, immediate_commit=False):
        if immediate_commit:
            self._commit.do()
        elif self._immediate_commit:
            if self._deferred:
                self._commit_pending = True
            else:
                self._commit.do()

    @contextmanager
    def deferred_commit(self):
        """Within this block, the commit after each change of an immediate_commit
        index waits: there is one at the end of the (outermost) block, also when it
        raises. Many changes, one commit (a commit takes the most time). Queries
        within the block don't see its changes yet. An explicit commit
        (immediate_commit=True) is not put off. Without immediate_commit nothing
        changes: the auto-commit commits."""
        self._deferred += 1
        try:
            yield
        finally:
            self._deferred -= 1
            if self._deferred == 0 and self._commit_pending:
                self._commit_pending = False
                self._commit.do()

    def add_record(self, record_id, field_data):
        record_id = str(record_id)
        doc = tantivy.Document()
        doc.add_text(ID_FIELD, record_id)
        doc.add_integer(SEQ_FIELD, next_seq())
        for field in self._profile.fields:
            value = field_data.get(field.name)
            value_as_list = (
                [] if value is None else value if isinstance(value, list) else [value]
            )
            if field.is_suggest:
                for each in value_as_list:
                    self._suggesters[field.name].add(each)
            field.add_to_doc(doc, value_as_list)
            if field.is_sortable and value_as_list == []:
                field.add_missing_sort_value(doc)

        # an update is a delete followed by an add; the delete does not touch the
        # document added after it
        self._engine.delete_term(ID_FIELD, record_id)
        self._engine.add_document(doc)

        self.commit()

    def _delete_record(self, record_id):
        self._engine.delete_term(ID_FIELD, str(record_id))

    def delete_record(self, record_id, immediate_commit=False):
        self._delete_record(record_id)
        self.commit(immediate_commit)

    def delete_all(self):
        self._engine.delete_all()
        for suggester in self._suggesters.values():
            suggester.clear()
        self.commit()

    # --- queries ---

    def term_query(self, field, value):
        """A query for documents with exactly this value (not analyzed) in a field."""
        if field not in self._field_names:
            # as Lucene: an unknown field matches nothing
            return Query(tantivy.Query.empty_query(), constant_score=True)
        if field != ID_FIELD:
            value = self._profile.get(field).term_value(value)
        return Query(
            tantivy.Query.term_query(self._schema, field, value), constant_score=True
        )

    @staticmethod
    def all_of(*queries):
        """A query for documents that match all queries given (replaces building a
        Lucene BooleanQuery with MUST clauses)."""
        unwrapped = [_unwrap(query) for query in queries]
        return Query(
            tantivy.Query.boolean_query(
                [(tantivy.Occur.Must, query) for query, _ in unwrapped]
            ),
            constant_score=all(constant for _, constant in unwrapped),
        )

    def parse_query(self, query):
        query = str(query)
        if query.strip() in ("*", "*:*"):
            return Query(tantivy.Query.all_query(), constant_score=True)

        default_fields = (
            [self._profile.unqualified.name] if self._profile.unqualified else []
        )
        index = self._engine.index
        try:
            parsed = index.parse_query(
                self._prefixes_as_regex(query),
                default_field_names=default_fields,
                allow_regexes=True,
            )
        except ValueError:
            # not valid query syntax (e.g. a single quote from a search box) or an
            # unknown field: search for the text literally
            literal = _QUERY_SYNTAX.sub(" ", query)
            try:
                parsed = index.parse_query(literal, default_field_names=default_fields)
            except ValueError as e:
                raise ValueError(f"Invalid query: {query!r}") from e
        return Query(parsed)

    def _prefixes_as_regex(self, query):
        """tantivy has no prefix query in its query language ("roc*"); a regex does
        the same: "roc*" becomes "ALL:/roc.*/". Not within a quoted phrase."""

        def as_regex(match):
            before, _, field_name, word = match.groups()
            field = (
                self._profile.get(field_name)
                if field_name
                else self._profile.unqualified
            )
            if field is None or field.field_type == INT:
                return match.group(0)  # leave it to the parser
            if field.field_type == TEXT or field.is_unqualified:
                word = word.lower()  # as the words in the index
            # a regex needs a field, also when it is the default field
            return f"{before}{field.name}:/{word}.*/"

        parts = re.split(r'("[^"]*")', query)
        for nr in range(0, len(parts), 2):  # the odd parts are quoted
            parts[nr] = _PREFIX_QUERY.sub(as_regex, parts[nr])
        return "".join(parts)

    # --- searching ---

    def search(self, query, page=1, limit=20, sort=None, drilldown=None):
        query, constant_score = _unwrap(query)
        sort_keys = self._sort_keys(sort)
        offset = (page - 1) * limit

        # a snapshot of the index: a commit in another thread does not affect it
        searcher = self._engine.searcher()
        # tantivy reserves room for as many hits as asked for; never more than
        # there are documents (Lucene capped it the same way)
        wanted = min(offset + limit, searcher.num_docs)

        if sort_keys or constant_score:
            # a constant score orders on age only, like sorting on no field at all
            addresses, total = self._sorted_hits(searcher, query, wanted, sort_keys)
            addresses = addresses[offset:wanted]
        else:
            addresses, total = self._hits_by_relevance(searcher, query, offset, wanted)

        docs = [self._as_hit(searcher.doc(address)) for address in addresses]

        drilldown_results = (
            {}
            if drilldown is None
            else self._drilldown.execute(searcher, query, drilldown)
        )

        return dict(count=total, docs=docs, drilldown=drilldown_results)

    def _sort_keys(self, sort):
        if sort is None:
            return []
        if isinstance(sort, str):
            sort = [sort]
        sort_keys = []
        for each in sort:
            if isinstance(each, str):
                field_name = each
                reverse = False
            else:
                field_name = each["field"]
                reverse = each.get("reverse", False)

            if (field := self._profile.get(field_name)) is None:
                raise RuntimeError(f"Unknown field: {field_name}")

            if not field.is_sortable:
                raise RuntimeError(f"Unsortable field: {field_name}")

            sort_keys.append((field, reverse))
        return sort_keys

    def _hits_by_relevance(self, searcher, query, offset, wanted):
        """Hits by score; equal scores the oldest first (as Lucene).

        The last hit of the page may have the same score as hits after it that are
        older. Look further ahead until the score drops, in fixed steps (so every
        page looks at the same hits), but not further than SCORE_TIES_LOOKAHEAD:
        beyond that, equal scores keep the order tantivy gives them."""
        result = searcher.search(query, limit=max(wanted, 1))
        total, hits = result.count, result.hits
        if wanted == 0 or not hits:
            return [], total

        if len(hits) == wanted and total > wanted:
            boundary = hits[-1][0]
            size = wanted
            while (
                len(hits) == size
                and hits[-1][0] == boundary
                and size < max(wanted, SCORE_TIES_LOOKAHEAD)
            ):
                size = _next_step(size)
                hits = searcher.search(query, limit=size, count=False).hits

        addresses = [address for _, address in hits]
        seqs = searcher.fast_field_values(SEQ_FIELD, addresses)
        ordered = sorted(
            zip(hits, seqs), key=lambda hit_seq: (-hit_seq[0][0], hit_seq[1])
        )
        return [address for (_, address), _ in ordered[offset:wanted]], total

    def _sorted_hits(self, searcher, query, wanted, sort_keys, count=True):
        """The first `wanted` hits ordered on the sort fields, then on age.

        tantivy sorts on one fast field: sort on the first field. The hits with the
        same value as the last one may continue past it, and need ordering on the
        next fields: those are found with a query for that value, sorted on the
        next field the same way. Hits before that value are complete groups,
        ordered here on the values of the other sort fields.

        Returns the hits and the number of documents found (if count)."""
        if not sort_keys:
            result = searcher.search(
                query,
                limit=max(wanted, 1),
                count=count,
                order_by_field=SEQ_FIELD,
                order=tantivy.Order.Asc,
            )
            return [address for _, address in result.hits][:wanted], result.count

        (field, reverse), next_keys = sort_keys[0], sort_keys[1:]
        result = searcher.search(
            query,
            limit=max(wanted, 1),
            count=count,
            order_by_field=field.sort_field_name,
            order=tantivy.Order.Desc if reverse else tantivy.Order.Asc,
        )
        hits, total = result.hits[:wanted], result.count
        if wanted == 0:
            return [], total
        if len(hits) < wanted:  # all of them
            return self._sort_in_python(searcher, hits, sort_keys), total

        boundary = hits[-1][0]
        before = [hit for hit in hits if hit[0] != boundary]
        same_value = tantivy.Query.boolean_query(
            [
                (tantivy.Occur.Must, query),
                (
                    tantivy.Occur.Must,
                    tantivy.Query.term_query(
                        self._schema, field.sort_field_name, boundary
                    ),
                ),
            ]
        )
        rest, _ = self._sorted_hits(
            searcher, same_value, wanted - len(before), next_keys, count=False
        )
        return self._sort_in_python(searcher, before, sort_keys) + rest, total

    def _sort_in_python(self, searcher, hits, sort_keys):
        """Order hits (sorted on the first sort field already) on all sort fields,
        then on age. Stable sorts, the last field first."""
        if not hits:
            return []
        addresses = [address for _, address in hits]
        seqs = searcher.fast_field_values(SEQ_FIELD, addresses)
        rows = [
            (address, seq, first_value)
            for (first_value, address), seq in zip(hits, seqs)
        ]
        rows.sort(key=lambda row: row[1])

        next_keys = sort_keys[1:]
        if next_keys:
            values = {}
            for address, _, _ in rows:
                stored = searcher.doc(address).to_dict()
                values[_key(address)] = {
                    field.sort_field_name: stored.get(field.sort_field_name, [None])[0]
                    for field, _ in next_keys
                }
            for field, reverse in reversed(next_keys):
                name, missing = field.sort_field_name, field.missing_sort_value
                rows.sort(
                    key=lambda row: _or(values[_key(row[0])][name], missing),
                    reverse=reverse,
                )

        rows.sort(key=lambda row: row[2], reverse=sort_keys[0][1])
        return [address for address, _, _ in rows]

    def _as_hit(self, doc):
        return Hit(
            {
                name: values
                for name, values in doc.to_dict().items()
                if name in self._stored_fields
            }
        )

    def search_all(self, *args, **kwargs):
        return self.search(
            Query(tantivy.Query.all_query(), constant_score=True), *args, **kwargs
        )

    def search_by_id(self, record_id, page=1, limit=20):
        return self.search(self.term_query(ID_FIELD, record_id), page=page, limit=limit)

    def search_by_term(self, field, value, *args, **kwargs):
        return self.search(self.term_query(field, value), *args, **kwargs)

    def search_query(self, query, *args, **kwargs):
        parsed_query = self.parse_query(query)
        return self.search(parsed_query, *args, **kwargs)

    def suggest(self, field, value):
        suggester = self._suggesters[field]
        return suggester.suggest(value)


def _key(address):
    return (address.segment_ord, address.doc)


def _or(value, missing):
    return missing if value is None else value


def _next_step(size):
    """1024, 2048, 4096, ...: the first step larger than size."""
    step = 1024
    while step <= size:
        step *= 2
    return step


__all__ = ["Hit", "Index", "Query", "ensure_current_thread_attached"]
