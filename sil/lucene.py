from java.nio.file import Paths
from org.apache.lucene.analysis.standard import StandardAnalyzer
from org.apache.lucene.store import FSDirectory
from org.apache.lucene.index import (
    DirectoryReader,
    IndexWriter,
    IndexWriterConfig,
    IndexOptions,
)
from org.apache.lucene.search import IndexSearcher

from .commit import Commit
import asyncio

import logging

logger = logging.getLogger(__name__)


class Lucene:
    def __init__(self, path, commit_timeout=10):
        self._directory = FSDirectory.open(Paths.get(path.as_posix()))
        self._analyzer = StandardAnalyzer()
        self._config = IndexWriterConfig(self._analyzer)
        self._config.setOpenMode(IndexWriterConfig.OpenMode.CREATE_OR_APPEND)

        self._writer = IndexWriter(self._directory, self._config)

        self._commit_task = None
        if commit_timeout > 0:
            self._commit_task = asyncio.create_task(
                Commit(self, timeout=commit_timeout).watch()
            )
            logger.info(f"Lucene: auto-commit interval: {commit_timeout}")
        else:
            self._writer.commit()
            logger.info(f"Lucene: auto-commit disabled")

    def shutdown(self):
        if self._commit_task is not None:
            logger.info("Lucene: Cancelling auto-commit")
            self._commit_task.cancel()
        if self._writer.isOpen():
            logger.info(f"Lucene: Commiting and closing writer {self._writer!r}")
            self._writer.commit()
            self._writer.close()

    @property
    def writer(self):
        return self._writer

    @property
    def analyzer(self):
        return self._analyzer

    @property
    def reader(self):
        return DirectoryReader.open(self._directory)

    @property
    def searcher(self):
        return IndexSearcher(self.reader)

    def commit(self):
        if self._writer.hasUncommittedChanges():
            logger.info(f"Committing changes for {self._writer!r}")
            if self._writer.isOpen():
                self._writer.commit()
