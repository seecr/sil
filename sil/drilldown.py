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

from .utils import as_directory, mkdir

from org.apache.lucene.facet import (
    FacetsConfig,
    FacetsCollector,
)
from org.apache.lucene.facet.taxonomy import FastTaxonomyFacetCounts
from org.apache.lucene.facet.taxonomy.directory import (
    DirectoryTaxonomyWriter,
    DirectoryTaxonomyReader,
)


class Drilldown:
    def __init__(self, path):
        self._path = as_directory(mkdir(path / "taxo"))
        self._writer = DirectoryTaxonomyWriter(self._path)
        self._facets_config = FacetsConfig()

    def commit(self):
        self._writer.commit()

    def close(self):
        self._writer.close()

    @property
    def reader(self):
        return DirectoryTaxonomyReader(self._path)

    @property
    def writer(self):
        return self._writer

    def build(self, doc):
        return self._facets_config.build(self._writer, doc)

    def execute(self, searcher, query, drilldown):
        collector = FacetsCollector()
        searcher.search(query, collector)

        facets = FastTaxonomyFacetCounts(self.reader, self._facets_config, collector)

        results = {}
        for field in drilldown:
            name = field["name"]
            count = field.get("count", 10)

            if (
                facet_result := facets.getTopChildren(count, f"facet_{name}")
            ) is not None:
                results[name] = [(i.label, i.count) for i in facet_result.labelValues]
        return results
