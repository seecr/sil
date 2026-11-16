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


class Drilldown:
    """Counts the values of drilldown fields in the documents that match a query.

    Lucene kept a separate taxonomy index for this; tantivy counts the terms of a
    fast field with a terms aggregation, so there is nothing to store or commit.
    Values with the same count are ordered alphabetically (Lucene ordered them by
    when a value was first indexed).
    """

    def __init__(self, profile):
        self._profile = profile

    def execute(self, searcher, query, drilldown):
        aggregations = {}
        for field in drilldown:
            name = field["name"]
            count = field.get("count", 10)
            if (index_field := self._profile.get(name)) is None or (
                not index_field.is_drilldown
            ):
                continue
            aggregations[name] = {
                "terms": {
                    "field": index_field.facet_dimension,
                    "size": count,
                    # every segment reports its top values; more than asked for,
                    # so that the totals over several segments are exact
                    "segment_size": max(count * 10, 10_000),
                    "order": {"_count": "desc"},
                }
            }
        if not aggregations:
            return {}

        aggregated = searcher.aggregate(query, aggregations)

        results = {}
        for name in aggregations:
            if buckets := aggregated.get(name, {}).get("buckets"):
                results[name] = [
                    (bucket["key"], bucket["doc_count"]) for bucket in buckets
                ]
        return results
