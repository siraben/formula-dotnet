"""Port of Src/CommandLine/TaskManager.cs.

Manages asynchronous query / apply / solve tasks.
"""

from __future__ import annotations

import gc
from datetime import datetime, timedelta
from enum import IntEnum, auto
from typing import Any, Dict, List, Optional, Tuple


class TaskKind(IntEnum):
    Query = 0
    Apply = auto()
    Solve = auto()
    Unknown = auto()


class TaskData:
    """Internal record for a single managed task."""

    def __init__(
        self,
        task_id: int,
        kind: TaskKind,
        task: Any,
        result: Any = None,
        statistics: Any = None,
        canceller: Any = None,
    ) -> None:
        self.id = task_id
        self.kind = kind
        self.task = task
        self.result = result
        self.statistics = statistics
        self.canceller = canceller
        self.start_time: datetime = datetime.now()

    @property
    def duration(self) -> timedelta:
        return datetime.now() - self.start_time

    @property
    def status(self) -> str:
        """Return 'Done' if the task has completed, 'Running' otherwise."""
        if self.task is None:
            return "Done"
        return "Running"

    @property
    def result_summary(self) -> str:
        """Return a string summary of the result."""
        if self.result is None:
            return "?"
        if isinstance(self.result, bool):
            return "true" if self.result else "false"
        return str(self.result)


class TaskManager:
    """Manages a collection of asynchronous tasks.

    The ``is_wait_on`` property controls whether newly started tasks
    should block until completion (synchronous mode).
    """

    # Column names for the task table
    _TABLE_COLS = ("Id", "Kind", "Status", "Result", "Started", "Duration")

    def __init__(self) -> None:
        self._tasks: Dict[int, TaskData] = {}
        self._next_id: int = 0
        self._is_wait_on: bool = False

    # -- properties ----------------------------------------------------

    @property
    def is_wait_on(self) -> bool:
        return self._is_wait_on

    @is_wait_on.setter
    def is_wait_on(self, value: bool) -> None:
        self._is_wait_on = value

    # -- task lookup ---------------------------------------------------

    def try_get_task(self, task_id: int) -> Optional[Tuple[Any, TaskKind]]:
        """Return ``(task, kind)`` or ``None`` when *task_id* is unknown."""
        data = self._tasks.get(task_id)
        if data is None:
            return None
        return data.task, data.kind

    def try_get_statistics(self, task_id: int) -> Optional[Any]:
        data = self._tasks.get(task_id)
        if data is None:
            return None
        return data.statistics

    # -- task lifecycle ------------------------------------------------

    def unload_tasks(self) -> int:
        """Remove all tasks.  Returns the number of tasks removed."""
        count = len(self._tasks)
        self._tasks.clear()
        self._next_id = 0
        gc.collect()
        return count

    def try_unload_task(self, task_id: int) -> bool:
        if task_id not in self._tasks:
            return False
        del self._tasks[task_id]
        gc.collect()
        return True

    def start_task(
        self,
        kind: TaskKind,
        task: Any,
        result: Any = None,
        statistics: Any = None,
        canceller: Any = None,
    ) -> int:
        """Register and start a task.  Returns the assigned task id."""
        task_id = self._next_id
        self._next_id += 1
        data = TaskData(task_id, kind, task, result, statistics, canceller)
        self._tasks[task_id] = data
        return task_id

    # -- display -------------------------------------------------------

    def make_task_table(self) -> Tuple[List[List[str]], List[int]]:
        """Build a printable task table.

        Returns ``(rows, col_widths)`` where *rows* is a list of
        string-lists (first row is the header).
        """
        header = list(self._TABLE_COLS)
        col_widths = [len(h) for h in header]
        rows: List[List[str]] = [header]

        for data in self._tasks.values():
            row = [
                str(data.id),
                data.kind.name,
                data.status,
                data.result_summary,
                data.start_time.strftime("%Y-%m-%d %H:%M"),
                f"{data.duration.total_seconds():.2f}s",
            ]
            for j, cell in enumerate(row):
                col_widths[j] = max(col_widths[j], len(cell))
            rows.append(row)

        return rows, col_widths
