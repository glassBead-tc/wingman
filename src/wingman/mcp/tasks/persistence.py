"""Task persistence for durability."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from wingman.mcp.tasks.state import Task

# Use orjson if available via lib/oj.py pattern
try:
    from lib.oj import loads, dumps
except ImportError:
    import json

    def loads(data: bytes | str) -> Any:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data)

    def dumps(obj: Any) -> bytes:
        return json.dumps(obj).encode("utf-8")


logger = logging.getLogger(__name__)


class TaskPersistence:
    """
    Persist tasks to disk for durability.

    Enables tasks to survive process restarts. Uses JSON files
    in a designated storage directory.
    """

    def __init__(self, storage_dir: Path):
        """
        Initialize task persistence.

        Args:
            storage_dir: Directory to store task files.
        """
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Task persistence initialized at {storage_dir}")

    def _task_path(self, task_id: str) -> Path:
        """Get path for task file."""
        return self.storage_dir / f"{task_id}.json"

    def save_task(self, task: Task) -> None:
        """
        Save task to disk.

        Args:
            task: Task to save.
        """
        path = self._task_path(task.id)
        data = dumps(task.to_dict())
        path.write_bytes(data)
        logger.debug(f"Saved task {task.id} to {path}")

    def load_task(self, task_id: str) -> Task | None:
        """
        Load task from disk.

        Args:
            task_id: ID of task to load.

        Returns:
            Task if found, None otherwise.
        """
        path = self._task_path(task_id)
        if not path.exists():
            return None

        try:
            data = loads(path.read_bytes())
            task = Task.from_dict(data)
            logger.debug(f"Loaded task {task_id} from {path}")
            return task
        except Exception as e:
            logger.error(f"Error loading task {task_id}: {e}")
            return None

    def load_all_tasks(self) -> list[Task]:
        """
        Load all tasks from disk.

        Returns:
            List of all persisted tasks.
        """
        tasks: list[Task] = []
        for path in self.storage_dir.glob("*.json"):
            try:
                data = loads(path.read_bytes())
                task = Task.from_dict(data)
                tasks.append(task)
            except Exception as e:
                logger.error(f"Error loading task from {path}: {e}")

        logger.debug(f"Loaded {len(tasks)} tasks from {self.storage_dir}")
        return tasks

    def delete_task(self, task_id: str) -> bool:
        """
        Delete task from disk.

        Args:
            task_id: ID of task to delete.

        Returns:
            True if deleted, False if not found.
        """
        path = self._task_path(task_id)
        if path.exists():
            path.unlink()
            logger.debug(f"Deleted task {task_id}")
            return True
        return False

    def cleanup_terminal_tasks(self, max_age_seconds: float) -> int:
        """
        Delete old terminal tasks.

        Args:
            max_age_seconds: Maximum age in seconds.

        Returns:
            Number of tasks deleted.
        """
        import time

        deleted = 0
        now = time.time()

        for path in self.storage_dir.glob("*.json"):
            try:
                # Check file age first (cheaper than parsing)
                if (now - path.stat().st_mtime) < max_age_seconds:
                    continue

                data = loads(path.read_bytes())
                task = Task.from_dict(data)

                if task.is_terminal:
                    path.unlink()
                    deleted += 1
            except Exception as e:
                logger.error(f"Error checking task {path}: {e}")

        if deleted:
            logger.info(f"Cleaned up {deleted} old terminal tasks")

        return deleted

    def get_stats(self) -> dict[str, Any]:
        """Get persistence statistics."""
        task_files = list(self.storage_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in task_files)

        return {
            "storage_dir": str(self.storage_dir),
            "task_count": len(task_files),
            "total_size_bytes": total_size,
        }


class PersistentTaskManager:
    """
    Task manager with automatic persistence.

    Wraps TaskManager with persistence hooks to save/load tasks.
    """

    def __init__(
        self,
        manager: "TaskManager",  # type: ignore
        persistence: TaskPersistence,
    ):
        """
        Initialize persistent task manager.

        Args:
            manager: TaskManager to wrap.
            persistence: TaskPersistence for storage.
        """
        from wingman.mcp.tasks.manager import TaskManager
        from wingman.mcp.tasks.state import TaskState

        self.manager: TaskManager = manager
        self.persistence = persistence

        # Hook into state changes for persistence
        original_callback = manager._on_state_change

        async def persist_on_change(
            task: Task, old_state: TaskState, new_state: TaskState
        ) -> None:
            # Save task on every state change
            self.persistence.save_task(task)

            # Call original callback if any
            if original_callback:
                await original_callback(task, old_state, new_state)

        manager._on_state_change = persist_on_change

    async def restore_tasks(self) -> int:
        """
        Restore persisted tasks into manager.

        Returns:
            Number of tasks restored.
        """
        tasks = self.persistence.load_all_tasks()

        restored = 0
        for task in tasks:
            # Only restore non-terminal tasks
            if task.is_active:
                self.manager._tasks[task.id] = task
                restored += 1
                logger.info(
                    f"Restored task {task.id} (state={task.state.value})"
                )

        return restored

    async def cleanup(self, max_age_seconds: float = 86400.0) -> int:
        """
        Clean up old persisted tasks.

        Args:
            max_age_seconds: Maximum age (default 24 hours).

        Returns:
            Number of tasks cleaned up.
        """
        return self.persistence.cleanup_terminal_tasks(max_age_seconds)
