"""Application registry handling launch/focus semantics."""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from agent.platform.windows import window_manager
from agent.schemas.config import AppConfigSchema, AppRegistrySchema

LOGGER = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_instance_id() -> str:
    return os.urandom(8).hex()


@dataclass
class ApplicationDefinition:
    name: str
    config: AppConfigSchema

    def require_enabled(self) -> None:
        if not self.config.enabled:
            raise RuntimeError(f"Application '{self.name}' is disabled by policy.")

    def build_launch_plan(
        self,
        *,
        preset: str | None = None,
        extra_args: Iterable[str] | None = None,
        env_overrides: Optional[Mapping[str, str]] = None,
        inherit_env: Optional[bool] = None,
        working_dir: Optional[str] = None,
    ) -> tuple[Sequence[str] | str, Mapping[str, str], bool, Optional[str]]:
        if not any([self.config.path, self.config.shell]):
            raise NotImplementedError(
                "Only path and shell launch vectors are supported by the local runner."
            )

        args = list(self.config.args)
        if preset:
            args.extend(self.config.presets.get(preset, []))
        if extra_args:
            args.extend(extra_args)

        cwd = working_dir or self.config.working_dir
        inherit = self.config.inherit_env if inherit_env is None else inherit_env
        env: Dict[str, str] = {}
        if inherit:
            env.update(os.environ)
        env.update(self.config.env)
        if env_overrides:
            env.update(env_overrides)

        if self.config.path:
            command: Sequence[str] | str = [self.config.path, *args]
            use_shell = False
        else:
            shell_cmd = self.config.shell or ""
            command = shell_cmd if not args else f"{shell_cmd} {shlex.join(args)}"
            use_shell = True

        return command, env, use_shell, cwd


@dataclass
class WindowRecord:
    hwnd: int
    title: str
    class_name: str
    bounds: tuple[int, int, int, int]
    is_visible: bool
    is_minimized: bool
    process_name: str
    pid: int
    last_seen: datetime


@dataclass
class ApplicationProcess:
    definition: ApplicationDefinition
    process: subprocess.Popen[str] | None
    preset: Optional[str] = None
    started_at: datetime = field(default_factory=_utcnow)
    last_focused_at: Optional[datetime] = None
    instance_id: str = field(default_factory=_make_instance_id)
    pid: int | None = None
    windows: Dict[int, WindowRecord] = field(default_factory=dict)

    def has_live_process(self) -> bool:
        return bool(self.process and self.process.poll() is None)

    def has_live_window(self) -> bool:
        return any(window_manager.is_window(hwnd) for hwnd in self.windows)


