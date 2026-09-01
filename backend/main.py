import base64
import json
import re
import subprocess
import tempfile
import urllib.request
import yt_dlp
from fastapi import FastAPI, UploadFile, File
from openai import OpenAI
from fastapi.middleware.cors import CORSMiddleware

import pipeline
import jobs
from pipeline import (
    channel_run_dir,
    character_bible_path,
    character_ref_path,
    run_path,
    safe_channel_key,
)

# Этап 1: один план на КАНАЛ, а не одна глобальная строка на весь процесс.
latest_visual_plans: dict[str, str] = {}

app = FastAPI()
client = OpenAI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    )

@app.get("/")
def read_root():
    return {"message": "YouTube AI Autopilot backend работает"}
    
@app.get("/autopilot/start")
def start_autopilot(channel_analysis: str = "", channel_language: str = ""):

        # Язык — универсальный параметр для ЛЮБОГО канала (preset или
        # пользовательский), а не частный случай одного канала:
        # - если frontend прислал known channel_language (язык этого канала
        #   уже определён/сохранён как часть его конфигурации) — используем
        #   его напрямую, без догадок;
        # - иначе, как и раньше, определяем язык по тексту channel_analysis.
        if channel_language.strip():
            language_instruction = (
                f"Обязательно пиши ВЕСЬ результат на языке: {channel_language}. "
                "Не переключайся на другой язык, даже если анализ ниже написан на другом языке."
            )
        else:
            language_instruction = (
                "Определи основной язык существующего канала по анализу ниже и пиши весь результат на этом же языке."
            )

        response = client.responses.create(
    model="gpt-5.6",
    input=(
    "Ты — AI-стратег по YouTube. "
    f"{language_instruction} "
        f"Вот анализ существующего канала:\n{channel_analysis}\n"
        "Выбери перспективную нишу для нового YouTube-канала для начинающего автора. "
    "Придумай название канала и тему первого ролика. "
    "Ответь строго в формате:\n"
    "NICHE: ...\n"
    "CHANNEL: ...\n"
    "VIDEO: ..."
    ),
    )

        text = response.output_text

        lines = text.splitlines()

        niche = lines[0].replace("NICHE:", "").strip()
        channel_name = lines[1].replace("CHANNEL:", "").strip()
        first_video = lines[2].replace("VIDEO:", "").strip()

        return {
    "status": "ok",
    "niche": niche,
    "channel_name": channel_name,
    "first_video": first_video,
    "message": "Данные созданы через OpenAI"
    }
@app.get("/autopilot/script")
def generate_script(topic: str):
    response = client.responses.create(
        model="gpt-5.6",
        input=f"""
Определи язык по теме ниже и напиши весь сценарий на этом же языке.
Тема: {topic}
"""
    )

    return {
        "status": "ok",
        "script": response.output_text
    }
@app.get("/autopilot/voice-plan")
def generate_voice_plan(topic: str):
    response = client.responses.create(
        model="gpt-5.6",
        input=f"""
Составь план озвучки для YouTube-видео на тему:
{topic}

Дай:
1. стиль голоса
2. темп речи
3. настроение
4. где делать паузы
5. какие фразы выделять голосом
6. рекомендации по дикции
"""
    )

    return {
        "status": "ok",
        "voice_plan": response.output_text
    }
from pathlib import Path
import uuid
from fastapi.responses import FileResponse
@app.get("/autopilot/voice")
def generate_voice(text: str, channel_id: str):
    speech_file_path = run_path(channel_id, "speech.mp3")

    chunks = [text[i:i+3000] for i in range(0, len(text), 3000)]
    audio_parts = []
    for index, chunk in enumerate(chunks):
        part_path = run_path(channel_id, f"speech_{uuid.uuid4().hex}_{index}.mp3")

        with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice="marin",
            input=chunk,
            instructions=(
                "Speak in the same language as the input text, in a warm, "
                "friendly, lively voice, like a cheerful storyteller for a "
                "children's YouTube channel. Upbeat but gentle tone, "
                "natural pacing, clear pronunciation, light smile in the "
                "voice, no monotone or robotic delivery."
            ),
        ) as response:
            response.stream_to_file(part_path)

        audio_parts.append(part_path)

    with open(speech_file_path, "wb") as final_audio:
        for part_path in audio_parts:
            final_audio.write(part_path.read_bytes())
            part_path.unlink()

    return {
        "status": "ok",
        "audio_file": "speech.mp3"
    }

@app.get("/autopilot/audio")
def get_audio(channel_id: str):
    speech_file_path = run_path(channel_id, "speech.mp3")
    return FileResponse(
        speech_file_path,
        media_type="audio/mpeg",
        filename="speech.mp3"
    )

@app.post("/autopilot/upload-character-photo")
async def upload_character_photo(channel_id: str, file: UploadFile = File(...)):
    photo_path = run_path(channel_id, "character_photo.jpg")

    with open(photo_path, "wb") as buffer:
        buffer.write(await file.read())

    return {
        "status": "ok",
        "filename": file.filename,
        "saved_as": "character_photo.jpg",
    }
