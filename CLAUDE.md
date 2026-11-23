# sil – Seecr Indexing Lib

A search index on tantivy (it replaced Lucene in 3.0): index profile, forgiving query
language, multi-field sorting, drilldown, suggestions, timer commits. Used by swindl
(one `Index` per model). MIT licensed. Maintained by Seecr (Johan Jonkers, Thijs Janssen).
`doc/reference.md` is the user-facing reference; keep it in step with the code.

## Layout

- `sil/index.py` – `Index` (add/delete/commit/search/suggest, sorting, the query
  language), `Hit`, `Query`
- `sil/indexfield.py` – `IndexField` (untokenized, text, int, unqualified; stored,
  sortable, drilldown, hierarchical, ascii_folding, suggest) and how each adds itself to the tantivy
  schema
- `sil/indexprofile.py` – `IndexProfile` (the fields of an index)
- `sil/engine.py` – `Engine`: the tantivy index with its one writer (lazy, behind a lock)
- `sil/drilldown.py` – counts per value (terms aggregation on a fast field); a tree for a
  hierarchical field (every level is a term, joined by `\x1f` in the facet column)
- `sil/cql.py` – CQL: own parser (cqlparser's precedence: OR weakest) to a tree of
  `SearchClause`/`Boolean`, `Translator` to tantivy queries as meresco-lucene did
- `sil/suggester.py` – `Suggester`: its own small tantivy index per suggest field
- `sil/commit.py` – `Commit`: commits targets, as an asyncio timer task or on demand

## Commands

```sh
pytest sil                       # the tests
flake8 sil && isort --check-only sil
```

`env/` is the virtualenv (see the seecr-python rebuild-venv skill); the dev tools
(flake8, isort, pytest) are the `dev` dependency group in `pyproject.toml`:
`env/bin/pip install -e . --group dev`.

Releasing: give the version a `## X.Y.Z (date)` section in `CHANGELOG.md`, then push
the tag `X.Y.Z` to GitHub; `.github/workflows/publish.yml` builds it, uploads it to
PyPI (trusted publishing) and makes the GitHub release. The tag is the version
(setuptools-scm).

## Design decisions (deliberate, don't re-propose)

- tantivy, in process. No Java, no separate query server over HTTP.
- A changed profile (schema) recreates the index empty and sets `needs_reindex`; sil
  never rebuilds from data itself (it has none: the application does that).
- Invalid query syntax is searched literally: a search box never raises.
  CQL (`cql_query`) is the exception: it is for APIs (SRU), and raises `CqlError`.
- Ordering ties (equal scores, equal sort values, `*`) by insertion order (`__seq__`),
  as Lucene did; paging must be stable.
- tantivy keeps only a tokenizer's name in the schema: `Engine` registers sil's own
  (`FOLDING_TEXT_TOKENIZER`) every time it opens an index; query analysis (CQL,
  prefixes) uses the field's analyzer from `indexfield.py`, which must match it.
- The writer is opened at the first change (each tantivy writer runs threads).

## Invariants to keep

- An update is a delete followed by an add of the same record id; `None` values are
  ignored.
- `__id__` is always stored; it is the record id (swindl adds the object id after it).
- `Engine._get_writer` commits once right after opening the writer: without it a
  tantivy writer's first operation gets the last commit's opstamp, and a merge can
  undo that delete (duplicates after a restart; `engine_test.py`). Keep it.
- Searches use a snapshot (`Engine.searcher()`); the reader is reloaded explicitly after
  a commit, so a search right after a commit sees it.
- A sortable text/untokenized field has `sort_<name>` (the value), `sortprefix_<name>`
  (first 8 UTF-8 bytes as an order-preserving i64) and `sorthash_<name>` (blake2b, 8
  bytes). `_sorted_hits` orders on the prefix; hits with the same prefix are ordered on
  the value in Python (`_same_prefix`, `_whole_value`: one document read per different
  hash), or by tantivy on the text when the group is too large (`PREFIX_GROUP*`).
- Int fields are fast fields (range queries); changing a field's options changes the
  schema and needs a reindex: announce it in the CHANGELOG.

## Conventions

- Every source file starts with the license header (copy it from `sil/index.py`).
- Code style: black, isort with the black profile (`pyproject.toml`), flake8 (`.flake8`);
  lines up to 88.
- Before every push: flake8, isort and the tests must pass. The pre-push hook
  (`.githooks/pre-push`, on with `git config core.hooksPath .githooks`) runs them.
- Tests live next to the code (`*_test.py`), plain pytest functions, `tmp_path`.
- Python >= 3.11. Versions come from git tags via `setuptools_scm`. Don't tag or push
  unless asked.
