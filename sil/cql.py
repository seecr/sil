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

"""CQL (Contextual Query Language, https://www.loc.gov/standards/sru/cql/) for sil.

parse() gives a tree of SearchClause and Boolean; Index.cql_query() turns a tree or a
CQL string into a sil query. It follows what meresco (cqlparser and meresco-lucene)
did, so CQL that worked there gives the same hits here:

- OR binds weakest; AND and NOT bind stronger, left to right: "a OR b AND c" is
  "a OR (b AND c)", "a AND b OR c" is "(a AND b) OR c". (The CQL standard gives all
  booleans the same precedence; cqlparser did not.)
- "a NOT b" is a and not b.
- relations: "=", "==", "exact", "<", "<=", ">", ">="; the modifier "/boost=2" on a
  relation. Other relations, modifiers and prefix assignments raise CqlError.
- A term in a text field (and a term without index, in the unqualified field) is
  analysed as the field is indexed: one word is a term query, more words a phrase,
  "word*" (at least two letters, digits, "_" or "-") a prefix. A term without words
  (e.g. "*" in a text field) is left out of the query. "*" without index is
  everything.
- "exact" and "==" (and "=" on an untokenized field) look for the term as it is, not
  analysed. On a hierarchical field "a>b" is a path.
- "<", "<=", ">", ">=" are ranges on int fields only.
- An index that is not in the profile matches nothing (as Lucene did).
"""

import re
from dataclasses import dataclass, replace

import tantivy

from .indexfield import INT, TEXT

COMPARATORS = ("=", "==", "exact", "<", "<=", ">", ">=")
# comparators CQL has but sil does not: an error, not a search for their name
UNSUPPORTED_COMPARATORS = ("<>", "any", "all", "adj", "within", "encloses")
RANGES = {"<", "<=", ">", ">="}
EXACT = {"==", "exact"}

# as cqlparser's tokenizer: symbols, a quoted string (\" inside), or a word
_TOKEN = re.compile(r'(?s)\s*(\(|\)|>=|<>|<=|==|>|<|=|/|".*?(?<!\\)"|[^"()>=<\s/]+)')
_SYMBOLS = {"(", ")", ">=", "<>", "<=", "==", ">", "<", "=", "/"}
# meresco-lucene made "pr*" into a prefix query only for this form
_PREFIX = re.compile(r"^([\w-]{2,})\*$")


class CqlError(ValueError):
    """CQL that can not be parsed, or that sil does not support."""


@dataclass(frozen=True)
class SearchClause:
    """A term, or index relation term: 'fiets', 'title = fiets'."""

    term: str
    index: str | None = None
    relation: str | None = None
    boost: float | None = None

    def __str__(self):
        term = _quoted(self.term)
        if self.index is None:
            return term
        boost = "" if self.boost is None else f"/boost={self.boost:g}"
        return f"{_quoted(self.index)} {self.relation}{boost} {term}"


@dataclass(frozen=True)
class Boolean:
    """left operator right; operator is "and", "or" or "not"."""

    operator: str
    left: "SearchClause | Boolean"
    right: "SearchClause | Boolean"

    def __str__(self):
        def side(node):
            return f"({node})" if isinstance(node, Boolean) else str(node)

        return f"{side(self.left)} {self.operator.upper()} {side(self.right)}"


def parse(text):
    """The tree of a CQL string. Raises CqlError."""
    return _Parser(_tokenize(text)).parse()


def rewrite(node, function):
    """The tree with every SearchClause replaced by function(clause), which returns a
    SearchClause (dataclasses.replace(clause, index=...)) or a Boolean."""
    if isinstance(node, Boolean):
        return replace(
            node, left=rewrite(node.left, function), right=rewrite(node.right, function)
        )
    return function(node)


def to_cql(node):
    """The tree as a CQL string again."""
    return str(node)


def _kind(node):
    return "or" if node.operator == "or" else "and"


def _quoted(text):
    if (
        text
        and not re.search(r'[\s"()>=</]', text)
        and text.lower()
        not in (
            "and",
            "or",
            "not",
            "prox",
        )
    ):
        return text
    return '"' + text.replace('"', r"\"") + '"'


def _tokenize(text):
    tokens = _TOKEN.findall(text)
    if re.sub(r"\s+", "", "".join(tokens)) != re.sub(r"\s+", "", text):
        raise CqlError(f"Unrecognized token in {text!r}")
    return tokens


