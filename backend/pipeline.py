"""Pipeline core (Этапы 1-7), без FastAPI и без обязательного OpenAI.

Все функции чистые/файловые и принимают channel_id — состояние каждого канала
живёт ТОЛЬКО в backend/runs/<channel_key>/. OpenAI-клиент всегда передаётся
аргументом, поэтому модуль можно импортировать и тестировать без ключей и без
единого платного вызова.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
RUNS_DIR = BACKEND_DIR / "runs"

FFMPEG_BIN = "ffmpeg"
FFPROBE_BIN = "ffprobe"


class PipelineError(Exception):
    """Явная ошибка этапа: сообщение показывается пользователю как есть."""

    def __init__(self, message: str, *, stage: str = "", retryable: bool = True, details: str = ""):
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.retryable = retryable
        self.details = details


class AudioProbeError(PipelineError):
    pass


# --------------------------------------------------------------------------
# Этап 1: изоляция каналов
# --------------------------------------------------------------------------

def safe_channel_key(channel_id: str) -> str:
    key = re.sub(r"[^a-zA-Z0-9_-]+", "_", (channel_id or "").strip())
    return key[:80] if key else "default"


def channel_run_dir(channel_id: str, *, create: bool = True) -> Path:
    path = RUNS_DIR / safe_channel_key(channel_id)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def run_path(channel_id: str, *parts: str, create_parent: bool = True) -> Path:
    path = channel_run_dir(channel_id).joinpath(*parts)
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def character_ref_path(channel_id: str) -> Path:
    """Постоянный эталон внешности канала. Никогда не перезаписывается сценами."""
    return run_path(channel_id, "character_ref.png")


def character_bible_path(channel_id: str) -> Path:
    return run_path(channel_id, "character_bible.json")


def scene_script_path(channel_id: str) -> Path:
    return run_path(channel_id, "scene_script.json")


def voice_profiles_path(channel_id: str) -> Path:
    return run_path(channel_id, "voice_profiles.json")


def voice_plan_path(channel_id: str) -> Path:
    return run_path(channel_id, "voice_plan.json")


def timeline_path(channel_id: str) -> Path:
    return run_path(channel_id, "timeline.json")


def video_plan_path(channel_id: str) -> Path:
    return run_path(channel_id, "video_plan.json")


def final_video_path(channel_id: str) -> Path:
    return run_path(channel_id, "final_video.mp4")


# --------------------------------------------------------------------------
# Этап 2: стабильная личность персонажа
# --------------------------------------------------------------------------

CHARACTER_BIBLE_FIELDS = (
    ("age", "возраст"),
    ("face", "лицо"),
    ("skin_tone", "тон кожи"),
    ("eye_color", "цвет глаз"),
    ("hair_color", "цвет волос/шерсти"),
    ("hair_style", "причёска"),
    ("proportions", "пропорции"),
    ("outfit", "одежда"),
    ("footwear", "обувь"),
    ("accessories", "аксессуары"),
    ("colors", "ключевые цвета"),
    ("distinguishing_features", "отличительные черты"),
)

LEGACY_ALIASES = {
    "hair_color": ("hair",),
    "hair_style": ("hair",),
    "outfit": ("clothing",),
    "distinguishing_features": ("distinctive_features",),
}

IDENTITY_LOCK_RULES = (
    "IDENTITY LOCK: возраст, лицо, тон кожи, цвет глаз, цвет и форма волос/шерсти, "
    "пропорции, одежда, обувь и аксессуары персонажа обязаны совпадать с "
    "character_ref.png и character_bible.json. Запрещено изменять внешность, "
    "переодевать, взрослить/омолаживать или заменять персонажа. Меняются только "
    "поза, мимика в рамках эмоции, движение камеры и фон."
)

REFERENCE_PROMPT_SUFFIX = (
    "\n\nПЕРВОЕ приложенное изображение — постоянный эталон внешности персонажей "
    "(character_ref). Сохрани лицо, причёску/шерсть, одежду, цвета и пропорции "
    "ТОЧНО как на нём. ВТОРОЕ изображение (если оно есть) — только референс "
    "освещения, палитры и окружения предыдущей сцены; НЕ бери из него внешность. "
    + IDENTITY_LOCK_RULES
)


def character_bible_value(profile: dict, key: str) -> str:
    value = (profile.get(key) or "").strip()
    if value:
        return value
    for alias in LEGACY_ALIASES.get(key, ()):  # обратная совместимость
        legacy = (profile.get(alias) or "").strip()
        if legacy:
            return legacy
    return ""


def character_bible_schema_instructions() -> str:
    keys = ", ".join(key for key, _ in CHARACTER_BIBLE_FIELDS)
    return (
        "Раздели на отдельных персонажей, если их несколько. Для КАЖДОГО персонажа "
        f"укажи коротко и конкретно: name, {keys}.\n\n"
        "Ответь СТРОГО валидным JSON без markdown, в формате: "
        '{"style": "...", "characters": [{"name": "...", '
        + ", ".join(f'"{key}": "..."' for key, _ in CHARACTER_BIBLE_FIELDS)
        + "}]}"
    )


def render_character_bible_prompt(bible: dict) -> str:
    lines = [
        f"Стиль канала (фиксированный): {bible.get('style', '')}",
        "ПОСТОЯННЫЕ ПЕРСОНАЖИ КАНАЛА (character bible, не менять никогда):",
    ]
    for profile in bible.get("characters", []):
        parts = [f"— {profile.get('name') or 'Персонаж'}:"]
        for key, label in CHARACTER_BIBLE_FIELDS:
            value = character_bible_value(profile, key)
            if value:
                parts.append(f"{label}: {value}")
        lines.append(" ".join(parts))
    lines.append(IDENTITY_LOCK_RULES)
    return "\n".join(lines)


def load_character_bible(channel_id: str) -> dict:
    bible = read_json(character_bible_path(channel_id))
    if not isinstance(bible, dict) or not isinstance(bible.get("characters"), list):
        raise PipelineError(
            "Character bible для этого канала отсутствует или повреждён.",
            stage="character_identity",
            retryable=False,
        )
    return bible


def save_character_bible(channel_id: str, bible: dict, *, overwrite: bool = False) -> Path:
    path = character_bible_path(channel_id)
    if path.exists() and not overwrite:
        return path
    write_json(path, bible)
    return path


def save_character_reference(channel_id: str, image_bytes: bytes, *, overwrite: bool = False) -> bool:
    """Эталон пишется только если его ещё нет (или явный overwrite)."""
    path = character_ref_path(channel_id)
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_bytes)
    return True


# --------------------------------------------------------------------------
# Этап 3: scene-based сценарий
# --------------------------------------------------------------------------

NARRATOR_ID = "narrator"


def _slugify_id(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return slug[:40] or fallback


def build_character_roster(bible: dict) -> list:
    roster = []
    used = set()
    for index, profile in enumerate(bible.get("characters", []), start=1):
        name = (profile.get("name") or f"Персонаж {index}").strip()
        character_id = _slugify_id(name, f"character_{index}")
        while character_id in used:
            character_id = f"{character_id}_{index}"
        used.add(character_id)
        roster.append({"character_id": character_id, "name": name, "is_narrator": False})
    roster.append({"character_id": NARRATOR_ID, "name": "Narrator", "is_narrator": True})
    return roster


def scene_script_prompt(topic: str, bible: dict, roster: list) -> str:
    speakers = ", ".join(f"{item['character_id']} ({item['name']})" for item in roster)
    return (
        "Ты сценарист YouTube-ролика. Составь сценарий, разбитый на 8-14 сцен.\n\n"
        f"Тема: {topic}\n\n"
        f"{render_character_bible_prompt(bible)}\n\n"
        f"Доступные speaker_id (использовать ТОЛЬКО их): {speakers}\n\n"
        "Ответь СТРОГО валидным JSON без markdown в формате:\n"
        '{"scenes": [{"scene_id": 1, "scene_title": "...", "visual_description": "...", '
        '"character_ids": ["..."], "action": "...", "emotion": "...", "pause_after": 0.5, '
        '"lines": [{"speaker_id": "...", "dialogue": "...", "emotion": "...", "pause_after": 0.3}]}]}\n'
        "Не выдумывай персонажей вне списка speaker_id. Не пиши один длинный текст."
    )


def _coerce_float(value, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(result) or result < 0:
        return default
    return round(result, 3)


def normalize_scene_script(raw: dict, roster: list, *, channel_id: str = "", topic: str = "") -> dict:
    by_id = {item["character_id"]: item for item in roster}
    default_speaker = NARRATOR_ID
    raw_scenes = (raw or {}).get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise PipelineError(
            "Модель не вернула ни одной сцены.", stage="scene_script", retryable=True
        )

    scenes = []
    for index, raw_scene in enumerate(raw_scenes, start=1):
        raw_scene = raw_scene if isinstance(raw_scene, dict) else {}
        scene_id = raw_scene.get("scene_id")
        scene_id = int(scene_id) if isinstance(scene_id, int) and scene_id > 0 else index

        raw_lines = raw_scene.get("lines")
        if not isinstance(raw_lines, list) or not raw_lines:
            single = (raw_scene.get("dialogue") or "").strip()
            raw_lines = [{
                "speaker_id": raw_scene.get("speaker_id"),
                "dialogue": single,
                "emotion": raw_scene.get("emotion"),
                "pause_after": raw_scene.get("pause_after"),
            }] if single else []

        lines = []
        for line_index, raw_line in enumerate(raw_lines, start=1):
            raw_line = raw_line if isinstance(raw_line, dict) else {}
            dialogue = (raw_line.get("dialogue") or "").strip()
            if not dialogue:
                continue
            speaker_id = raw_line.get("speaker_id")
            if speaker_id not in by_id:
                speaker_id = default_speaker
            lines.append({
                "line_id": line_index,
                "speaker_id": speaker_id,
                "speaker_name": by_id[speaker_id]["name"],
                "dialogue": dialogue,
                "emotion": (raw_line.get("emotion") or raw_scene.get("emotion") or "neutral").strip(),
                "pause_after": _coerce_float(raw_line.get("pause_after"), 0.3),
            })

        character_ids = [
            cid for cid in (raw_scene.get("character_ids") or []) if cid in by_id
        ]
        for line in lines:
            if line["speaker_id"] not in character_ids:
                character_ids.append(line["speaker_id"])
        if not character_ids:
            character_ids = [default_speaker]

        primary = lines[0]["speaker_id"] if lines else default_speaker
        scenes.append({
            "scene_id": scene_id,
            "scene_title": (raw_scene.get("scene_title") or f"Сцена {scene_id}").strip(),
            "visual_description": (raw_scene.get("visual_description") or "").strip(),
            "character_ids": character_ids,
            "speaker_id": primary,
            "speaker_name": by_id[primary]["name"],
            "dialogue": " ".join(line["dialogue"] for line in lines),
            "action": (raw_scene.get("action") or "").strip(),
            "emotion": (raw_scene.get("emotion") or "neutral").strip(),
            "pause_after": _coerce_float(raw_scene.get("pause_after"), 0.5),
            "lines": lines,
        })

    return {
        "channel_id": channel_id,
        "topic": topic,
        "characters": roster,
        "scenes": scenes,
    }


def load_scene_script(channel_id: str) -> dict:
    script = read_json(scene_script_path(channel_id))
    if not isinstance(script, dict) or not script.get("scenes"):
        raise PipelineError(
            "scene_script.json отсутствует или пуст — сначала выполните этап сценария.",
            stage="scene_script",
            retryable=False,
        )
    return script


# --------------------------------------------------------------------------
# Этап 4: multi-voice TTS
# --------------------------------------------------------------------------

CHARACTER_VOICE_POOL = ("alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse")
NARRATOR_VOICE_ID = "marin"
TTS_MODEL = "gpt-4o-mini-tts"


def get_or_create_voice_profiles(channel_id: str, roster: list) -> dict:
    stored = read_json(voice_profiles_path(channel_id))
    profiles = stored.get("profiles") if isinstance(stored, dict) else None
    profiles = profiles if isinstance(profiles, dict) else {}

    used = {value.get("voice_id") for value in profiles.values() if isinstance(value, dict)}
    changed = False
    for item in roster:
        character_id = item["character_id"]
        if character_id in profiles:
            continue
        if item["is_narrator"]:
            voice_id = NARRATOR_VOICE_ID
        else:
            available = [v for v in CHARACTER_VOICE_POOL if v not in used and v != NARRATOR_VOICE_ID]
            voice_id = available[0] if available else CHARACTER_VOICE_POOL[len(profiles) % len(CHARACTER_VOICE_POOL)]
        used.add(voice_id)
        profiles[character_id] = {"voice_id": voice_id, "name": item["name"]}
        changed = True

    payload = {"channel_id": channel_id, "profiles": profiles}
    if changed or not stored:
        write_json(voice_profiles_path(channel_id), payload)
    return payload


def build_voice_plan(channel_id: str, script: dict, voice_profiles: dict) -> dict:
    profiles = voice_profiles["profiles"]
    items = []
    for scene in script["scenes"]:
        for line in scene["lines"]:
            speaker_id = line["speaker_id"]
            profile = profiles.get(speaker_id) or profiles[NARRATOR_ID]
            rel = f"audio/scene_{scene['scene_id']:03d}_line_{line['line_id']:03d}.mp3"
            items.append({
                "scene_id": scene["scene_id"],
                "line_id": line["line_id"],
                "speaker_id": speaker_id,
                "speaker_name": line["speaker_name"],
                "voice_id": profile["voice_id"],
                "emotion": line["emotion"],
                "text": line["dialogue"],
                "pause_after": line["pause_after"],
                "audio_path": rel,
            })
    plan = {"channel_id": channel_id, "model": TTS_MODEL, "items": items}
    write_json(voice_plan_path(channel_id), plan)
    return plan


def synthesize_voice_plan(channel_id: str, plan: dict, client) -> dict:
    """Идемпотентно: существующий непустой клип не переозвучивается."""
    created, skipped = [], []
    for item in plan["items"]:
        target = run_path(channel_id, *item["audio_path"].split("/"))
        if target.exists() and target.stat().st_size > 0:
            skipped.append(item["audio_path"])
            continue
        with client.audio.speech.with_streaming_response.create(
            model=plan.get("model", TTS_MODEL),
            voice=item["voice_id"],
            input=item["text"],
            instructions=(
                f"Speak in the same language as the input text. Emotion: {item['emotion']}. "
                "Keep one consistent voice identity for this character."
            ),
        ) as response:
            response.stream_to_file(target)
        created.append(item["audio_path"])
    return {"created": created, "skipped": skipped}


# --------------------------------------------------------------------------
# Этап 5: тайминг и синхронизация
# --------------------------------------------------------------------------

SILENT_SCENE_DURATION = 3.0


def probe_audio_duration(path: Path) -> float:
    if not Path(path).exists():
        raise AudioProbeError(
            f"Аудиоклип не найден: {path}", stage="timeline", retryable=True
        )
    try:
        probe = subprocess.run(
            [FFPROBE_BIN, "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            capture_output=True, text=True, check=True,
        )
        duration = float(json.loads(probe.stdout)["format"]["duration"])
    except Exception as error:  # noqa: BLE001 — ошибка явная, без "угадывания"
        raise AudioProbeError(
            f"Не удалось определить длительность аудио: {path}",
            stage="timeline",
            retryable=True,
            details=str(error),
        ) from error
    if duration <= 0:
        raise AudioProbeError(
            f"Нулевая длительность аудио: {path}", stage="timeline", retryable=True
        )
    return round(duration, 3)


def build_timeline(channel_id: str, script: dict, plan: dict) -> dict:
    by_key = {(item["scene_id"], item["line_id"]): item for item in plan["items"]}
    scenes = []
    cursor = 0.0
    for scene in script["scenes"]:
        lines = []
        position = 0.0
        for line in scene["lines"]:
            item = by_key.get((scene["scene_id"], line["line_id"]))
            if item is None:
                raise PipelineError(
                    f"В voice_plan нет реплики {scene['scene_id']}/{line['line_id']}.",
                    stage="timeline", retryable=False,
                )
            audio_file = run_path(channel_id, *item["audio_path"].split("/"), create_parent=False)
            duration = probe_audio_duration(audio_file)
            start = round(position, 3)
            end = round(start + duration, 3)
            lines.append({
                "line_id": line["line_id"],
                "speaker_id": line["speaker_id"],
                "audio_path": item["audio_path"],
                "duration": duration,
                "start_time_in_scene": start,
                "end_time_in_scene": end,
                "pause_after": line["pause_after"],
            })
            position = end + line["pause_after"]

        scene_duration = round(position + scene["pause_after"], 3) if lines else SILENT_SCENE_DURATION
        scenes.append({
            "scene_id": scene["scene_id"],
            "scene_start": round(cursor, 3),
            "scene_end": round(cursor + scene_duration, 3),
            "scene_duration": scene_duration,
            "silent": not lines,
            "lines": lines,
        })
        cursor += scene_duration

    timeline = {
        "channel_id": channel_id,
        "total_duration": round(cursor, 3),
        "scenes": scenes,
    }
    write_json(timeline_path(channel_id), timeline)
    return timeline


def load_timeline(channel_id: str) -> dict:
    timeline = read_json(timeline_path(channel_id))
    if not isinstance(timeline, dict) or not timeline.get("scenes"):
        raise PipelineError(
            "timeline.json отсутствует — сначала рассчитайте тайминг.",
            stage="timeline", retryable=False,
        )
    return timeline


# --------------------------------------------------------------------------
# Этап 6: image-to-video план и провайдеры
# --------------------------------------------------------------------------

FLOW_DURATIONS = (4.0, 6.0, 8.0)


def plan_provider_duration(target: float, allowed=FLOW_DURATIONS) -> dict:
    best = min(allowed, key=lambda value: (abs(value - target), value))
    if abs(best - target) < 0.01:
        adjust = "none"
    else:
        adjust = "trim" if best > target else "extend"
    return {"provider_duration": best, "adjust": adjust}


def build_video_plan(channel_id: str, script: dict, timeline: dict, *, provider: str = "mock") -> dict:
    durations = {scene["scene_id"]: scene["scene_duration"] for scene in timeline["scenes"]}
    scenes = []
    for scene in script["scenes"]:
        target = durations.get(scene["scene_id"])
        if target is None:
            raise PipelineError(
                f"В timeline нет сцены {scene['scene_id']}.", stage="video_plan", retryable=False
            )
        motion_prompt = (
            f"{scene['visual_description']} Движение камеры и персонажа следует действию: "
            f"{scene['action'] or 'спокойное естественное движение'}. Эмоция: {scene['emotion']}. "
            + IDENTITY_LOCK_RULES
        )
        scenes.append({
            "scene_id": scene["scene_id"],
            "image_path": f"visual_{scene['scene_id']}.png",
            "character_ref": "character_ref.png",
            "motion_prompt": motion_prompt,
            "target_duration": target,
            **plan_provider_duration(target),
            "video_path": f"video/scene_{scene['scene_id']:03d}.mp4",
        })
    plan = {"channel_id": channel_id, "provider": provider, "scenes": scenes}
    write_json(video_plan_path(channel_id), plan)
    return plan


def _mock_video_provider(channel_id: str, scene: dict) -> Path:
    target = run_path(channel_id, *scene["video_path"].split("/"))
    target.write_bytes(b"MOCK_VIDEO")
    return target


def _flow_video_provider(channel_id: str, scene: dict) -> Path:
    raise PipelineError(
        "Провайдер Flow не сконфигурирован (нет API-доступа). Настройте ключи или используйте mock.",
        stage="scene_videos", retryable=False,
    )


VIDEO_PROVIDERS = {"mock": _mock_video_provider, "flow": _flow_video_provider}


def generate_scene_videos(channel_id: str, plan: dict) -> dict:
    provider = VIDEO_PROVIDERS.get(plan.get("provider", "mock"))
    if provider is None:
        raise PipelineError(
            f"Неизвестный video provider: {plan.get('provider')}", stage="scene_videos", retryable=False
        )
    created, skipped = [], []
    for scene in plan["scenes"]:
        target = run_path(channel_id, *scene["video_path"].split("/"))
        if target.exists() and target.stat().st_size > 0:
            skipped.append(scene["video_path"])
            continue
        provider(channel_id, scene)
        created.append(scene["video_path"])
    return {"created": created, "skipped": skipped}


# --------------------------------------------------------------------------
# Этап 7: финальная сборка FFmpeg
# --------------------------------------------------------------------------

SYNC_TOLERANCE = 0.08


def _run_ffmpeg(args: list) -> None:
    result = subprocess.run([FFMPEG_BIN, "-y", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise PipelineError(
            "FFmpeg завершился с ошибкой.", stage="final_video", retryable=True,
            details=result.stderr[-2000:],
        )


def assemble_scene_audio(channel_id: str, scene: dict, out_path: Path) -> Path:
    """Аудио сцены: тишина длиной scene_duration + вставленные по времени клипы."""
    inputs, filters, labels = ["-f", "lavfi", "-t", str(scene["scene_duration"]), "-i", "anullsrc=r=44100:cl=mono"], [], []
    for index, line in enumerate(scene["lines"], start=1):
        clip = run_path(channel_id, *line["audio_path"].split("/"), create_parent=False)
        if not clip.exists():
            raise PipelineError(
                f"Отсутствует аудиоклип {line['audio_path']}.", stage="final_video", retryable=True
            )
        inputs += ["-i", str(clip)]
        delay = int(round(line["start_time_in_scene"] * 1000))
        filters.append(f"[{index}:a]adelay={delay}|{delay}[a{index}]")
        labels.append(f"[a{index}]")
    if labels:
        filter_complex = ";".join(filters) + f";[0:a]{''.join(labels)}amix=inputs={len(labels) + 1}:duration=first:dropout_transition=0[out]"
        _run_ffmpeg([*inputs, "-filter_complex", filter_complex, "-map", "[out]", "-t", str(scene["scene_duration"]), str(out_path)])
    else:
        _run_ffmpeg([*inputs, "-t", str(scene["scene_duration"]), str(out_path)])
    return out_path


def check_scene_sync(timeline: dict, measured: dict) -> None:
    for scene in timeline["scenes"]:
        actual = measured.get(scene["scene_id"])
        if actual is None:
            continue
        if abs(actual - scene["scene_duration"]) > SYNC_TOLERANCE:
            raise PipelineError(
                f"Рассинхрон сцены {scene['scene_id']}: {actual}s против {scene['scene_duration']}s "
                f"(допуск {SYNC_TOLERANCE}s). Голос не растягивается.",
                stage="final_video", retryable=False,
            )


def assemble_final_video(channel_id: str, timeline: dict, video_plan: dict) -> Path:
    by_scene = {scene["scene_id"]: scene for scene in video_plan["scenes"]}
    work_dir = run_path(channel_id, "work")
    work_dir.mkdir(parents=True, exist_ok=True)
    segments = []
    for scene in timeline["scenes"]:
        plan_scene = by_scene.get(scene["scene_id"])
        if plan_scene is None:
            raise PipelineError(
                f"В video_plan нет сцены {scene['scene_id']}.", stage="final_video", retryable=False
            )
        clip = run_path(channel_id, *plan_scene["video_path"].split("/"), create_parent=False)
        if not clip.exists():
            raise PipelineError(
                f"Отсутствует видео сцены {plan_scene['video_path']}.", stage="final_video", retryable=True
            )
        audio = assemble_scene_audio(channel_id, scene, work_dir / f"scene_{scene['scene_id']:03d}.m4a")
        segment = work_dir / f"segment_{scene['scene_id']:03d}.mp4"
        # trim / freeze-extend до точной scene_duration, звук не меняется
        _run_ffmpeg([
            "-stream_loop", "-1", "-i", str(clip), "-i", str(audio),
            "-map", "0:v:0", "-map", "1:a:0",
            "-t", str(scene["scene_duration"]),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(segment),
        ])
        segments.append(segment)

    concat_file = work_dir / "segments.txt"
    concat_file.write_text("\n".join(f"file '{segment.resolve()}'" for segment in segments))
    output = final_video_path(channel_id)
    _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(output)])
    shutil.rmtree(work_dir, ignore_errors=True)
    return output
