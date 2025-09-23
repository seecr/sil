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

from org.apache.lucene.util import BytesRef
from org.apache.lucene.search.suggest.analyzing import AnalyzingInfixSuggester
from org.apache.lucene.analysis.standard import StandardAnalyzer

from java.util import HashSet


class Suggester:
    def __init__(self, path, name):
        self._suggester = AnalyzingInfixSuggester(
            as_directory(mkdir(path / name)), StandardAnalyzer()
        )
        self._dirty = False

    def add(self, word):
        self._suggester.add(BytesRef(word), HashSet(), 1, BytesRef(word))
        self._dirty = True

    def suggest(self, word):
        if self._dirty:
            self._suggester.refresh()
            self._dirty = False

        return [
            each.payload.utf8ToString()
            for each in self._suggester.lookup(word, 10, False, False)
        ]

    def commit(self):
        if self._dirty:
            self._suggester.commit()

    def close(self):
        self._suggester.close()