@app.get("/autopilot/visual-plan")
def generate_visual_plan(
    topic: str,
    character: str,
    style: str,
    channel_id: str,
    use_character_photo: bool = False,
):
    # 1. character/style теперь обязательные (без "" по умолчанию) — вызов
    # без них (например, старая кнопка "Создать план визуалов") получит
    # ошибку вместо того, чтобы тихо затереть план текущего канала пустым.

    # 2. Перед генерацией НОВОГО плана удаляем старые кадры сцен, чтобы
    # build_video() не мог случайно подхватить картинки от другого канала,
    # если какая-то из сцен не перегенерируется в этом запуске.
    for scene_name in ("visual_1.png", "visual_2.png", "visual_3.png"):
        scene_path = run_path(channel_id, scene_name)
        if scene_path.exists():
            scene_path.unlink()

    photo_path = run_path(channel_id, "character_photo.jpg")

    # КРИТИЧНО (найдено при проверке полного pipeline, баг существовал ещё
    # в main-old.py, задолго до этого раунда правок):
    # 1) Раньше use_character_photo не проверялся вовсе — фото ЛЮБОГО
    #    прошлого канала, просто оставшееся на диске, молча попадало в
    #    план ЭТОГО канала (та же утечка, что уже была закрыта в
    #    generate_scene, но здесь так и оставалась открытой) — вероятная
    #    настоящая причина "персонажи не похожи на Sabrina/Unico": план и
    #    сцены могли неявно ориентироваться на чужое фото.
    # 2) `response` создавался ТОЛЬКО внутри `if photo_path.exists():`, а
    #    использовался БЕЗ этого условия — при отсутствии файла на диске
    #    это гарантированно роняло запрос с UnboundLocalError. Теперь
    #    `response` создаётся в обеих ветках.
    use_photo_reference = use_character_photo and photo_path.exists()
    photo_info = "Фото персонажей загружено." if use_photo_reference else "Фото персонажей не загружено."

    # Тот же зафиксированный по channel_id character bible, что и в
    # generate_scene — план сцен строится с учётом ТЕХ ЖЕ персонажей и
    # стиля, что потом попадут в картинки, а не заново пересказанного
    # текста character/style (иначе само планирование сцен могло бы
    # придумывать новые детали персонажей).
    character_bible = get_or_create_character_bible(channel_id, character, style, use_character_photo)
    character_bible_prompt = render_character_bible_prompt(character_bible)

    prompt_text = f"""
Создай визуальный план для YouTube-видео на тему:
{topic}
{character_bible_prompt}
Фото: {photo_info}
Разбей видео на 10–15 сцен.
Каждую сцену начинай ОТДЕЛЬНОЙ строкой ровно в формате "### SCENE <номер>"
(например "### SCENE 1"), без другого текста на этой строке — это нужно,
чтобы потом программно доставать описание конкретной сцены.
Для каждой сцены дай:
1. что должно быть на экране
2. тип визуала: фото, видео, текст, графика
3. пример поискового запроса для изображения или видео
4. пример текста на экране, если нужен

Ответ дай структурированно и понятно.
"""

    if use_photo_reference:
        base64_image = base64.b64encode(photo_path.read_bytes()).decode("utf-8")
        response = client.responses.create(
            model="gpt-5.6",
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt_text},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{base64_image}",
                    },
                ],
            }],
        )
    else:
        response = client.responses.create(
            model="gpt-5.6",
            input=prompt_text,
        )

    latest_visual_plans[safe_channel_key(channel_id)] = response.output_text
    return {
        "status": "ok",
        "visual_plan": response.output_text
    }
@app.get("/autopilot/visual-image-test")
def visual_image_test():
    return {
        "status": "ok",
        "message": "Маршрут для визуалов работает"
    }
   
@app.get("/autopilot/visual-image")
def generate_visual_image(prompt: str, channel_id: str):
    result = client.images.generate(
        model="gpt-image-2",
        prompt=prompt,
        size="1536x1024"
    )

    image_base64 = result.data[0].b64_json
    image_bytes = base64.b64decode(image_base64)

    image_path = run_path(channel_id, "visual_1.png")
    image_path.write_bytes(image_bytes)

    return {
        "status": "ok",
        "image_file": "visual_1.png"
    }
    from fastapi.responses import FileResponse

@app.get("/autopilot/visual-image-file")
def get_visual_image(channel_id: str):
    image_path = run_path(channel_id, "visual_1.png")
    return FileResponse(
        image_path,
        media_type="image/png"
    )
@app.get("/autopilot/visual-scenes-test")
def visual_scenes_test():
    return {
        "status": "ok",
        "scenes": [
            "Сцена 1",
            "Сцена 2",
            "Сцена 3"
        ]
    }
@app.get("/autopilot/visual-scenes")
def visual_scenes():
    return {
        "status": "ok",
        "scenes": [
            {
                "id": 1,
                "prompt": "Рабочий стол, ноутбук, таймер, много задач, динамичный YouTube-кадр"
            },
            {
                "id": 2,
                "prompt": "Человек автоматизирует рутинные задачи с помощью ИИ, современный интерфейс"
            },
            {
                "id": 3,
                "prompt": "Экран с результатом автоматизации, свободное время, ощущение продуктивности"
            }
        ]
    }
@app.get("/autopilot/generate-scenes")
def generate_scenes():
    scenes = [
        "Рабочий стол, ноутбук, таймер, много задач, динамичный YouTube-кадр",
        "Человек автоматизирует рутинные задачи с помощью ИИ, современный интерфейс",
        "Экран с результатом автоматизации, свободное время, ощущение продуктивности"
    ]

    return {
        "status": "ready",
        "count": len(scenes),
        "scenes": scenes
    }
CHARACTER_BIBLE_FIELDS = (
    ("face", "лицо"),
    ("hair", "волосы/шерсть"),
    ("clothing", "одежда"),
    ("age", "возраст"),
    ("proportions", "пропорции"),
    ("accessories", "аксессуары"),
    ("colors", "ключевые цвета"),
    ("distinctive_features", "отличительные черты"),
)


def _fallback_character_bible(character: str, style: str) -> dict:
    # Если GPT не вернул валидный JSON (сеть/модель подвела) — конвейер не
    # должен падать. Вся исходная информация о персонажах сохраняется как
    # есть (без потери), просто без разбивки по полям — деградация, а не
    # отказ. При следующем вызове для ЭТОГО канала файл уже будет на диске
    # и повторной генерации не потребуется (см. get_or_create_character_bible).
    return {
        "style": style,
        "characters": [
            {
                "name": "Персонажи",
                "face": character,
                "hair": "",
                "clothing": "",
                "age": "",
                "proportions": "",
                "accessories": "",
                "colors": "",
                "distinctive_features": "",
            }
        ],
    }


