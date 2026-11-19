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


from .indexfield import FACET_PATH_SEPARATOR, as_path

# "count": 0 asks for all values; a terms aggregation needs a number
ALL_VALUES = 2**31 - 1


class Drilldown:
    """Counts the values of drilldown fields in the documents that match a query.

    Lucene kept a separate taxonomy index for this; tantivy counts the terms of a
    fast field with a terms aggregation, so there is nothing to store or commit.
    Values with the same count are ordered alphabetically (Lucene ordered them by
    when a value was first indexed).

    A request is a dict: {"name": field, "count": 10}; "count": 0 gives all values.
    A hierarchical field gives (value, count, subvalues) for each value, the
    subvalues in the same form; "path" (levels, or "a>b") starts below that value,
    "depth" (default all) limits the levels. "count" is per level.
    """

    def __init__(self, profile):
        self._profile = profile

    def execute(self, searcher, query, drilldown):
        aggregations = {}
        requests = {}
        for request in drilldown:
            name = request["name"]
            if (index_field := self._profile.get(name)) is None or (
                not index_field.is_drilldown
            ):
                continue
            count = request.get("count", 10)
            # a hierarchical field: every level is a value of its own, all counted;
            # the tree is made from them below
            size = ALL_VALUES if count == 0 or index_field.is_hierarchical else count
            requests[name] = (index_field, request)
            aggregations[name] = {
                "terms": {
                    "field": index_field.facet_dimension,
                    "size": size,
                    # every segment reports its top values; more than asked for,
                    # so that the totals over several segments are exact
                    "segment_size": min(max(size * 10, 10_000), ALL_VALUES),
                    "order": {"_count": "desc"},
                }
            }
        if not aggregations:
            return {}

        aggregated = searcher.aggregate(query, aggregations)

        results = {}
        for name, (index_field, request) in requests.items():
            if not (buckets := aggregated.get(name, {}).get("buckets")):
                continue
            terms = [(bucket["key"], bucket["doc_count"]) for bucket in buckets]
            if index_field.is_hierarchical:
                terms = _tree(
                    terms,
                    path=as_path(request.get("path") or []),
                    count=request.get("count", 10),
                    depth=request.get("depth"),
                )
            if terms:
                results[name] = terms
        return results


def _tree(terms, path, count, depth):
    """(value, count, subvalues) for the values one level below path, most first,
    equal counts alphabetically, at most count (0: all) per level, depth levels
    deep (None: all)."""
    children = {}  # path of the parent -> [(level, count)]
    for key, doc_count in terms:
        levels = tuple(key.split(FACET_PATH_SEPARATOR))
        children.setdefault(levels[:-1], []).append((levels[-1], doc_count))

    def level(parent, depth):
        values = sorted(children.get(parent, []), key=lambda t: (-t[1], t[0]))
        if count:
            values = values[:count]
        return [
            (
                value,
                doc_count,
                [] if depth == 1 else level(parent + (value,), _less(depth)),
            )
            for value, doc_count in values
        ]

    return level(tuple(path), depth)


def _less(depth):
    return None if depth is None else depth - 1
