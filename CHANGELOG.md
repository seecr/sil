# Changelog

## Unreleased

### Fixed

- pytest and pytest-asyncio are dependencies again: the tests are part of the package
  (3.4.0 had moved them to the dev group). The dev group has flake8, isort and
  pytest-xdist.

## 3.4.0 (2026-11-23)

First release on PyPI: `pip install seecr-sil` (the import stays `sil`).

### Changed

- setuptools-scm is no longer installed with sil (it is only needed to build it); the
  only dependency is tantivy. The dev tools (flake8, isort, pytest) are the `dev`
  dependency group in `pyproject.toml` (`pip install -e . --group dev`);
  `requirements-dev.txt` is gone.
- The package metadata names the license as an SPDX expression (`MIT`).

### Added

- Published on GitHub (https://github.com/seecr/sil) and PyPI as `seecr-sil` (the name
  `sil` was taken there): `pip install seecr-sil`; the import stays `import sil`. An
  application that depends on `sil` now depends on `seecr-sil`; in an existing
  virtualenv, `pip uninstall sil` first (both install the `sil` package). Project URLs and
  classifiers in the metadata, tests in GitHub Actions, and a release to PyPI for every
  version tag.

## 3.3.0 (2026-11-20)

### Added

- Hierarchical drilldown: `IndexField.untokenized(name, drilldown=True,
  hierarchical=True)`. Values are paths (a tuple of levels, or levels with `>` between
  them); the drilldown gives a tree of `(value, count, subvalues)`, with `path` (start
  below a value) and `depth` in the request; a term query on a level finds everything
  below it. See "Hierarchical drilldown" in `doc/reference.md`.
- Drilldown `"count": 0` gives all values (as meresco-lucene's `maxTerms=0`).
- `ascii_folding=True` for text and unqualified fields: `cafe` finds `Café`, `strasse`
  finds `Straße`, in the query language, prefixes and CQL alike (as meresco-lucene's
  analyzer). Turning it on or off for a field changes the schema: reindex.
- CQL: `Index.cql_query(cql)` and `Index.search_cql(cql, ...)`, with `sil.cql.parse`,
  `rewrite` and `to_cql` for the tree. Gives the hits Meresco (cqlparser,
  meresco-lucene) gave, including its precedence (`OR` binds weakest). Own parser, no
  new dependency. See "CQL" in `doc/reference.md`.

No change to the schema of existing fields: no reindex needed.

## 3.2.0 (2026-11-16)

**Rebuild every index after upgrading.** It removes duplicates the bug below may have
left, and an index with a sortable text or untokenized field needs it anyway: such a
field gets two extra columns, which changes the schema, so that index starts empty (and
`needs_reindex` is `True`).

### Fixed

- After a restart (or a crash) an update could leave the old version of a document in
  the index next to the new one. A new tantivy writer gives its first operation the
  opstamp of the last commit, which that commit's deletes have too; a merge then took
  such a delete for one it had applied already. The engine now commits once when it
  opens its writer. Duplicates already in an index go with the rebuild.

### License

- sil is now MIT licensed (was GPLv2), like SWL.

### Changed

- Sorting on a text or untokenized field is several times faster: tantivy sorts on a
  text column some 30 times slower than on an int column. sil now sorts on the first 8
  bytes of the value as an int, and puts hits with the same first bytes in order itself,
  reading one document per different value (a hash of the value tells which are the
  same). With 50,000 records: a range of years sorted on artist takes 0.7 ms instead
  of 4.4 ms, page 51 of everything sorted on artist 4 ms instead of 185 ms. Where many
  different values share their first 8 bytes, it is as fast as before (tantivy sorts
  those on the text).

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
