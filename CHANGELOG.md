# Changelog

## 3.1.1 (unreleased)

### License

- sil is now MIT licensed (was GPLv2), like SWL.

### Changed

- The wheel only has the package itself (`sil/`); it used to install `doc/`, `examples/` and
  other directories of the repository into site-packages too.
- pytest, pytest-asyncio, pytest-xdist and python-multipart are no longer dependencies
  of sil; the test tools moved to `requirements-dev.txt`.
- `README.md`, `doc/reference.md`, this changelog, `LICENSE`, a pre-push hook
  (flake8, isort, tests). No change in behaviour.

## 3.1.0 (2026-11-10)

**Rebuild indexes with int fields after upgrading**: int fields are fast fields now,
which changes the schema; an existing index with int fields starts empty (and
`needs_reindex` is `True`).

### Added

- `Index.deferred_commit()`: many changes of an immediate-commit index, one commit at the
  end of the block.

### Changed

- A range query on an int field reads the fast field's column (about 0.6 ms instead of
  16 ms for 120,000 documents).

## 3.0.1 (2026-10-30)

### Changed

- The tantivy writer is opened at the first change, not when the index is opened: an
  index that is only searched costs little memory.
- The search limit is capped at the number of documents.

## 3.0.0 (2026-10-30)

Lucene (through JCC and a JVM) is replaced by tantivy. No JVM, no `LD_LIBRARY_PATH`, no
Lucene build.

### Breaking changes

- An existing Lucene index cannot be read: rebuild the indexes.
- The field types are `IndexField.untokenized`, `.text`, `.int` and `.unqualified`
  (instead of Lucene's field classes).
- Build queries with `Index.term_query` and `Index.all_of` instead of Lucene queries.
- Drilldown values with equal counts are ordered alphabetically.

## 2.x and before

Lucene-based; see the git history.
