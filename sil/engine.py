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
import shutil
import threading

import tantivy

logger = logging.getLogger(__name__)

# The writer buffers this much before it flushes a segment by itself. One indexing
# thread per writer: there is an index per model, so their memory adds up.
WRITER_HEAP_SIZE = 15_000_000


class Engine:
    """A tantivy index with its single writer (takes the place of the Lucene class).

    Searches only see committed changes, as before. A searcher is a snapshot of
    the index: a commit in another thread never disturbs a running search, so
    there is no searcher manager or reference counting.

    The writer is opened on the first change, not before: a tantivy writer runs
    about six threads of its own (indexing, merging, ...) and each thread costs
    memory. With an index per model (and per suggest field), most of which are
    only read, opening them all up front adds up quickly; e.g. in tests run in
    parallel processes.
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
        self._heap_size = heap_size
        self._writer = None  # opened on the first change
        self._closed = False
        # the writer is one object shared by all threads: one call at a time
        self._lock = threading.Lock()
        self._dirty = False

    @property
    def index(self):
        return self._index

    @property
    def schema(self):
        return self._schema

    def _get_writer(self):
        """The writer, opened if needed (call with self._lock held)."""
        if self._closed:
            raise RuntimeError(f"Index {self._path} is shut down")
        if self._writer is None:
            self._writer = self._index.writer(self._heap_size, 1)
        return self._writer

    def add_document(self, doc):
        with self._lock:
            self._get_writer().add_document(doc)
            self._dirty = True

    def delete_term(self, field_name, value):
        with self._lock:
            self._get_writer().delete_documents_by_term(field_name, value)
            self._dirty = True

    def delete_all(self):
        with self._lock:
            self._get_writer().delete_all_documents()
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
            self._closed = True
            if self._writer is None:
                return
            logger.info(f"Committing and closing writer for {self._path}")
            if self._dirty:
                self._writer.commit()
                self._dirty = False
            self._writer.wait_merging_threads()  # also releases the index lock
            self._writer = None
