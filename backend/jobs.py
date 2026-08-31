"""Этап 8: job status, идемпотентность, валидация, lock, retry, orchestration.

Никакой внешней инфраструктуры (Redis/Celery/БД) — состояние лежит рядом с
артефактами канала: runs/<channel_key>/job_status.json и job.lock.
Существующие функции этапов 1-7 не переписываются: этот модуль только вызывает
их через реестр stage-раннеров.
"""

from __future__ import annotations

import contextlib
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pipeline import (
    PipelineError,
    character_bible_path,
    character_ref_path,
    channel_run_dir,
    final_video_path,
    read_json,
    run_path,
    scene_script_path,
    timeline_path,
    video_plan_path,
    voice_plan_path,
    write_json,
)

MAX_RETRIES = 3
LOCK_STALE_SECONDS = 3600

STATUS_IDLE = "idle"
STATUS_RUNNING = "running"
STATUS_FAILED = "failed"
STATUS_COMPLETED = "completed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_status_path(channel_id: str) -> Path:
    return run_path(channel_id, "job_status.json")


def lock_path(channel_id: str) -> Path:
    return run_path(channel_id, "job.lock")


# --------------------------------------------------------------------------
# Валидация входов и готовых выходов каждого этапа
# --------------------------------------------------------------------------

def _non_empty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _audio_clips_ready(channel_id: str) -> bool:
    plan = read_json(voice_plan_path(channel_id))
    if not isinstance(plan, dict) or not plan.get("items"):
        return False
    return all(
        _non_empty(run_path(channel_id, *item["audio_path"].split("/"), create_parent=False))
        for item in plan["items"]
    )


def _scene_videos_ready(channel_id: str) -> bool:
    plan = read_json(video_plan_path(channel_id))
    if not isinstance(plan, dict) or not plan.get("scenes"):
        return False
    return all(
        _non_empty(run_path(channel_id, *scene["video_path"].split("/"), create_parent=False))
        for scene in plan["scenes"]
    )


def _character_ready(channel_id: str) -> bool:
    return _non_empty(character_bible_path(channel_id)) and _non_empty(character_ref_path(channel_id))


STAGES = (
    {
        "name": "character_identity",
        "requires": (),
        "is_done": _character_ready,
        "inputs": lambda channel_id: [],
    },
    {
        "name": "scene_script",
        "requires": ("character_identity",),
        "is_done": lambda channel_id: _non_empty(scene_script_path(channel_id)),
        "inputs": lambda channel_id: [character_bible_path(channel_id)],
    },
    {
        "name": "voice_plan",
        "requires": ("scene_script",),
        "is_done": lambda channel_id: _non_empty(voice_plan_path(channel_id)),
        "inputs": lambda channel_id: [scene_script_path(channel_id)],
    },
    {
        "name": "audio_clips",
        "requires": ("voice_plan",),
        "is_done": _audio_clips_ready,
        "inputs": lambda channel_id: [voice_plan_path(channel_id)],
    },
    {
        "name": "timeline",
        "requires": ("audio_clips",),
        "is_done": lambda channel_id: _non_empty(timeline_path(channel_id)),
        "inputs": lambda channel_id: [scene_script_path(channel_id), voice_plan_path(channel_id)],
    },
    {
        "name": "video_plan",
        "requires": ("timeline",),
        "is_done": lambda channel_id: _non_empty(video_plan_path(channel_id)),
        "inputs": lambda channel_id: [timeline_path(channel_id), scene_script_path(channel_id)],
    },
    {
        "name": "scene_videos",
        "requires": ("video_plan",),
        "is_done": _scene_videos_ready,
        "inputs": lambda channel_id: [video_plan_path(channel_id)],
    },
    {
        "name": "final_video",
        "requires": ("scene_videos",),
        "is_done": lambda channel_id: _non_empty(final_video_path(channel_id)),
        "inputs": lambda channel_id: [timeline_path(channel_id), video_plan_path(channel_id)],
    },
)

STAGE_ORDER = tuple(stage["name"] for stage in STAGES)
STAGE_BY_NAME = {stage["name"]: stage for stage in STAGES}


def validate_stage_inputs(channel_id: str, stage_name: str) -> None:
    stage = STAGE_BY_NAME[stage_name]
    missing = [path.name for path in stage["inputs"](channel_id) if not _non_empty(path)]
    if missing:
        raise PipelineError(
            f"Этап {stage_name} не может стартовать: отсутствуют входные данные: {', '.join(missing)}.",
            stage=stage_name,
            retryable=False,
        )


# --------------------------------------------------------------------------
# Job status
# --------------------------------------------------------------------------

def load_job_status(channel_id: str) -> dict:
    status = read_json(job_status_path(channel_id))
    if isinstance(status, dict) and status.get("job_id"):
        return status
    return {
        "channel_id": channel_id,
        "job_id": "",
        "status": STATUS_IDLE,
        "current_stage": None,
        "progress": 0,
        "created_at": None,
        "updated_at": None,
        "last_error": None,
        "retryable": False,
        "completed_stages": [],
        "retry_counts": {},
    }


def save_job_status(channel_id: str, status: dict) -> dict:
    status["updated_at"] = _now()
    write_json(job_status_path(channel_id), status)
    return status


def _progress(completed: list) -> int:
    return int(round(100 * len(completed) / len(STAGE_ORDER)))