def _parse_json_object(text: str) -> dict:
    # GPT иногда оборачивает JSON в ```json ... ``` — вырезаем блок между
    # первой "{" и последней "}", если прямой json.loads не сработал.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start:end + 1])


def _character_bible_schema_instructions() -> str:
    # Общая для текстового и визуального путей часть промпта — формат
    # ответа не должен отличаться в зависимости от источника.
    return (
        "Раздели на отдельных персонажей, если их несколько. Для КАЖДОГО "
        "персонажа укажи коротко и конкретно (несколько слов на поле, без "
        "абзацев): name, face, hair, clothing, age, proportions, "
        "accessories, colors, distinctive_features.\n\n"
        "Ответь СТРОГО валидным JSON без markdown-разметки и без пояснений, "
        "ровно в формате:\n"
        '{"style": "<короткая фиксированная формулировка стиля>", '
        '"characters": [{"name": "...", "face": "...", "hair": "...", '
        '"clothing": "...", "age": "...", "proportions": "...", '
        '"accessories": "...", "colors": "...", "distinctive_features": "..."}]}'
    )


def _generate_character_bible_from_text(character: str, style: str) -> dict:
    # Fallback-путь: используется, ТОЛЬКО если для канала ещё нет ни
    # реального изображения (character_ref_<channel_id>.png), ни явно
    # загруженного фото. Разовая генерация — дальше bible читается с диска
    # без изменений (см. get_or_create_character_bible).
    fallback = _fallback_character_bible(character, style)
    try:
        response = client.responses.create(
            model="gpt-5.6",
            input=(
                "Ты фиксируешь неизменный визуальный профиль персонажей "
                "YouTube-канала для генерации изображений (character bible).\n\n"
                f"Свободное описание персонажей канала:\n{character}\n\n"
                f"Стиль канала:\n{style}\n\n"
                f"{_character_bible_schema_instructions()}"
            ),
        )
        parsed = _parse_json_object(response.output_text)
        if isinstance(parsed, dict) and isinstance(parsed.get("characters"), list) and parsed["characters"]:
            parsed.setdefault("style", style)
            return parsed
    except Exception:
        # Любая проблема (сеть, невалидный JSON, неожиданная форма ответа) —
        # используем fallback, а не роняем /autopilot/visual-plan или
        # /autopilot/generate-scene.
        pass
    return fallback


def _generate_character_bible_from_image(image_bytes: bytes, character: str, style: str) -> dict:
    # Источник истины — РЕАЛЬНОЕ изображение канала (реальный thumbnail из
    # analyze_channel, ранее сохранённый character_ref, либо загруженное
    # пользователем фото). Текст используется ТОЛЬКО для имён и сюжетного
    # контекста — если текст противоречит картинке, побеждает картинка.
    fallback = _fallback_character_bible(character, style)
    try:
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        response = client.responses.create(
            model="gpt-5.6",
            input=[{
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Ты фиксируешь неизменный визуальный профиль персонажей "
                            "YouTube-канала для генерации изображений (character bible).\n\n"
                            "ПРИЛОЖЕННОЕ ИЗОБРАЖЕНИЕ — источник истины для внешности "
                            "персонажей. Определяй face, hair, clothing, age, "
                            "proportions, accessories, colors, distinctive_features "
                            "ТОЛЬКО по тому, что реально видно на изображении, ничего "
                            "не придумывая от себя.\n\n"
                            "Текстовое описание ниже используй ТОЛЬКО для имён "
                            "персонажей и сюжетного контекста — НЕ для внешности. "
                            "Если текст противоречит изображению по внешности — "
                            "доверяй изображению, а не тексту.\n\n"
                            f"Текст (имена/контекст):\n{character}\n\n"
                            f"Стиль канала:\n{style}\n\n"
                            f"{_character_bible_schema_instructions()}"
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{base64_image}",
                    },
                ],
            }],
        )
        parsed = _parse_json_object(response.output_text)
        if isinstance(parsed, dict) and isinstance(parsed.get("characters"), list) and parsed["characters"]:
            parsed.setdefault("style", style)
            return parsed
    except Exception:
        pass
    return fallback


