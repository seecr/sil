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
