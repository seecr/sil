import lucene
from org.apache.lucene.store import FSDirectory
from java.nio.file import Paths


def ensure_current_thread_attached():
    if (vmEnv := lucene.getVMEnv()).isCurrentThreadAttached() is False:
        vmEnv.attachCurrentThread()


def as_directory(path):
    return FSDirectory.open(Paths.get(path.as_posix()))


def mkdir(path):
    path.mkdir(parents=True, exist_ok=True)
    return path
