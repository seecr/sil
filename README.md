# sil – Seecr Indexing Lib

A search index for Python applications, on [tantivy](https://github.com/quickwit-oss/tantivy):
an index profile in Python, a forgiving query language, sorting on several fields,
drilldown (counts per value), suggestions while typing, and commits on a timer. One index
is one directory; no server, no JVM.

```python
from sil.index import Index
from sil.indexfield import IndexField
from sil.indexprofile import IndexProfile

index = Index(path, IndexProfile([
    IndexField.unqualified("all"),
    IndexField.untokenized("genre", drilldown=True),
    IndexField.int("year", sortable=True),
]), immediate_commit=True)

index.add_record("book-1", {"all": "Dune Frank Herbert", "genre": "sf", "year": 1965})
index.search_query("dune", sort="year", drilldown=[{"name": "genre"}])
# {"count": 1, "docs": [{"__id__": "book-1"}], "drilldown": {"genre": [("sf", 1)]}}
```

Install with `pip install seecr-sil` (the package is `sil`). It needs Python 3.11 or
newer and tantivy.

The [reference](https://github.com/seecr/sil/blob/master/doc/reference.md) describes
everything; the [changelog](https://github.com/seecr/sil/blob/master/CHANGELOG.md) says
what changed. sil was built on Lucene (through JCC) up to 2.x; 3.0 replaced it with
tantivy.

MIT licensed, see [LICENSE](https://github.com/seecr/sil/blob/master/LICENSE). By
[Seecr](https://seecr.nl).
