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

from java.nio.file import Paths
from org.apache.lucene.analysis.standard import StandardAnalyzer
from org.apache.lucene.store import FSDirectory
from org.apache.lucene.index import (
    IndexWriter,
    IndexWriterConfig,
    IndexOptions,
)
from org.apache.lucene.search import SearcherManager

import logging

logger = logging.getLogger(__name__)


class Lucene:
    def __init__(self, path):
        self._directory = FSDirectory.open(Paths.get(path.as_posix()))
        self._analyzer = StandardAnalyzer()
        self._config = IndexWriterConfig(self._analyzer)
        self._config.setOpenMode(IndexWriterConfig.OpenMode.CREATE_OR_APPEND)

        self._writer = IndexWriter(self._directory, self._config)
        self._writer.commit()

        # Searches acquire a searcher and release it when done; a commit refreshes
        # the manager, which closes an old reader only after its last search.
        # (Reads committed changes only, as before.)
        self._searcher_manager = SearcherManager(self._directory, None)

    def add_commit(self, target):
        self._commit.add_target(target)

    def shutdown(self):
        if self._writer.isOpen():
            logger.info(f"Lucene: Commiting and closing writer {self._writer!r}")
            self._writer.commit()
            self._writer.close()
        self._searcher_manager.close()

    @property
    def writer(self):
        return self._writer

    @property
    def analyzer(self):
        return self._analyzer

    def acquire_searcher(self):
        return self._searcher_manager.acquire()

    def release_searcher(self, searcher):
        self._searcher_manager.release(searcher)

    def commit(self):
        if self._writer.hasUncommittedChanges():
            logger.info(f"Committing changes for {self._writer!r}")
            if self._writer.isOpen():
                self._writer.commit()
                self._searcher_manager.maybeRefreshBlocking()
