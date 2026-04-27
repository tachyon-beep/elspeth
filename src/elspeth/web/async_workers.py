"""Async helpers for running bounded synchronous work off the event loop."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor


async def run_sync_in_worker[**P, T](func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Run synchronous work in a one-call worker without blocking the loop.

    The short wait loop keeps an explicit event-loop timer active while the
    worker runs.  This preserves the normal async-over-sync contract even in
    sandboxed runtimes where executor completion can fail to wake the selector
    promptly.
    """
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    future = loop.run_in_executor(executor, functools.partial(func, *args, **kwargs))
    try:
        while True:
            try:
                return await asyncio.wait_for(asyncio.shield(future), timeout=0.1)
            except TimeoutError:
                continue
    finally:
        executor.shutdown(wait=future.done(), cancel_futures=True)
