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

import logging
import shutil
import threading

import tantivy

logger = logging.getLogger(__name__)

# The writer buffers this much before it flushes a segment by itself. One thread
# per writer: there is an index per model, so their memory adds up.
WRITER_HEAP_SIZE = 15_000_000


class Engine:
    """A tantivy index with its single writer (takes the place of the Lucene class).

    Searches only see committed changes, as before. A searcher is a snapshot of
    the index: a commit in another thread never disturbs a running search, so
    there is no searcher manager or reference counting.
    """

    def __init__(self, path, schema, heap_size=WRITER_HEAP_SIZE):
        self._path = path
        self._schema = schema
        self.recreated = False
        try:
            self._index = tantivy.Index(schema, path=path.as_posix(), reuse=True)
        except ValueError as e:
            if "schema does not match" not in str(e):
                raise
            # Lucene had no schema, tantivy does: fields added to or removed from
            # the profile make the existing index unusable. The index is derived
            # data, so start empty; the application has to rebuild it.
            logger.warning(
                f"{path}: the index profile changed, the index is recreated empty "
                "and needs to be rebuilt"
            )
            shutil.rmtree(path)
            path.mkdir(parents=True)
            self._index = tantivy.Index(schema, path=path.as_posix(), reuse=True)
            self.recreated = True

        # Reload explicitly after a commit, so a search right after a commit sees it
        # (the "OnCommit" policy reloads asynchronously, a little later).
        self._index.config_reader("Manual")
        self._writer = self._index.writer(heap_size, 1)
        # the writer is one object shared by all threads: one call at a time
        self._lock = threading.Lock()
        self._dirty = False

    @property
    def index(self):
        return self._index

    @property
    def schema(self):
        return self._schema

    def add_document(self, doc):
        with self._lock:
            self._writer.add_document(doc)
            self._dirty = True

    def delete_term(self, field_name, value):
        with self._lock:
            self._writer.delete_documents_by_term(field_name, value)
            self._dirty = True

    def delete_all(self):
        with self._lock:
            self._writer.delete_all_documents()
            self._dirty = True

    def has_uncommitted_changes(self):
        return self._dirty

    def commit(self):
        with self._lock:
            if not self._dirty or self._writer is None:
                return
            logger.info(f"Committing changes for {self._path}")
            self._writer.commit()
            self._dirty = False
            self._index.reload()

    def searcher(self):
        return self._index.searcher()

    def shutdown(self):
        with self._lock:
            if self._writer is None:
                return
            logger.info(f"Committing and closing writer for {self._path}")
            if self._dirty:
                self._writer.commit()
                self._dirty = False
            self._writer.wait_merging_threads()  # also releases the index lock
            self._writer = None