class _Parser:
    def __init__(self, tokens):
        self._tokens = tokens
        self._pos = 0

    def parse(self):
        if not self._tokens:
            raise CqlError("No tokens found, at least one token expected.")
        if self._tokens[0] == ">":
            raise CqlError("Unsupported CQL: prefix assignment (>)")
        tree = self._or()
        if self._pos < len(self._tokens):
            raise CqlError(f"Unexpected token: {self._tokens[self._pos]!r}")
        return tree

    def _peek(self, offset=0):
        pos = self._pos + offset
        return self._tokens[pos] if pos < len(self._tokens) else None

    def _next(self):
        token = self._peek()
        if token is None:
            raise CqlError("Unexpected end of query")
        self._pos += 1
        return token

    def _boolean(self):
        token = self._peek()
        if token is None:
            return None
        if token.lower() == "prox":
            raise CqlError("Unsupported CQL: prox")
        if token.lower() in ("and", "or", "not"):
            if self._peek(1) == "/":
                raise CqlError("Unsupported CQL: modifiers on a boolean")
            return token.lower()
        return None

    def _or(self):
        left = self._and()
        if self._boolean() == "or":
            self._pos += 1
            return Boolean("or", left, self._or())
        return left

    def _and(self):
        left = self._clause()
        while (operator := self._boolean()) in ("and", "not"):
            self._pos += 1
            left = Boolean(operator, left, self._clause())
        return left

    def _clause(self):
        if self._peek() == "(":
            self._pos += 1
            tree = self._or()
            if self._next() != ")":
                raise CqlError("Missing )")
            return tree
        following = self._peek(1)
        if following in COMPARATORS or following in UNSUPPORTED_COMPARATORS:
            index = self._term()
            relation = self._next()
            if relation in UNSUPPORTED_COMPARATORS:
                raise CqlError(f"Unsupported comparator: {relation}")
            boost = self._boost()
            return SearchClause(self._term(), index, relation, boost)
        return SearchClause(self._term())

    def _boost(self):
        if self._peek() != "/":
            return None
        self._pos += 1
        name = self._next()
        if name != "boost" or self._next() != "=":
            raise CqlError(f"Unsupported modifier: {name}")
        value = self._term()
        try:
            return float(value)
        except ValueError:
            raise CqlError(f"Not a number for boost: {value!r}") from None

    def _term(self):
        token = self._next()
        if token.startswith('"'):
            return token[1:-1].replace(r"\"", '"')
        if token in _SYMBOLS:
            raise CqlError(f"Unexpected token: {token!r}")
        return token


class Translator:
    """A CQL tree as a tantivy query for an index (used by Index.cql_query)."""

    _OCCUR = {"and": tantivy.Occur.Must, "or": tantivy.Occur.Should}

    def __init__(self, index):
        self._index = index
        self._schema = index._schema
        self._profile = index._profile

    def query(self, tree):
        """(tantivy query, constant score)"""
        translated = self._node(tree)
        if translated is None:
            # meresco: an empty BooleanQuery, which matches nothing
            return tantivy.Query.empty_query(), True
        return translated

    def _node(self, node):
        if isinstance(node, Boolean):
            return self._boolean(node)
        query = self._clause(node)
        if query is not None and node.boost is not None:
            return tantivy.Query.boost_query(query[0], node.boost), False
        return query

    def _operands(self, node, kind):
        """[(occur, node)] of a run of ORs, or of ANDs and NOTs, flattened as
        cqlparser's cqltoexpression did; the right side of a NOT is one operand."""
        if isinstance(node, Boolean) and _kind(node) == kind:
            operands = self._operands(node.left, kind)
            if node.operator == "not":
                operands.append((tantivy.Occur.MustNot, node.right))
            else:
                operands.extend(self._operands(node.right, kind))
            return operands
        return [(self._OCCUR[kind], node)]

    def _boolean(self, node):
        clauses = []
        constant = True
        for occur, operand in self._operands(node, _kind(node)):
            translated = self._node(operand)
            if translated is None:
                # as meresco-lucene: an empty query is left out
                continue
            query, operand_constant = translated
            clauses.append((occur, query))
            constant = constant and operand_constant
        if not clauses:
            return None
        return tantivy.Query.boolean_query(clauses), constant

    def _clause(self, clause):
        if clause.index is None:
            if clause.term == "*":
                return tantivy.Query.all_query(), True
            field = self._profile.unqualified
            if field is None:
                return None
            return self._analysed(field, clause.term)

        field = self._profile.get(clause.index)
        if field is None or field.is_unqualified and clause.relation in RANGES:
            return tantivy.Query.empty_query(), True

        if clause.relation in RANGES:
            return self._range(field, clause)
        if field.field_type == INT:
            return self._term_query(field, clause.term)
        if clause.relation in EXACT or field.field_type != TEXT:
            return self._term_query(field, clause.term)
        return self._analysed(field, clause.term)

    def _term_query(self, field, value):
        try:
            query = self._index.term_query(field.name, value)
        except ValueError:
            raise CqlError(f"Not a number for {field.name}: {value!r}") from None
        return query.query, query.constant_score

    def _analysed(self, field, term):
        name = field.name
        words = field.analyzer.analyze(term)
        if not words:
            return None
        if len(words) == 1:
            if _PREFIX.match(term):
                pattern = re.escape(words[0]) + ".*"
                return tantivy.Query.regex_query(self._schema, name, pattern), True
            return tantivy.Query.term_query(self._schema, name, words[0]), False
        return tantivy.Query.phrase_query(self._schema, name, words), False

    def _range(self, field, clause):
        if field.field_type != INT:
            raise CqlError(f"{clause.relation} is only supported on int fields")
        try:
            value = int(clause.term)
        except ValueError:
            raise CqlError(f"Not a number for {field.name}: {clause.term!r}") from None
        lower = value if ">" in clause.relation else None
        upper = value if "<" in clause.relation else None
        query = tantivy.Query.range_query(
            self._schema,
            field.name,
            tantivy.FieldType.Integer,
            lower,
            upper,
            include_lower=clause.relation == ">=" or lower is None,
            include_upper=clause.relation == "<=" or upper is None,
        )
        return query, True
