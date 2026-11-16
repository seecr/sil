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

import threading
import time


def ensure_current_thread_attached():
    """Kept for compatibility: with Lucene every thread had to be attached to the
    JVM. Tantivy needs nothing like that."""


def mkdir(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


_seq_lock = threading.Lock()
_last_seq = 0


def next_seq():
    """An always increasing number (nanoseconds since the epoch, made unique)
    that records the order in which documents were added."""
    global _last_seq
    with _seq_lock:
        _last_seq = max(time.time_ns(), _last_seq + 1)
        return _last_seq