def get_or_create_character_bible(
    channel_id: str,
    character: str,
    style: str,
    use_character_photo: bool = False,
) -> dict:
    # "Постоянный" character bible на канал: если файл уже существует —
    # возвращаем его КАК ЕСТЬ, не пересоздавая и не подмешивая текущие
    # character/style с фронтенда. Это и есть фиксация: одни и те же
    # персонажи/стиль передаются без изменений в каждую сцену каждого
    # ролика этого канала. Имя файла зависит только от channel_id — тот же
    # safe_channel_key, что и у character_ref_<channel_id>.png, поэтому
    # каналы не могут случайно поделить один и тот же bible.
    project_dir = channel_run_dir(channel_id)
    bible_path = character_bible_path(channel_id)
    if bible_path.exists():
        try:
            return json.loads(bible_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass  # повреждённый файл — пересоздаём ниже, не роняем pipeline

    # Приоритет источника истины для ВНЕШНОСТИ, единый для всех каналов:
    # 1) явно загруженное пользователем фото для ЭТОГО канала — самый
    #    сильный сигнал, выше автоматически сохранённого референса;
    # 2) уже установленный реальный/устоявшийся референс канала
    #    (character_ref_<channel_id>.png — либо из analyze_channel по
    #    реальным thumbnail, либо закреплённый по итогам прошлых роликов);
    # 3) только если ничего визуального нет — текстовое описание (fallback).
    channel_reference_path = character_ref_path(channel_id)
    photo_path = project_dir / "character_photo.jpg"

    if use_character_photo and photo_path.exists():
        bible = _generate_character_bible_from_image(
            photo_path.read_bytes(), character, style
        )
    elif channel_reference_path.exists():
        bible = _generate_character_bible_from_image(
            channel_reference_path.read_bytes(), character, style
        )
    else:
        bible = _generate_character_bible_from_text(character, style)

    try:
        bible_path.write_text(json.dumps(bible, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return bible


def render_character_bible_prompt(bible: dict) -> str:
    # Детерминированно превращает bible в один и тот же текстовый блок —
    # без пересказа моделью, без вариаций формулировок между вызовами.
    lines = [
        f"Стиль канала (фиксированный, не менять между сценами): {bible.get('style', '')}",
        "ПОСТОЯННЫЕ ПЕРСОНАЖИ КАНАЛА (character bible, не менять между сценами и между роликами):",
    ]
    for character_profile in bible.get("characters", []):
        parts = [f"— {character_profile.get('name') or 'Персонаж'}:"]
        for key, label in CHARACTER_BIBLE_FIELDS:
            value = (character_profile.get(key) or "").strip()
            if value:
                parts.append(f"{label}: {value}")
        lines.append(" ".join(parts))
    lines.append(
        "СТРОГО: используй эти характеристики персонажей и стиль ТОЧНО как "
        "указано, без изменений, во всех сценах и во всех будущих роликах "
        "этого канала. Не меняй лица, волосы/шерсть, одежду, возраст, "
        "пропорции, аксессуары или цвета персонажей между сценами."
    )
    return "\n".join(lines)


@app.get("/autopilot/reset-character-bible")
def reset_character_bible(channel_id: str):
    # Минимальный сброс: удаляет ТОЛЬКО character_bible_<channel_id>.json
    # этого канала. Ничего больше не трогает (ни character_ref_*.png, ни
    # visual_*.png, ни latest_visual_plan) — следующий вызов
    # /autopilot/visual-plan или /autopilot/generate-scene для этого же
    # channel_id просто не найдёт файл и сгенерирует bible заново с нуля
    # (см. get_or_create_character_bible), без дополнительных действий.
    bible_path = character_bible_path(channel_id)
    existed = bible_path.exists()
    if existed:
        bible_path.unlink()
    return {
        "status": "ok",
        "channel_id": channel_id,
        "deleted": existed,
    }


def extract_scene_description(plan_text: str, scene_id: int) -> str:
    # Достаёт из общего текстового плана только описание ОДНОЙ сцены по
    # маркерам "### SCENE <n>" (см. промпт в generate_visual_plan), вместо
    # того чтобы отдавать в каждую сцену весь план целиком.
    # Если разметку найти не удалось (модель ответила не в ожидаемом
    # формате) — используем весь план как раньше, это деградация, а не отказ.
    matches = list(re.finditer(r"###\s*SCENE\s*(\d+)\s*\n", plan_text, re.IGNORECASE))
    if not matches:
        return plan_text

    for index, match in enumerate(matches):
        if int(match.group(1)) != scene_id:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(plan_text)
        return plan_text[start:end].strip()

    return plan_text


def safe_channel_key(channel_id: str) -> str:
    # Превращает произвольное имя канала в безопасное имя файла: только
    # буквы/цифры/"_"/"-", без слэшей и спецсимволов (защита от обхода
    # пути через query-параметр), с ограничением длины.
    key = re.sub(r"[^a-zA-Z0-9_-]+", "_", channel_id.strip())
    return key[:80] if key else "default"


# Добавляется к prompt только когда реально передаётся референс-картинка
# (images.edit). Явно просит модель не "переизобретать" персонажей по
# тексту, а придерживаться именно приложенного изображения — без этого
# модель иногда всё равно рисует "просто похожего" персонажа, а не того
# же самого.
REFERENCE_PROMPT_SUFFIX = (
    "\n\nВАЖНО: приложенное изображение — эталон внешности персонажей. "
    "Сохрани лица, причёски/шерсть, одежду и её цвета, пропорции и стиль "
    "ТОЧНО как на приложенном изображении. Меняй только позу, ракурс, фон "
    "и действие по описанию сцены выше — не придумывай новый дизайн "
    "персонажей."
)


@app.get("/autopilot/generate-scene/{scene_id}")
def generate_scene(
    scene_id: int,
    character: str,
    style: str,
    channel_id: str,
    use_character_photo: bool = False,
    keep_characters: bool = False,
):
    latest_visual_plan = latest_visual_plans.get(safe_channel_key(channel_id), "")
    if not latest_visual_plan:
        return {"status": "error", "message": "Визуальный план ещё не создан"}

    # character_bible — постоянный, зафиксированный по channel_id профиль
    # персонажей+стиля этого канала (см. get_or_create_character_bible).
    # Один и тот же bible передаётся во ВСЕ сцены этого и будущих роликов
    # канала без изменений — это и устраняет "плывущие" между сценами
    # лица/волосы/одежду/возраст/пропорции/аксессуары.
    character_bible = get_or_create_character_bible(channel_id, character, style, use_character_photo)
    character_reference_prompt = render_character_bible_prompt(character_bible)
    scene_description = extract_scene_description(latest_visual_plan, scene_id)

    # Только описание ТЕКУЩЕЙ сцены + единый якорь персонажей — не весь план.
    prompt = f"{character_reference_prompt}\n\nСцена {scene_id}: {scene_description}"

    project_dir = channel_run_dir(channel_id)
    photo_path = project_dir / "character_photo.jpg"
    previous_scene_path = project_dir / f"visual_{scene_id - 1}.png"

    # Постоянный эталон внешности ЭТОГО канала между РАЗНЫМИ роликами.
    # Имя файла зависит только от channel_id, поэтому у разных каналов
    # всегда разные файлы — персонажи разных каналов не могут перемешаться.
    # Используется, только если для канала включено "Сохранять постоянных
    # персонажей" (keep_characters) — тот же флаг, что уже есть в UI
    # (чекбокс "Сохранять постоянных персонажей" -> keepCharacters), т.е.
    # ничего нового пользователю решать не нужно.
    channel_reference_path = character_ref_path(channel_id)

    # use_character_photo — явный признак от фронтенда, что для ТЕКУЩЕГО
    # канала реально выбран режим "Загрузить фото персонажей". Одного
    # факта наличия character_photo.jpg на диске недостаточно: файл мог
    # остаться от прошлого канала, чей прогон не дошёл до build-video
    # (там он обычно удаляется). Поэтому фото используется, только если
    # флаг явно true И файл при этом существует — иначе он полностью
    # игнорируется, даже если физически лежит на диске.
    use_photo_reference = use_character_photo and photo_path.exists()

    # Этап 2: character_ref.png — ПОСТОЯННЫЙ эталон канала. Он всегда идёт
    # первым референсом и НИКОГДА не перезаписывается результатом сцены,
    # поэтому внешность не "дрейфует" от кадра к кадру. Предыдущая сцена
    # передаётся только вторым изображением — для света/фона, не для лица.
    primary_reference = None
    if use_photo_reference:
        primary_reference = photo_path
    elif channel_reference_path.exists():
        primary_reference = channel_reference_path

    secondary_reference = previous_scene_path if (scene_id > 1 and previous_scene_path.exists()) else None

    if primary_reference is None:
        result = client.images.generate(
            model="gpt-image-2",
            prompt=prompt,
            size="1536x1024",
        )
    else:
        open_files = [open(primary_reference, "rb")]
        if secondary_reference is not None:
            open_files.append(open(secondary_reference, "rb"))
        try:
            result = client.images.edit(
                model="gpt-image-2",
                image=open_files if len(open_files) > 1 else open_files[0],
                prompt=prompt + REFERENCE_PROMPT_SUFFIX,
                size="1536x1024",
            )
        finally:
            for handle in open_files:
                handle.close()

    image_base64 = result.data[0].b64_json
    image_bytes = base64.b64decode(image_base64)

    image_path = project_dir / f"visual_{scene_id}.png"
    image_path.write_bytes(image_bytes)

    # Если у канала эталона ещё нет вообще — первая сцена его ЗАДАЁТ один раз.
    # Дальше он неизменен: результаты сцен эталон не перезаписывают.
    if scene_id == 1 and not use_photo_reference and not channel_reference_path.exists():
        channel_reference_path.write_bytes(image_bytes)

    return {
        "status": "ok",
        "scene_id": scene_id,
        "image_file": f"visual_{scene_id}.png"
    }

@app.get("/autopilot/build-video")
def build_video(channel_id: str):
    project_dir = channel_run_dir(channel_id)
    speech_path = project_dir / "speech.mp3"
    output_path = project_dir / "first_video.mp4"
    ffmpeg_bin = pipeline.FFMPEG_BIN
    # ffprobe выводится из пути ffmpeg (тот же bin-каталог Homebrew),
    # а не хардкодится отдельно — так путь верен и на Apple Silicon (/opt/homebrew),
    # и на Intel Mac (/usr/local), если ffmpeg_bin вообще указан правильно
    ffprobe_bin = str(Path(ffmpeg_bin).with_name("ffprobe"))

    # 1-2. Реальная длительность озвучки через ffprobe (вместо хардкода)
    probe = subprocess.run(
        [
            ffprobe_bin,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(speech_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    audio_duration = float(json.loads(probe.stdout)["format"]["duration"])

    # 3. Только текущие сцены 1–3 (столько генерирует /autopilot/generate-scene).
    # Без glob("visual_*.png"): он подхватил бы старые visual_4.png, visual_5.png
    # и т.п., оставшиеся от прошлых запусков с другим числом сцен.
    expected_scene_names = ["visual_1.png", "visual_2.png", "visual_3.png"]
    scene_files = [
        project_dir / name
        for name in expected_scene_names
        if (project_dir / name).exists()
    ]
    if not scene_files:
        return {"status": "error", "message": "Нет изображений сцен (visual_1.png..visual_3.png)"}

    seconds_per_scene = audio_duration / len(scene_files)
    frames_per_scene = max(int(round(seconds_per_scene * 30)), 1)

    # Шаг зума считается по длительности КОНКРЕТНОЙ сцены, а не фиксированным
    # числом: иначе на сценах длиннее ~6 сек zoom упирался в потолок 1.15
    # раньше времени и вторая половина сцены снова становилась статичной
    # (проверено тестом: с фиксированным +0.0008 на 20-секундной сцене
    # картинка замирала уже после 6-й секунды).
    zoom_start, zoom_end = 1.0, 1.15
    zoom_increment = (zoom_end - zoom_start) / frames_per_scene

    with tempfile.TemporaryDirectory(dir=project_dir) as tmp_dir:
        tmp_path = Path(tmp_dir)
        scene_clips = []

        # 4-5. Каждая сцена показывается ровно frames_per_scene кадров
        # (= seconds_per_scene секунд при 30 fps), с непрерывным Ken Burns
        # zoom/pan к центру на всю длину сцены, без статичных отрезков.
        # Использую только "-frames:v", а не "-t" + zoompan(d=...) одновременно:
        # оба варианта задавали длительность независимо друг от друга и могли
        # разойтись на доли кадра из-за округления seconds_per_scene.
        for index, image_path in enumerate(scene_files):
            clip_path = tmp_path / f"scene_{index}.mp4"

            zoom_cmd = [
                ffmpeg_bin,
                "-y",
                "-loop", "1",
                "-i", str(image_path),
                "-vf",
                (
                    "scale=1920:1080:force_original_aspect_ratio=increase,"
                    "crop=1920:1080,"
                    f"zoompan=z='min(zoom+{zoom_increment:.8f},{zoom_end})':"
                    "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"d={frames_per_scene}:s=1920x1080:fps=30"
                ),
                "-frames:v", str(frames_per_scene),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                str(clip_path),
            ]
            subprocess.run(zoom_cmd, check=True)
            scene_clips.append(clip_path)

        # Склеиваем анимированные сцены в один немой ролик
        concat_list_path = tmp_path / "concat_list.txt"
        concat_list_path.write_text(
            "\n".join(f"file '{clip.resolve()}'" for clip in scene_clips)
        )

        silent_video_path = tmp_path / "silent_video.mp4"
        subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list_path),
                "-c", "copy",
                str(silent_video_path),
            ],
            check=True,
        )

        # 6. Формат сохранён: 1920x1080, H.264 (video copy), AAC, -shortest по звуку
        subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-i", str(silent_video_path),
                "-i", str(speech_path),
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                str(output_path),
            ],
            check=True,
        )

    # 4. Сбрасываем план после успешной сборки видео: случайный повторный
    # клик "Собрать видео" без нового плана явно упадёт в generate-scene
    # ("Визуальный план ещё не создан") вместо тихого использования плана
    # от предыдущего запуска/канала.
    latest_visual_plans.pop(safe_channel_key(channel_id), None)

    # Сбрасываем и загруженное фото персонажей вместе с планом: иначе оно
    # оставалось бы на диске навсегда и generate_scene молча использовал бы
    # его как референс для СЛЕДУЮЩЕГО канала, даже если для того канала
    # режим "фото" вообще не выбирался. Фото актуально ровно один прогон:
    # если пользователь загрузил его для текущего канала, но ещё не запускал
    # "Собрать видео", оно продолжает действовать до конца этого прогона;
    # после успешной сборки — обнуляется, и следующий канал начинает с чистого
    # листа (для сцен 2/3 автоматически используется visual_1.png).
    character_photo_path = project_dir / "character_photo.jpg"
    if character_photo_path.exists():
        character_photo_path.unlink()

    return {
        "status": "ok",
        "video_file": "first_video.mp4"
    }
@app.get("/autopilot/video-file")
def get_video_file(channel_id: str):
    video_path = run_path(channel_id, "first_video.mp4")
    return FileResponse(
        video_path,
        media_type="video/mp4"
    )
def _download_thumbnail_bytes(thumbnail_url: str):
    try:
        with urllib.request.urlopen(thumbnail_url, timeout=10) as resp:
            return resp.read()
    except Exception:
        # Недоступный/битый thumbnail — просто пропускаем этот кандидат,
        # не роняем анализ канала целиком.
        return None


def _select_best_character_thumbnail(candidate_images: list) -> bytes:
    # candidate_images: непустой список bytes (реальные thumbnail-ы
    # последних видео канала). Просим GPT выбрать, на каком повторяющийся
    # главный персонаж виден яснее и крупнее всего. Если сравнение по
    # какой-то причине не удалось — используем лучший ДОСТУПНЫЙ вариант
    # (первый успешно скачанный thumbnail) как fallback, а не падаем.
    if len(candidate_images) == 1:
        return candidate_images[0]

    content = [{
        "type": "input_text",
        "text": (
            "Ниже — несколько превью (thumbnail) последних видео одного "
            "YouTube-канала, пронумерованные начиная с 0 в порядке показа. "
            "Выбери ОДНО превью, где повторяющийся главный персонаж канала "
            "виден наиболее ясно и крупно (хороший план лица/фигуры, "
            "персонаж не заслонён и не мелкий на фоне). Если ни один "
            "вариант не позволяет уверенно определить персонажа — всё равно "
            "выбери наиболее чёткий и крупный план из имеющихся.\n\n"
            "Ответь СТРОГО валидным JSON без markdown, ровно в формате: "
            '{"selected_index": <число>}'
        ),
    }]
    for position, image_bytes in enumerate(candidate_images):
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        content.append({"type": "input_text", "text": f"Превью {position}:"})
        content.append({
            "type": "input_image",
            "image_url": f"data:image/jpeg;base64,{base64_image}",
        })

    try:
        response = client.responses.create(
            model="gpt-5.6",
            input=[{"role": "user", "content": content}],
        )
        parsed = _parse_json_object(response.output_text)
        selected_index = parsed.get("selected_index")
        if isinstance(selected_index, int) and 0 <= selected_index < len(candidate_images):
            return candidate_images[selected_index]
    except Exception:
        pass

    # Fallback: лучший доступный вариант — первый успешно скачанный thumbnail.
    return candidate_images[0]


@app.get("/autopilot/analyze-channel")
def analyze_channel(channel: str, channel_id: str):
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
        "playlistend": 10,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel, download=False)

    entries = info.get("entries", [])[:10]
    videos = [item.get("title", "") for item in entries]
    videos_text = "\n".join(videos)

    # Реальный визуальный референс канала (общий механизм для ВСЕХ
    # каналов, ничего не зависит от конкретного имени канала):
    # берём thumbnail до 5 последних видео (уже присутствуют в flat-выдаче
    # yt_dlp — дополнительных запросов к YouTube не требуется), скачиваем
    # и просим GPT выбрать тот, где повторяющийся главный персонаж виден
    # яснее и крупнее всего, а не слепо берём первый попавшийся.
    candidate_images = []
    for item in entries[:5]:
        thumbnails = item.get("thumbnails") or []
        if not thumbnails:
            continue
        best_thumb = max(
            thumbnails,
            key=lambda t: (t.get("width") or 0) * (t.get("height") or 0),
        )
        thumbnail_url = best_thumb.get("url")
        if not thumbnail_url:
            continue
        image_bytes = _download_thumbnail_bytes(thumbnail_url)
        if image_bytes:
            candidate_images.append(image_bytes)

    visual_reference_saved = False
    if candidate_images:
        chosen_image_bytes = _select_best_character_thumbnail(candidate_images)
        channel_reference_path = character_ref_path(channel_id)
        try:
            if channel_reference_path.exists():
                # Этап 2: постоянный эталон канала не перезаписывается
                # повторным анализом — внешность персонажа фиксирована.
                visual_reference_saved = False
                return_early_bible_cleanup = False
            else:
                channel_reference_path.write_bytes(chosen_image_bytes)
                visual_reference_saved = True
                return_early_bible_cleanup = True
            # Инвалидируем старый bible этого канала: если он раньше был
            # построен из текста (или из другого, неверного изображения),
            # он не должен продолжать "стабилизировать неправильный образ".
            # Новый bible будет построен ЛЕНИВО, при следующем реальном
            # вызове /autopilot/visual-plan или /autopilot/generate-scene
            # (см. get_or_create_character_bible) — там уже известны
            # актуальные style/character с фронтенда, а приоритет источника
            # истины отдаст этому только что сохранённому реальному фото.
            bible_path = character_bible_path(channel_id)
            if return_early_bible_cleanup and bible_path.exists():
                bible_path.unlink()
        except OSError:
            visual_reference_saved = False

    response = client.responses.create(
        model="gpt-5.6",
        input=f"""
Проанализируй YouTube-канал.

Канал:
{channel}

Последние видео:
{videos_text}

Дай кратко:
1. Тематика канала
2. Стиль контента
3. Целевая аудитория
4. Повторяющиеся персонажи и визуальные образы
5. Какие темы лучше продолжать
6. Определи основной язык, на котором говорят/пишут в видео этого канала
(по названиям видео и общему контексту). В самом конце ответа, отдельной
строкой, строго в формате:
LANGUAGE: <название языка по-английски, например English/Russian/Spanish>
"""
    )
    analysis = response.output_text
    characters = ""

    if "4." in analysis and "5." in analysis:
        characters = analysis.split("4.", 1)[1].split("5.", 1)[0].strip()

    # Язык канала — отдельным полем, распознаётся по строке "LANGUAGE: ...",
    # которую модель обязана добавить в конце ответа (см. пункт 6 промпта
    # выше). Если модель по какой-то причине не проставила метку, отдаём
    # пустую строку — тогда /autopilot/start сам сделает auto-detect по
    # полному тексту analysis, как и раньше.
    language = ""
    language_match = re.search(r"LANGUAGE:\s*(.+)", analysis, re.IGNORECASE)
    if language_match:
        language = language_match.group(1).strip()

    return {
    "status": "ok",
    "channel": channel,
    "videos": videos,
    "analysis": response.output_text,
    "characters": characters,
    "language": language,
    "visual_reference_saved": visual_reference_saved,
}


