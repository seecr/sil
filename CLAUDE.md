# sil – Seecr Indexing Lib

A search index on tantivy (it replaced Lucene in 3.0): index profile, forgiving query
language, multi-field sorting, drilldown, suggestions, timer commits. Used by swindl
(one `Index` per model). MIT licensed. Maintained by Seecr (Johan Jonkers, Thijs Janssen).
`doc/reference.md` is the user-facing reference; keep it in step with the code.

## Layout

- `sil/index.py` – `Index` (add/delete/commit/search/suggest, sorting, the query
  language), `Hit`, `Query`
- `sil/indexfield.py` – `IndexField` (untokenized, text, int, unqualified; stored,
  sortable, drilldown, suggest) and how each adds itself to the tantivy schema
- `sil/indexprofile.py` – `IndexProfile` (the fields of an index)
- `sil/engine.py` – `Engine`: the tantivy index with its one writer (lazy, behind a lock)
- `sil/drilldown.py` – counts per value (terms aggregation on a fast field)
- `sil/suggester.py` – `Suggester`: its own small tantivy index per suggest field
- `sil/commit.py` – `Commit`: commits targets, as an asyncio timer task or on demand

## Commands

```sh
pytest sil                       # the tests
flake8 sil && isort --check-only sil
```

`env/` is the virtualenv, with `requirements-dev.txt` (flake8, isort, pytest).

## Design decisions (deliberate, don't re-propose)

- tantivy, in process. No Java, no separate query server over HTTP.
- A changed profile (schema) recreates the index empty and sets `needs_reindex`; sil
  never rebuilds from data itself (it has none: the application does that).
- Invalid query syntax is searched literally: a search box never raises.
- Ordering ties (equal scores, equal sort values, `*`) by insertion order (`__seq__`),
  as Lucene did; paging must be stable.
- The writer is opened at the first change (each tantivy writer runs threads).

## Invariants to keep

- An update is a delete followed by an add of the same record id; `None` values are
  ignored.
- `__id__` is always stored; it is the record id (swindl adds the object id after it).
- Searches use a snapshot (`Engine.searcher()`); the reader is reloaded explicitly after
  a commit, so a search right after a commit sees it.
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
