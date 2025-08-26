from .utils import as_directory, mkdir

from org.apache.lucene.util import BytesRef


from org.apache.lucene.search.suggest.analyzing import AnalyzingInfixSuggester
from org.apache.lucene.analysis.standard import StandardAnalyzer

from java.util import HashSet


class Suggester:
    def __init__(self, path, name):
        self._suggester = AnalyzingInfixSuggester(
            as_directory(mkdir(path / name)), StandardAnalyzer()
        )

    def add(self, word):
        self._suggester.add(BytesRef(word), HashSet(), 1, BytesRef(word))

    def suggest(self, word):
        return [
            each.payload.utf8ToString()
            for each in self._suggester.lookup(word, 10, False, False)
        ]

    def commit(self):
        self._suggester.commit()
        self._suggester.refresh()