class ApplicationRegistry:
    def __init__(self, apps: Dict[str, AppConfigSchema], *, wm=window_manager):
        self._apps = {name: ApplicationDefinition(name, cfg) for name, cfg in apps.items()}
        self._running: Dict[str, List[ApplicationProcess]] = {}
        self._instances: Dict[str, ApplicationProcess] = {}
        self._window_manager = wm

    def get(self, name: str) -> ApplicationDefinition:
        if name not in self._apps:
            raise KeyError(f"Application '{name}' is not registered.")
        return self._apps[name]

    def start(
        self,
        name: str,
        *,
        preset: str | None = None,
        args: Iterable[str] | None = None,
        env: Mapping[str, str] | None = None,
        inherit_env: Optional[bool] = None,
        working_dir: Optional[str] = None,
    ) -> ApplicationProcess:
        definition = self.get(name)
        definition.require_enabled()
        self._purge_stopped(name)
        self._remove_inactive_records(name)

        policy = definition.config.window.single_instance
        running = self._running.get(name, [])
        if policy == "detect" and running:
            raise RuntimeError(f"Application '{name}' is already running (single_instance=detect).")
        if policy == "force" and running:
            LOGGER.info("single_instance=force - terminating existing %s instances", name)
            for process in list(running):
                self._force_kill(process)
            self._purge_stopped(name)

        command, env_vars, use_shell, cwd = definition.build_launch_plan(
            preset=preset,
            extra_args=args,
            env_overrides=env,
            inherit_env=inherit_env,
            working_dir=working_dir,
        )

        LOGGER.info("Launching app %s with command %s", name, command)
        process: subprocess.Popen[str] | None = subprocess.Popen(
            command,
            shell=use_shell,
            cwd=cwd or None,
            env=dict(env_vars),
            text=True,
        )

        record = ApplicationProcess(definition=definition, process=process, preset=preset, pid=process.pid)
        self._update_windows(record, require_visible=True)
        if record.windows:
            record.pid = next(iter(record.windows.values())).pid
        else:
            LOGGER.debug("No window detected for %s immediately after launch", name)
        self._running.setdefault(name, []).append(record)
        self._instances[record.instance_id] = record
        return record

    def focus(self, name: str, *, target: str | int | None = "latest") -> ApplicationProcess:
        record = self._ensure_running_record(name, target)
        hwnd = self._primary_window(record)
        if hwnd:
            self._window_manager.bring_to_foreground(hwnd)
        record.last_focused_at = _utcnow()
        LOGGER.info("Focused app %s (pid=%s)", name, record.pid)
        return record

    def minimize(self, name: str, *, target: str | int | None = "latest") -> ApplicationProcess:
        record = self._ensure_running_record(name, target)
        hwnd = self._primary_window(record)
        if hwnd:
            self._window_manager.show_window(hwnd, "minimize")
        LOGGER.info("Minimize requested for %s (pid=%s)", name, record.pid)
        return record

    def maximize(self, name: str, *, target: str | int | None = "latest") -> ApplicationProcess:
        record = self._ensure_running_record(name, target)
        hwnd = self._primary_window(record)
        if hwnd:
            self._window_manager.show_window(hwnd, "maximize")
        LOGGER.info("Maximize requested for %s (pid=%s)", name, record.pid)
        return record

    def restore(self, name: str, *, target: str | int | None = "latest") -> ApplicationProcess:
        record = self._ensure_running_record(name, target)
        hwnd = self._primary_window(record)
        if hwnd:
            self._window_manager.show_window(hwnd, "restore")
        LOGGER.info("Restore requested for %s (pid=%s)", name, record.pid)
        return record

    def close(
        self,
        name: str,
        *,
        timeout: float = 5.0,
        force: bool = False,
        all_instances: bool = False,
    ) -> None:
        records = self._select_records(name, all_instances=all_instances)
        if not records:
            raise RuntimeError(f"Application '{name}' is not running.")
        for record in records:
            if record.process and record.process.poll() is None:
                record.process.terminate()
                try:
                    record.process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    if force:
                        self._force_kill(record)
            for hwnd in list(record.windows):
                self._window_manager.close_window(hwnd)
            record.windows.clear()
        self._purge_stopped(name)

    def kill(self, name: str, *, all_instances: bool = False) -> None:
        records = self._select_records(name, all_instances=all_instances)
        if not records:
            raise RuntimeError(f"Application '{name}' is not running.")
        for record in records:
            self._force_kill(record)
        self._purge_stopped(name)

    def is_running(self, name: str) -> bool:
        self._purge_stopped(name)
        return bool(self._running.get(name))

    def running_processes(self, name: str) -> List[ApplicationProcess]:
        self._purge_stopped(name)
        return list(self._running.get(name, []))

    def _force_kill(self, record: ApplicationProcess) -> None:
        if record.process and record.process.poll() is None:
            record.process.kill()
            try:
                record.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                LOGGER.warning("Process %s did not exit after kill().", record.definition.name)
        elif record.pid:
            self._window_manager.terminate_process(record.pid)
        for hwnd in list(record.windows):
            self._window_manager.close_window(hwnd)
            record.windows.pop(hwnd, None)

    def _update_windows(self, record: ApplicationProcess, *, require_visible: bool) -> None:
        snapshots = self._window_manager.snapshot_windows(record.definition)
        now = _utcnow()
        record.windows = {
            snapshot.hwnd: WindowRecord(
                hwnd=snapshot.hwnd,
                title=snapshot.title,
                class_name=snapshot.class_name,
                bounds=snapshot.bounds,
                is_visible=snapshot.is_visible,
                is_minimized=snapshot.is_minimized,
                process_name=snapshot.process_name,
                pid=snapshot.pid,
                last_seen=now,
            )
            for snapshot in snapshots
            if not require_visible or snapshot.is_visible
        }
        if record.windows:
            record.pid = next(iter(record.windows.values())).pid

    def _primary_window(self, record: ApplicationProcess) -> Optional[int]:
        self._update_windows(record, require_visible=False)
        for hwnd, info in record.windows.items():
            if info.is_visible and not info.is_minimized:
                return hwnd
        return next(iter(record.windows), None)

    def _purge_stopped(self, name: str) -> None:
        records = self._running.get(name)
        if not records:
            return
        alive: List[ApplicationProcess] = []
        for record in records:
            self._update_windows(record, require_visible=False)
            has_process = record.has_live_process()
            has_window = bool(record.windows)
            if has_process or has_window:
                alive.append(record)
            else:
                self._instances.pop(record.instance_id, None)
        if alive:
            self._running[name] = alive
        else:
            self._running.pop(name, None)

    def _remove_inactive_records(self, name: str) -> None:
        records = self._running.get(name, [])
        if not records:
            return
        kept: List[ApplicationProcess] = []
        for record in records:
            self._update_windows(record, require_visible=False)
            if record.windows or record.has_live_process():
                kept.append(record)
            else:
                self._instances.pop(record.instance_id, None)
        if kept:
            self._running[name] = kept
        else:
            self._running.pop(name, None)

    def _select_records(
        self,
        name: str,
        *,
        all_instances: bool = False,
    ) -> List[ApplicationProcess]:
        self._purge_stopped(name)
        records = self._running.get(name, [])
        if not records:
            return []
        if all_instances:
            return list(records)
        return [records[-1]]

    def _select_record(
        self,
        name: str,
        target: str | int | None = "latest",
    ) -> Optional[ApplicationProcess]:
        self._purge_stopped(name)
        records = self._running.get(name, [])
        if not records:
            return None
        if target in (None, "latest"):
            return records[-1]
        if target == "first":
            return records[0]
        if isinstance(target, int):
            for record in records:
                if record.pid == target:
                    return record
            return None
        if isinstance(target, str):
            if target.isdigit():
                return self._select_record(name, int(target))
            return self._instances.get(target)
        raise ValueError(f"Unsupported focus target '{target}'.")

    def _ensure_running_record(
        self,
        name: str,
        target: str | int | None,
    ) -> ApplicationProcess:
        record = self._select_record(name, target)
        if record is None:
            raise RuntimeError(f"Application '{name}' is not running.")
        self._update_windows(record, require_visible=False)
        if record.has_live_process() or record.windows:
            return record
        self._purge_stopped(name)
        raise RuntimeError(f"Application '{name}' is not running.")

    @classmethod
    def from_schema(cls, schema: AppRegistrySchema) -> "ApplicationRegistry":
        return cls(schema.root)


__all__ = ["ApplicationRegistry", "ApplicationDefinition", "ApplicationProcess"]
