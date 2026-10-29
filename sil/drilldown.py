## begin license ##
#
# "SIL"(Seecr Index Lib) makes developing index apps easier
#
# Copyright (C) 2025 Seecr (Seek You Too B.V.) https://seecr.nl
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

import threading

from .utils import as_directory, mkdir

from org.apache.lucene.facet import (
    FacetsConfig,
    FacetsCollector,
)
from org.apache.lucene.facet.taxonomy import FastTaxonomyFacetCounts, TaxonomyReader
from org.apache.lucene.facet.taxonomy.directory import (
    DirectoryTaxonomyWriter,
    DirectoryTaxonomyReader,
)

from lucene import JavaError


class Drilldown:
    def __init__(self, path, dimensions=()):
        self._path = as_directory(mkdir(path / "taxo"))
        self._writer = DirectoryTaxonomyWriter(self._path)
        self._facets_config = FacetsConfig()
        self._reader_lock = threading.Lock()  # opening and refreshing the reader
        # a document may have several values for a drilldown field; without this
        # Lucene refuses such a document. The counts per value stay the same.
        for dimension in dimensions:
            self._facets_config.setMultiValued(dimension, True)
        self._reader = None

    def commit(self):
        self._writer.commit()
        self._refresh_reader()

    def close(self):
        if self._reader is not None:
            self._reader.decRef()
            self._reader = None
        self._writer.close()

    @property
    def reader(self):
        """One reader for all searches, refreshed after a commit. Opening a new reader
        for every search (and never closing it) leaked files and memory."""
        with self._reader_lock:
            if self._reader is None:
                try:
                    self._reader = DirectoryTaxonomyReader(self._path)
                except JavaError:
                    return None  # nothing committed yet
            return self._reader

    def _refresh_reader(self):
        with self._reader_lock:
            if self._reader is None:
                return  # opened on first use
            new_reader = TaxonomyReader.openIfChanged(self._reader)
            if new_reader is not None:
                old_reader, self._reader = self._reader, new_reader
                # closed once no search uses it any more (see _acquire_reader)
                old_reader.decRef()

    def _acquire_reader(self):
        """The current reader with its reference count raised, so a refresh in
        another thread does not close it during a search; give it back with
        decRef()."""
        while (reader := self.reader) is not None:
            if reader.tryIncRef():
                return reader
            # closed by a refresh between reading self._reader and tryIncRef: retry
        return None

    @property
    def writer(self):
        return self._writer

    def build(self, doc):
        return self._facets_config.build(self._writer, doc)

    def execute(self, searcher, query, drilldown):
        collector = FacetsCollector()
        searcher.search(query, collector)

        if (reader := self._acquire_reader()) is None:
            return {}
        try:
            facets = FastTaxonomyFacetCounts(reader, self._facets_config, collector)

            results = {}
            for field in drilldown:
                name = field["name"]
                count = field.get("count", 10)

                if (
                    facet_result := facets.getTopChildren(count, f"facet_{name}")
                ) is not None:
                    results[name] = [
                        (i.label, i.value.intValue()) for i in facet_result.labelValues
                    ]
            return results
        finally:
            reader.decRef()
