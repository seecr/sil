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


class Lucene:
    def __init__(self, path):
        self._directory = FSDirectory.open(Paths.get(path.as_posix()))
        self._analyzer = StandardAnalyzer()
        self._config = IndexWriterConfig(self._analyzer)
        self._config.setOpenMode(IndexWriterConfig.OpenMode.CREATE_OR_APPEND)

        self._writer = IndexWriter(self._directory, self._config)
        commit = Commit(self._writer)
        self._commit = asyncio.create_task(commit.watch())

    def shutdown(self):
        print("Lucene: Cancelling auto-commit")
        self._commit.cancel()
        if self._writer.isOpen():
            print("Lucene: Commiting and closing writer")
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