# ==========================================================================
# Этапы 3-7: scene script, multi-voice TTS, timeline, scene videos, сборка
# Тонкие endpoint-ы поверх backend/pipeline.py. Старые endpoint-ы не тронуты.
# ==========================================================================

from fastapi import HTTPException  # noqa: E402


def _pipeline_error(error: pipeline.PipelineError):
    raise HTTPException(status_code=400, detail={
        "stage": error.stage,
        "message": error.message,
        "retryable": error.retryable,
        "technical_details": error.details,
    })


@app.get("/autopilot/scene-script")
def scene_script(topic: str, channel_id: str, character: str = "", style: str = ""):
    try:
        bible = get_or_create_character_bible(channel_id, character, style)
        roster = pipeline.build_character_roster(bible)
        response = client.responses.create(
            model="gpt-5.6",
            input=pipeline.scene_script_prompt(topic, bible, roster),
        )
        raw = _parse_json_object(response.output_text)
        script = pipeline.normalize_scene_script(raw, roster, channel_id=channel_id, topic=topic)
        pipeline.write_json(pipeline.scene_script_path(channel_id), script)
        return {"status": "ok", "scene_script": script}
    except pipeline.PipelineError as error:
        _pipeline_error(error)


@app.get("/autopilot/scene-script-file")
def scene_script_file(channel_id: str):
    try:
        return {"status": "ok", "scene_script": pipeline.load_scene_script(channel_id)}
    except pipeline.PipelineError as error:
        _pipeline_error(error)


