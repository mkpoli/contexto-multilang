from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter

from alive_progress import alive_bar


def format_seconds(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.2f} s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:.2f}s"


@contextmanager
def timed_step(label: str, timings: dict[str, float]):
    print(f"[{label}] start")
    start = perf_counter()
    try:
        yield
    finally:
        elapsed = perf_counter() - start
        timings[label] = elapsed
        print(f"[{label}] done in {format_seconds(elapsed)}")


def iter_progress(iterable, *, total: int | None, title: str):
    with alive_bar(total, title=title) as bar:
        for item in iterable:
            yield item
            bar()


@contextmanager
def byte_progress(*, total: int | None, title: str):
    with alive_bar(total, title=title) as bar:
        yield bar
