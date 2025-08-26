import asyncio


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
            self.do()
            await asyncio.sleep(self._timeout)

    def as_task(self):
        return asyncio.create_task(self._watch())