@app.get("/autopilot/voice-profiles")
def voice_profiles(channel_id: str):
    try:
        script = pipeline.load_scene_script(channel_id)
        return {"status": "ok", "voice_profiles": pipeline.get_or_create_voice_profiles(channel_id, script["characters"])}
    except pipeline.PipelineError as error:
        _pipeline_error(error)


@app.get("/autopilot/scene-voice-plan")
def scene_voice_plan(channel_id: str):
    try:
        script = pipeline.load_scene_script(channel_id)
        profiles = pipeline.get_or_create_voice_profiles(channel_id, script["characters"])
        return {"status": "ok", "voice_plan": pipeline.build_voice_plan(channel_id, script, profiles)}
    except pipeline.PipelineError as error:
        _pipeline_error(error)


@app.get("/autopilot/scene-voice")
def scene_voice(channel_id: str):
    try:
        plan = pipeline.read_json(pipeline.voice_plan_path(channel_id))
        if not plan:
            script = pipeline.load_scene_script(channel_id)
            profiles = pipeline.get_or_create_voice_profiles(channel_id, script["characters"])
            plan = pipeline.build_voice_plan(channel_id, script, profiles)
        return {"status": "ok", **pipeline.synthesize_voice_plan(channel_id, plan, client)}
    except pipeline.PipelineError as error:
        _pipeline_error(error)


