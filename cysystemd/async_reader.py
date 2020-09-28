import asyncio
import logging
from collections.abc import AsyncIterator
from functools import partial
from queue import Empty as QueueEmpty
from uuid import UUID

from .reader import JournalEntry, JournalOpenMode, JournalReader


try:
    from queue import SimpleQueue
except ImportError:
    from queue import Queue as SimpleQueue


log = logging.getLogger("cysystemd.async_reader")


class Base:
    def __init__(self, loop: asyncio.AbstractEventLoop = None, executor=None):
        self._executor = executor
        self._loop = loop or asyncio.get_event_loop()

    async def _exec(self, func, *args, **kwargs):
        # noinspection PyTypeChecker
        return await self._loop.run_in_executor(
            self._executor, partial(func, *args, **kwargs)
        )


class AsyncJournalReader(Base):
    def __init__(self, executor=None, loop: asyncio.AbstractEventLoop = None):
        super().__init__(loop=loop, executor=executor)
        self.__reader = JournalReader()
        self.__flags = None
        self.__wait_lock = asyncio.Lock()

    async def wait(self) -> bool:
        async with self.__wait_lock:
            loop = self._loop
            reader = self.__reader
            event = asyncio.Event()

            loop.add_reader(reader.fd, event.set)

            try:
                await event.wait()
            finally:
                loop.remove_reader(reader.fd)

            reader.process_events()

        return True

    async def open(self, flags=JournalOpenMode.CURRENT_USER):
        self.__flags = flags
        return await self._exec(self.__reader.open, flags=flags)

    async def open_directory(self, path):
        return await self._exec(self.__reader.open_directory, path)

    async def open_files(self, *file_names):
        return await self._exec(self.__reader.open_files, *file_names)

    @property
    def data_threshold(self):
        return self.__reader.data_threshold

    @data_threshold.setter
    def data_threshold(self, size):
        self.__reader.data_threshold = size

    @property
    def closed(self) -> bool:
        return self.__reader.closed

    @property
    def locked(self) -> bool:
        return self.__reader.locked

    @property
    def idle(self) -> bool:
        return self.__reader.idle

    async def seek_head(self):
        return await self._exec(self.__reader.seek_head)

    def __repr__(self):
        return "<%s[%s]: %s>" % (
            self.__class__.__name__,
            self.__flags,
            "closed" if self.closed else "opened",
        )

    @property
    def fd(self):
        return self.__reader.fd

    @property
    def events(self):
        return self.__reader.events

    @property
    def timeout(self):
        return self.__reader.timeout

    async def get_catalog(self):
        return await self._exec(self.__reader.get_catalog)

    async def get_catalog_for_message_id(self, message_id):
        return await self._exec(
            self.__reader.get_catalog_for_message_id, message_id
        )

    async def seek_tail(self):
        return await self._exec(self.__reader.seek_tail)

    async def seek_monotonic_usec(self, boot_id: UUID, usec):
        return await self._exec(
            self.__reader.seek_monotonic_usec, boot_id, usec
        )

    async def seek_realtime_usec(self, usec):
        return await self._exec(self.__reader.seek_realtime_usec, usec)

    async def seek_cursor(self, cursor):
        return await self._exec(self.__reader.seek_cursor, cursor)

    async def skip_next(self, skip):
        return await self._exec(self.__reader.skip_next, skip)

    async def previous(self, skip=0):
        return await self._exec(self.__reader.previous, skip)

    async def skip_previous(self, skip):
        return await self._exec(self.__reader.skip_previous, skip)

    async def add_filter(self, rule):
        return await self._exec(self.__reader.add_filter, rule)

    async def clear_filter(self):
        return await self._exec(self.__reader.clear_filter)

    async def __aiter__(self):
        def read_entries():
            for item in self.__reader:
                asyncio.run_coroutine_threadsafe(queue.put(item), self._loop)

            asyncio.run_coroutine_threadsafe(queue.put(None), self._loop)

        queue = asyncio.Queue(1024)
        self._loop.run_in_executor(self._executor, read_entries)
        while True:
            item = await queue.get()
            if item is None:
                break

            yield item

    async def next(self, skip=0):
        return await self._exec(self.__reader.next, skip)