def _start_job(channel_id: str, status: dict) -> dict:
    if not status.get("job_id") or status.get("status") == STATUS_COMPLETED:
        status["job_id"] = uuid.uuid4().hex
        status["created_at"] = _now()
    status["channel_id"] = channel_id
    status["status"] = STATUS_RUNNING
    status["last_error"] = None
    status["retryable"] = False
    return save_job_status(channel_id, status)


def _fail_job(channel_id: str, status: dict, stage_name: str, error: Exception) -> dict:
    retryable = getattr(error, "retryable", True)
    status["status"] = STATUS_FAILED
    status["current_stage"] = stage_name
    status["retryable"] = bool(retryable)
    status["last_error"] = {
        "stage": stage_name,
        "message": str(error),
        "timestamp": _now(),
        "retryable": bool(retryable),
        "technical_details": getattr(error, "details", "") or "",
    }
    return save_job_status(channel_id, status)


# --------------------------------------------------------------------------
# Lock: один channel_id — один одновременный pipeline
# --------------------------------------------------------------------------

class JobLockedError(PipelineError):
    pass


@contextlib.contextmanager
def channel_lock(channel_id: str):
    channel_run_dir(channel_id)
    path = lock_path(channel_id)
    if path.exists():
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            age = 0
        if age > LOCK_STALE_SECONDS:
            path.unlink(missing_ok=True)
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise JobLockedError(
            f"Для канала {channel_id} уже выполняется pipeline.",
            stage="lock",
            retryable=True,
        ) from error
    try:
        os.write(handle, f"{os.getpid()} {_now()}".encode())
        os.close(handle)
        yield
    finally:
        path.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def run_autopilot_pipeline(channel_id: str, runners: dict, *, from_stage: str | None = None, force: bool = False) -> dict:
    """Последовательно выполняет этапы 1-7 через переданные раннеры.

    runners: {stage_name: callable(channel_id) -> Any}. Готовые этапы
    пропускаются (кредиты не тратятся), падение останавливает pipeline.
    """
    missing = [name for name in STAGE_ORDER if name not in runners]
    if missing:
        raise PipelineError(
            f"Нет раннеров для этапов: {', '.join(missing)}", stage="orchestration", retryable=False
        )
    if from_stage and from_stage not in STAGE_BY_NAME:
        raise PipelineError(f"Неизвестный этап: {from_stage}", stage="orchestration", retryable=False)

    with channel_lock(channel_id):
        status = _start_job(channel_id, load_job_status(channel_id))
        completed = [name for name in STAGE_ORDER if name in status.get("completed_stages", [])]
        start_index = STAGE_ORDER.index(from_stage) if from_stage else 0

        for index, stage_name in enumerate(STAGE_ORDER):
            stage = STAGE_BY_NAME[stage_name]
            status["current_stage"] = stage_name
            save_job_status(channel_id, status)

            already_done = stage["is_done"](channel_id)
            rerun = force and index >= start_index
            if already_done and not rerun:
                if stage_name not in completed:
                    completed.append(stage_name)
                status["completed_stages"] = completed
                status["progress"] = _progress(completed)
                save_job_status(channel_id, status)
                continue
            if index < start_index and not already_done:
                return _fail_job(
                    channel_id, status, stage_name,
                    PipelineError(
                        f"Этап {stage_name} не выполнен, продолжение с {from_stage} невозможно.",
                        stage=stage_name, retryable=False,
                    ),
                )

            try:
                validate_stage_inputs(channel_id, stage_name)
                runners[stage_name](channel_id)
                if not stage["is_done"](channel_id):
                    raise PipelineError(
                        f"Этап {stage_name} завершился без ожидаемого результата.",
                        stage=stage_name, retryable=True,
                    )
            except Exception as error:  # noqa: BLE001 — ошибка фиксируется в job_status
                return _fail_job(channel_id, status, stage_name, error)

            if stage_name not in completed:
                completed.append(stage_name)
            status["completed_stages"] = completed
            status["progress"] = _progress(completed)
            save_job_status(channel_id, status)

        status["status"] = STATUS_COMPLETED
        status["current_stage"] = None
        status["retryable"] = False
        status["last_error"] = None
        status["progress"] = 100
        return save_job_status(channel_id, status)


def retry_failed_stage(channel_id: str, runners: dict) -> dict:
    """Перезапуск ТОЛЬКО упавшего этапа и всего, что после него."""
    status = load_job_status(channel_id)
    if status["status"] != STATUS_FAILED or not status.get("last_error"):
        raise PipelineError(
            "Нет упавшего этапа для повторного запуска.", stage="orchestration", retryable=False
        )
    stage_name = status["last_error"]["stage"]
    if not status["last_error"].get("retryable", False):
        raise PipelineError(
            f"Этап {stage_name} помечен как не подлежащий повтору: {status['last_error']['message']}",
            stage=stage_name, retryable=False,
        )
    counts = status.get("retry_counts", {})
    attempts = int(counts.get(stage_name, 0)) + 1
    if attempts > MAX_RETRIES:
        raise PipelineError(
            f"Превышен лимит повторов ({MAX_RETRIES}) для этапа {stage_name}.",
            stage=stage_name, retryable=False,
        )
    counts[stage_name] = attempts
    status["retry_counts"] = counts
    save_job_status(channel_id, status)
    return run_autopilot_pipeline(channel_id, runners, from_stage=stage_name)