@app.get("/autopilot/scene-audio")
def scene_audio(channel_id: str, scene_id: int, line_id: int):
    path = pipeline.run_path(channel_id, "audio", f"scene_{scene_id:03d}_line_{line_id:03d}.mp3", create_parent=False)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Аудиоклип не найден")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/autopilot/timeline")
def timeline(channel_id: str):
    try:
        script = pipeline.load_scene_script(channel_id)
        plan = pipeline.read_json(pipeline.voice_plan_path(channel_id))
        if not plan:
            raise pipeline.PipelineError("voice_plan.json отсутствует.", stage="timeline", retryable=False)
        return {"status": "ok", "timeline": pipeline.build_timeline(channel_id, script, plan)}
    except pipeline.PipelineError as error:
        _pipeline_error(error)


@app.get("/autopilot/timeline-file")
def timeline_file(channel_id: str):
    try:
        return {"status": "ok", "timeline": pipeline.load_timeline(channel_id)}
    except pipeline.PipelineError as error:
        _pipeline_error(error)


@app.get("/autopilot/video-plan")
def video_plan(channel_id: str, provider: str = "mock"):
    try:
        script = pipeline.load_scene_script(channel_id)
        return {"status": "ok", "video_plan": pipeline.build_video_plan(
            channel_id, script, pipeline.load_timeline(channel_id), provider=provider
        )}
    except pipeline.PipelineError as error:
        _pipeline_error(error)


