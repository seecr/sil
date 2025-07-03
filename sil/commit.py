import asyncio


class Commit:
    def __init__(self, lucene, timeout=10):
        self._timeout = timeout
        self._lucene = lucene

    async def watch(self):
        while True:
            self._lucene.commit()
            await asyncio.sleep(self._timeout)
