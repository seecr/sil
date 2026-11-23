## begin license ##
#
# "SIL"(Seecr Indexing Lib) provides a search index on tantivy
#
# Copyright (C) 2025-2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "sil"
#
# "sil" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
#
## end license ##

import asyncio
import logging

logger = logging.getLogger(__name__)


class Commit:
    def __init__(self, timeout=10):
        self._timeout = timeout
        self._targets = []

    def add_target(self, target):
        self._targets.append(target)

    def do(self):
        for target in self._targets:
            target.commit()

    async def _watch(self):
        while True:
            try:
                self.do()
            except Exception:
                # keep committing: an uncaught error would end this task silently
                logger.exception("Commit failed; retrying after the timeout")
            await asyncio.sleep(self._timeout)

    def as_task(self):
        return asyncio.create_task(self._watch())
