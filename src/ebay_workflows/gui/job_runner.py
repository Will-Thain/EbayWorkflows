from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QProcess, Signal

from ..cli_launch import project_root, resolve_cli_launch
from .workflow_catalog import WORKFLOW_JOBS, build_argv


class JobRunner(QObject):
    log_line = Signal(str)
    job_started = Signal(str)
    job_finished = Signal(int, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._current_job_id: str | None = None

    def is_busy(self) -> bool:
        return self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning

    @property
    def current_job_id(self) -> str | None:
        if not self.is_busy():
            return None
        return self._current_job_id

    def start(self, job_id: str, params: dict[str, Any] | None = None) -> None:
        if self.is_busy():
            raise RuntimeError("A workflow job is already running.")

        argv = build_argv(job_id, params)
        program, args = resolve_cli_launch(argv)

        process = QProcess(self)
        process.setWorkingDirectory(str(project_root()))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._on_output)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)

        self._process = process
        self._current_job_id = job_id
        self.log_line.emit(f"--- Starting {job_id}: {program} {' '.join(args)} ---")
        process.start(program, args)
        if not process.waitForStarted(10_000):
            self._process = None
            self._current_job_id = None
            raise RuntimeError(f"Failed to start process: {process.errorString()}")
        self.job_started.emit(job_id)

    def stop(self) -> None:
        if not self.is_busy() or self._process is None:
            return
        self.log_line.emit("--- Stop requested ---")
        self._process.terminate()
        if not self._process.waitForFinished(10_000):
            self._process.kill()
            self._process.waitForFinished(5_000)

    def _on_output(self) -> None:
        if self._process is None:
            return
        data = self._process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        for line in data.splitlines():
            if line.strip():
                self.log_line.emit(line)

    def _on_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        job_id = self._current_job_id or "job"
        self.log_line.emit(f"--- Finished {job_id} (exit {exit_code}) ---")
        self.job_finished.emit(exit_code, job_id)
        self._process = None
        self._current_job_id = None

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.log_line.emit("--- Process failed to start ---")
