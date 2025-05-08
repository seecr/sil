import asyncio


class Commit:
    def __init__(self, writer, period=10):
        self._period = period
        self._writer = writer

    async def watch(self):
        while True:
            if self._writer.hasUncommittedChanges():
                print("Committing changes for", self._writer)
                if self._writer.isOpen():
                    self._writer.commit()
            await asyncio.sleep(self._period)
