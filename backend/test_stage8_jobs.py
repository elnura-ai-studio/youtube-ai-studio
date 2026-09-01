"""Бесплатные локальные тесты Этапа 8: job status, retry, lock, изоляция."""

import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pipeline  # noqa: E402
import jobs  # noqa: E402


def check(condition, message):
    if not condition:
        raise AssertionError(message)


class MockPipeline:
    """Раннеры-заглушки: никакой реальный API не вызывается."""

    def __init__(self, fail_stage=None, retryable=True):
        self.fail_stage = fail_stage
        self.retryable = retryable
        self.calls = []

    def runners(self):
        return {name: self._make(name) for name in jobs.STAGE_ORDER}

    def _make(self, name):
        def runner(channel_id):
            self.calls.append((channel_id, name))
            if name == self.fail_stage:
                raise pipeline.PipelineError(
                    f"сбой на {name}", stage=name, retryable=self.retryable, details="mock"
                )
            self._produce(channel_id, name)
        return runner

    def _produce(self, channel_id, name):
        if name == "character_identity":
            pipeline.write_json(pipeline.character_bible_path(channel_id), {"style": "s", "characters": [{"name": "A"}]})
            pipeline.character_ref_path(channel_id).write_bytes(b"REF")
        elif name == "scene_script":
            pipeline.write_json(pipeline.scene_script_path(channel_id), {"scenes": [{"scene_id": 1}]})
        elif name == "voice_plan":
            pipeline.write_json(pipeline.voice_plan_path(channel_id), {"items": [
                {"scene_id": 1, "line_id": 1, "audio_path": "audio/scene_001_line_001.mp3"}]})
        elif name == "audio_clips":
            pipeline.run_path(channel_id, "audio", "scene_001_line_001.mp3").write_bytes(b"A")
        elif name == "timeline":
            pipeline.write_json(pipeline.timeline_path(channel_id), {"scenes": [{"scene_id": 1, "scene_duration": 2}]})
        elif name == "video_plan":
            pipeline.write_json(pipeline.video_plan_path(channel_id), {"provider": "mock", "scenes": [
                {"scene_id": 1, "video_path": "video/scene_001.mp4"}]})
        elif name == "scene_videos":
            pipeline.run_path(channel_id, "video", "scene_001.mp4").write_bytes(b"V")
        elif name == "final_video":
            pipeline.final_video_path(channel_id).write_bytes(b"F")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        pipeline.RUNS_DIR = Path(tmp) / "runs"
        a, b = "UC_A", "UC_B"

        # 1. Нормальный проход всех стадий
        mock = MockPipeline()
        job = jobs.run_autopilot_pipeline(a, mock.runners())
        check(job["status"] == jobs.STATUS_COMPLETED, f"status {job['status']}")
        check(job["progress"] == 100 and job["completed_stages"] == list(jobs.STAGE_ORDER), "не все стадии")
        check(len(mock.calls) == len(jobs.STAGE_ORDER), "стадии вызваны не по одному разу")
        check(job["last_error"] is None and job["job_id"], "лишняя ошибка/нет job_id")

        # 2. Успешные стадии не повторяются
        mock2 = MockPipeline()
        job2 = jobs.run_autopilot_pipeline(a, mock2.runners())
        check(mock2.calls == [], "готовые стадии выполнены повторно (трата кредитов)")
        check(job2["status"] == jobs.STATUS_COMPLETED, "повторный прогон не completed")

        # 3. Изоляция каналов
        check(jobs.load_job_status(b)["status"] == jobs.STATUS_IDLE, "job канала B не изолирован")
        check(not pipeline.final_video_path(b).exists(), "артефакты утекли в канал B")

        # 4. Падение стадии => status=failed с явной ошибкой
        failing = MockPipeline(fail_stage="timeline")
        job3 = jobs.run_autopilot_pipeline(b, failing.runners())
        check(job3["status"] == jobs.STATUS_FAILED, "падение не отражено")
        error = job3["last_error"]
        check(error["stage"] == "timeline" and error["retryable"] is True, "ошибка без stage/retryable")
        check(error["timestamp"] and error["technical_details"] == "mock", "нет timestamp/деталей")
        check(job3["completed_stages"] == ["character_identity", "scene_script", "voice_plan", "audio_clips"],
              "pipeline продолжился после ошибки")
        done_before = len(job3["completed_stages"])

        # 5. Retry продолжает с упавшей стадии
        fixed = MockPipeline()
        job4 = jobs.retry_failed_stage(b, fixed.runners())
        check(job4["status"] == jobs.STATUS_COMPLETED, "retry не завершил job")
        retried = [name for _, name in fixed.calls]
        check(retried == list(jobs.STAGE_ORDER[done_before:]), f"retry начал не с той стадии: {retried}")

        # 6. Не-retryable ошибка не перезапускается
        c = "UC_C"
        hard = MockPipeline(fail_stage="scene_script", retryable=False)
        job5 = jobs.run_autopilot_pipeline(c, hard.runners())
        check(job5["retryable"] is False, "не-retryable помечен как retryable")
        try:
            jobs.retry_failed_stage(c, MockPipeline().runners())
            raise AssertionError("не-retryable этап всё же перезапущен")
        except pipeline.PipelineError:
            pass

        # 7. Лимит повторов
        d = "UC_D"
        status = jobs.load_job_status(d)
        status.update({"job_id": "x", "status": jobs.STATUS_FAILED, "retry_counts": {"timeline": jobs.MAX_RETRIES},
                       "last_error": {"stage": "timeline", "message": "e", "timestamp": "t", "retryable": True}})
        jobs.save_job_status(d, status)
        try:
            jobs.retry_failed_stage(d, MockPipeline().runners())
            raise AssertionError("бесконечные retry не ограничены")
        except pipeline.PipelineError as err:
            check("лимит" in str(err), f"неверная ошибка лимита: {err}")

        # 8. Missing input останавливает pipeline понятной ошибкой
        e = "UC_E"
        broken = MockPipeline().runners()
        broken["scene_script"] = lambda channel_id: None  # ничего не создаёт
        job6 = jobs.run_autopilot_pipeline(e, broken)
        check(job6["status"] == jobs.STATUS_FAILED and job6["last_error"]["stage"] == "scene_script", "нет ошибки входа")
        try:
            jobs.validate_stage_inputs("UC_EMPTY", "timeline")
            raise AssertionError("валидация пропустила отсутствующие входы")
        except pipeline.PipelineError as err:
            check("scene_script.json" in str(err), f"невнятная ошибка: {err}")

        # 9. Lock: второй параллельный запуск того же канала блокируется,
        #    другой канал при этом выполняется свободно
        f, g = "UC_F", "UC_G"
        started, release, results = threading.Event(), threading.Event(), {}

        def slow_runner(channel_id):
            started.set()
            release.wait(5)
            MockPipeline()._produce(channel_id, "character_identity")

        slow = MockPipeline().runners()
        slow["character_identity"] = slow_runner
        worker = threading.Thread(target=lambda: jobs.run_autopilot_pipeline(f, slow))
        worker.start()
        started.wait(5)
        try:
            jobs.run_autopilot_pipeline(f, MockPipeline().runners())
            results["locked"] = False
        except jobs.JobLockedError:
            results["locked"] = True
        other = jobs.run_autopilot_pipeline(g, MockPipeline().runners())
        release.set()
        worker.join(10)
        check(results["locked"] is True, "lock не заблокировал второй запуск канала")
        check(other["status"] == jobs.STATUS_COMPLETED, "другой канал не смог работать параллельно")
        check(not jobs.lock_path(f).exists(), "lock не снят после завершения")
        check(jobs.load_job_status(f)["status"] == jobs.STATUS_COMPLETED, "первый запуск не завершился")

    print("OK: stage 8 reliability checks passed")


if __name__ == "__main__":
    main()