@app.get("/autopilot/scene-videos")
def scene_videos(channel_id: str):
    try:
        plan = pipeline.read_json(pipeline.video_plan_path(channel_id))
        if not plan:
            raise pipeline.PipelineError("video_plan.json отсутствует.", stage="scene_videos", retryable=False)
        return {"status": "ok", **pipeline.generate_scene_videos(channel_id, plan)}
    except pipeline.PipelineError as error:
        _pipeline_error(error)


@app.get("/autopilot/scene-video-file")
def scene_video_file(channel_id: str, scene_id: int):
    path = pipeline.run_path(channel_id, "video", f"scene_{scene_id:03d}.mp4", create_parent=False)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Видео сцены не найдено")
    return FileResponse(path, media_type="video/mp4")


@app.get("/autopilot/assemble-final-video")
def assemble_final_video(channel_id: str):
    try:
        plan = pipeline.read_json(pipeline.video_plan_path(channel_id))
        if not plan:
            raise pipeline.PipelineError("video_plan.json отсутствует.", stage="final_video", retryable=False)
        output = pipeline.assemble_final_video(channel_id, pipeline.load_timeline(channel_id), plan)
        return {"status": "ok", "final_video": output.name}
    except pipeline.PipelineError as error:
        _pipeline_error(error)


@app.get("/autopilot/final-video-file")
def final_video_file(channel_id: str):
    path = pipeline.final_video_path(channel_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Финальное видео не найдено")
    return FileResponse(path, media_type="video/mp4")


# ==========================================================================
# Этап 8: job status / retry / lock / orchestration
# ==========================================================================

def build_stage_runners(topic: str, character: str, style: str, provider: str = "mock") -> dict:
    """Реестр раннеров: обёртки над УЖЕ существующими функциями этапов."""

    def character_identity(channel_id: str):
        bible = get_or_create_character_bible(channel_id, character, style)
        pipeline.save_character_bible(channel_id, bible)
        if not pipeline.character_ref_path(channel_id).exists():
            raise pipeline.PipelineError(
                "Нет постоянного эталона character_ref.png — выполните анализ канала или загрузите фото.",
                stage="character_identity", retryable=False,
            )

    def scene_script_stage(channel_id: str):
        scene_script(topic=topic, channel_id=channel_id, character=character, style=style)

    def voice_plan_stage(channel_id: str):
        scene_voice_plan(channel_id=channel_id)

    def audio_stage(channel_id: str):
        scene_voice(channel_id=channel_id)

    def timeline_stage(channel_id: str):
        timeline(channel_id=channel_id)

    def video_plan_stage(channel_id: str):
        video_plan(channel_id=channel_id, provider=provider)

    def scene_videos_stage(channel_id: str):
        scene_videos(channel_id=channel_id)

    def final_video_stage(channel_id: str):
        assemble_final_video(channel_id=channel_id)

    return {
        "character_identity": character_identity,
        "scene_script": scene_script_stage,
        "voice_plan": voice_plan_stage,
        "audio_clips": audio_stage,
        "timeline": timeline_stage,
        "video_plan": video_plan_stage,
        "scene_videos": scene_videos_stage,
        "final_video": final_video_stage,
    }


@app.get("/autopilot/run-pipeline")
def run_pipeline(channel_id: str, topic: str, character: str = "", style: str = "", provider: str = "mock"):
    runners = build_stage_runners(topic, character, style, provider)
    try:
        return {"status": "ok", "job": jobs.run_autopilot_pipeline(channel_id, runners)}
    except pipeline.PipelineError as error:
        _pipeline_error(error)


@app.get("/autopilot/job-status")
def job_status(channel_id: str):
    return {"status": "ok", "job": jobs.load_job_status(channel_id)}


@app.get("/autopilot/retry-stage")
def retry_stage(channel_id: str, topic: str, character: str = "", style: str = "", provider: str = "mock"):
    runners = build_stage_runners(topic, character, style, provider)
    try:
        return {"status": "ok", "job": jobs.retry_failed_stage(channel_id, runners)}
    except pipeline.PipelineError as error:
        _pipeline_error(error)
