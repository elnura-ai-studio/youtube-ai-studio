"""Бесплатные локальные тесты этапов 1-7 (mock, без OpenAI/Flow/YouTube)."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pipeline  # noqa: E402


class FakeStream:
    def __init__(self, calls, voice, text):
        self.calls, self.voice, self.text = calls, voice, text

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def stream_to_file(self, path):
        self.calls.append((self.voice, self.text))
        Path(path).write_bytes(b"AUDIO")


class FakeClient:
    def __init__(self):
        self.calls = []
        speech = type("S", (), {"with_streaming_response": self})()
        self.audio = type("A", (), {"speech": speech})()

    def create(self, **kwargs):
        return FakeStream(self.calls, kwargs["voice"], kwargs["input"])


BIBLE = {
    "style": "3D cartoon",
    "characters": [
        {"name": "Sabrina", "age": "7", "hair": "brown", "clothing": "red dress"},
        {"name": "Unico", "age": "5", "hair_color": "white", "outfit": "blue cape"},
    ],
}


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        pipeline.RUNS_DIR = Path(tmp) / "runs"

        # --- Этап 1: изоляция каналов ---
        a, b = "UC_channel_A", "UC/channel B"
        check(pipeline.channel_run_dir(a) != pipeline.channel_run_dir(b), "каналы делят папку")
        check(".." not in str(pipeline.channel_run_dir("../etc")), "path traversal")

        # --- Этап 2: постоянный эталон и legacy-поля ---
        pipeline.save_character_bible(a, BIBLE)
        pipeline.save_character_bible(a, {"style": "other", "characters": []})
        check(pipeline.load_character_bible(a)["style"] == "3D cartoon", "bible перезаписан")
        check(pipeline.save_character_reference(a, b"REF") is True, "эталон не создан")
        check(pipeline.save_character_reference(a, b"SCENE") is False, "эталон перезаписан")
        check(pipeline.character_ref_path(a).read_bytes() == b"REF", "эталон изменён сценой")
        check(not pipeline.character_ref_path(b).exists(), "эталон утёк в другой канал")
        prompt = pipeline.render_character_bible_prompt(BIBLE)
        for expected in ("brown", "red dress", "white", "blue cape", "IDENTITY LOCK"):
            check(expected in prompt, f"нет {expected} в prompt")

        # --- Этап 3: scene script ---
        roster = pipeline.build_character_roster(BIBLE)
        ids = [item["character_id"] for item in roster]
        check(ids == ["sabrina", "unico", "narrator"], f"roster {ids}")
        raw = {"scenes": [
            {"scene_id": 1, "visual_description": "лес", "action": "идут",
             "lines": [{"speaker_id": "sabrina", "dialogue": "Привет!", "pause_after": 0.2},
                       {"speaker_id": "ghost", "dialogue": "Кто там?"}]},
            {"visual_description": "поляна", "speaker_id": "unico", "dialogue": "Идём", "pause_after": 1},
        ]}
        script = pipeline.normalize_scene_script(raw, roster, channel_id=a, topic="тест")
        pipeline.write_json(pipeline.scene_script_path(a), script)
        check(script["scenes"][0]["lines"][1]["speaker_id"] == "narrator", "выдуманный спикер не заменён")
        check(script["scenes"][1]["scene_id"] == 2, "scene_id не проставлен")
        check(script["scenes"][1]["lines"][0]["speaker_id"] == "unico", "одиночная реплика потеряна")
        check(all(s["scene_title"] and s["character_ids"] for s in script["scenes"]), "нет обязательных полей")

        # --- Этап 4: multi-voice, стабильность и идемпотентность ---
        profiles = pipeline.get_or_create_voice_profiles(a, roster)["profiles"]
        again = pipeline.get_or_create_voice_profiles(a, roster)["profiles"]
        check(profiles == again, "голоса изменились при повторном вызове")
        check(profiles["narrator"]["voice_id"] == pipeline.NARRATOR_VOICE_ID, "narrator без своего голоса")
        voices = [value["voice_id"] for value in profiles.values()]
        check(len(voices) == len(set(voices)), "голоса дублируются")

        plan = pipeline.build_voice_plan(a, script, {"profiles": profiles})
        check(len(plan["items"]) == 3, "неверное число реплик")
        client = FakeClient()
        first = pipeline.synthesize_voice_plan(a, plan, client)
        second = pipeline.synthesize_voice_plan(a, plan, client)
        check(len(first["created"]) == 3 and not second["created"], "повторная озвучка тратит кредиты")
        check(len(second["skipped"]) == 3, "клипы не переиспользованы")

        # --- Этап 5: тайминг ---
        pipeline.probe_audio_duration = lambda path: 2.0
        timeline = pipeline.build_timeline(a, script, plan)
        scene1 = timeline["scenes"][0]
        check(scene1["lines"][0]["end_time_in_scene"] == 2.0, "неверный конец реплики")
        check(scene1["lines"][1]["start_time_in_scene"] == 2.2, "pause_after не учтён")
        check(scene1["scene_duration"] == 5.0, f"scene_duration {scene1['scene_duration']}")
        check(timeline["scenes"][1]["scene_start"] == scene1["scene_end"], "сцены перекрываются")
        try:
            pipeline.probe_audio_duration = _raise_probe
            pipeline.build_timeline(a, script, plan)
            raise AssertionError("битое аудио не вызвало ошибку")
        except pipeline.AudioProbeError:
            pass
        pipeline.probe_audio_duration = lambda path: 2.0
        timeline = pipeline.build_timeline(a, script, plan)

        # --- Этап 6: video plan ---
        video_plan = pipeline.build_video_plan(a, script, timeline, provider="mock")
        check(len(video_plan["scenes"]) == len(script["scenes"]), "план не покрывает все сцены")
        first_scene = video_plan["scenes"][0]
        check("IDENTITY LOCK" in first_scene["motion_prompt"], "нет identity lock")
        check("идут" in first_scene["motion_prompt"], "action не попал в motion")
        check(first_scene["adjust"] in ("trim", "extend", "none"), "нет адаптации длительности")
        check(pipeline.plan_provider_duration(5.0)["adjust"] == "extend", "5.0 -> extend")
        check(pipeline.plan_provider_duration(7.0)["adjust"] in ("trim", "extend"), "7.0 без адаптации")
        result = pipeline.generate_scene_videos(a, video_plan)
        check(len(result["created"]) == len(video_plan["scenes"]), "видео не созданы")
        check(not pipeline.generate_scene_videos(a, video_plan)["created"], "видео пересоздаются")
        try:
            pipeline.generate_scene_videos(b, {**video_plan, "provider": "flow"})
            raise AssertionError("flow без конфигурации не упал")
        except pipeline.PipelineError:
            pass

        # --- Этап 7: контроль синхронизации ---
        pipeline.check_scene_sync(timeline, {1: 5.05})
        try:
            pipeline.check_scene_sync(timeline, {1: 5.8})
            raise AssertionError("рассинхрон не пойман")
        except pipeline.PipelineError:
            pass

        # изоляция: второй канал ничего не унаследовал
        check(not pipeline.scene_script_path(b).exists(), "scene_script утёк")
        check(not pipeline.voice_plan_path(b).exists(), "voice_plan утёк")
        check(pipeline.character_ref_path(a).read_bytes() == b"REF", "эталон изменён в конце прогона")

    print("OK: stages 1-7 checks passed")


def _raise_probe(path):
    raise pipeline.AudioProbeError("битый файл", stage="timeline")


if __name__ == "__main__":
    main()
