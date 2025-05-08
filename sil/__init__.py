import lucene

lucene.initVM()

from ._version import __version__  # noqa: E402

VERSION = __version__.split("+")[0]
