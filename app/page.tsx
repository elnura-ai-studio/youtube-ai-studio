"use client";

import { useState, useEffect } from "react";

type Mode =
  | "home"
  | "newAuto"
  | "existingAuto"
  | "running"
  | "done";

const steps = [
  "Анализирую перспективные ниши",
  "Сравниваю спрос и конкуренцию",
  "Выбираю лучшую нишу",
  "Создаю название канала",
  "Готовлю описание и слоган",
  "Создаю логотип и баннер",
  "Формирую контент-план",
  "Выбираю тему первого ролика",
  "Пишу сценарий",
  "Готовлю озвучку и превью",
  "Подготавливаю первый ролик",
];

export default function Home() {
  const [mode, setMode] = useState<Mode>("home");
  const [currentStep, setCurrentStep] = useState(0);
const [autopilotData, setAutopilotData] = useState<any>(null);
const [script, setScript] = useState("");
const [voicePlan, setVoicePlan] = useState("");
const [selectedChannel, setSelectedChannel] = useState("");
const [customChannelName, setCustomChannelName] = useState("");
const [clientChannels, setClientChannels] = useState<string[]>([]);
const [channelUrl, setChannelUrl] = useState("");
const [channelAnalysis, setChannelAnalysis] = useState("");
// Язык канала — часть конфигурации канала, как character/style: для
// анализируемых (analyzeChannel) и пользовательских каналов определяется
// автоматически GPT по контенту канала; для preset-каналов — если язык
// известен заранее, задаётся прямо в конфиге кнопки этого канала (см.
// ниже). Пустая строка означает "определить по channel_analysis на
// бэкенде" — единообразно для всех каналов, без частных случаев.
const [channelLanguage, setChannelLanguage] = useState("");
const analyzeChannel = async () => {
  if (!channelUrl.trim()) return;

  // Снимок канала на момент запуска запроса: analyze-channel может идти
  // несколько секунд (yt-dlp + GPT), и если за это время пользователь
  // переключится на другой канал, результат ниже не должен затирать
  // "текущее" состояние уже другого, нового канала.
  const analyzedChannel = selectedChannel;
  // Тот же ключ канала, что и в generate-scene/visual-plan (см.
  // sceneChannelId) — по нему backend сохраняет реальный визуальный
  // референс (character_ref_<channel_id>.png) и character_bible именно
  // ЭТОГО канала, без смешивания с другими.
  const analyzedChannelId =
    analyzedChannel === "custom" ? customChannelName.trim() : analyzedChannel;

  const response = await fetch(
    `http://127.0.0.1:8000/autopilot/analyze-channel?channel=${encodeURIComponent(channelUrl)}&channel_id=${encodeURIComponent(analyzedChannelId)}`
  );

  const data = await response.json();

  if (selectedChannel !== analyzedChannel) {
    // Пользователь уже выбрал другой канал, пока шёл запрос — результат
    // для старого канала отбрасываем, не применяем к текущему состоянию.
    return;
  }

  setChannelAnalysis(data.analysis || "");
  setChannelCharacter(data.characters || "");
  setChannelLanguage(data.language || "");

  if (analyzedChannel && analyzedChannel !== "custom") {
    setClientChannelCharacters((prev) => ({
      ...prev,
      [analyzedChannel]: data.characters || "",
    }));
    setClientChannelLanguages((prev) => ({
      ...prev,
      [analyzedChannel]: data.language || "",
    }));
  }
};
const [channelsLoaded, setChannelsLoaded] = useState(false);
const [clientChannelStyles, setClientChannelStyles] = useState<Record<string, string>>({});
const [clientChannelKeepCharacters, setClientChannelKeepCharacters] = useState<Record<string, boolean>>({});
const [clientChannelCharacters, setClientChannelCharacters] = useState<Record<string, string>>({});
const [clientChannelCharacterModes, setClientChannelCharacterModes] =
  useState<Record<string, string>>({});
const [clientChannelDescriptions, setClientChannelDescriptions] =
  useState<Record<string, string>>({});
const [clientChannelPhotos, setClientChannelPhotos] =
  useState<Record<string, File | null>>({});
const [clientChannelLanguages, setClientChannelLanguages] =
  useState<Record<string, string>>({});

// Восстановление сохранённых каналов и их персонажей/стиля при загрузке
// страницы. Файлы фото (clientChannelPhotos) — исключение: File нельзя
// сериализовать в localStorage (там нет содержимого, только метаданные),
// поэтому сам файл после перезагрузки страницы не восстанавливается —
// в localStorage под этим ключом хранится только имя файла для справки,
// а фото нужно будет загрузить заново.
useEffect(() => {
  const savedChannels = localStorage.getItem("clientChannels");
  if (savedChannels) {
    setClientChannels(JSON.parse(savedChannels));
  }

  const savedStyles = localStorage.getItem("clientChannelStyles");
  if (savedStyles) {
    setClientChannelStyles(JSON.parse(savedStyles));
  }

  const savedCharacters = localStorage.getItem("clientChannelCharacters");
  if (savedCharacters) {
    setClientChannelCharacters(JSON.parse(savedCharacters));
  }

  const savedCharacterModes = localStorage.getItem("clientChannelCharacterModes");
  if (savedCharacterModes) {
    setClientChannelCharacterModes(JSON.parse(savedCharacterModes));
  }

  const savedDescriptions = localStorage.getItem("clientChannelDescriptions");
  if (savedDescriptions) {
    setClientChannelDescriptions(JSON.parse(savedDescriptions));
  }

  const savedKeepCharacters = localStorage.getItem("clientChannelKeepCharacters");
  if (savedKeepCharacters) {
    setClientChannelKeepCharacters(JSON.parse(savedKeepCharacters));
  }

  const savedLanguages = localStorage.getItem("clientChannelLanguages");
  if (savedLanguages) {
    setClientChannelLanguages(JSON.parse(savedLanguages));
  }

setChannelsLoaded(true);
}, []);

useEffect(() => {
  if (!channelsLoaded) return;
  localStorage.setItem("clientChannels", JSON.stringify(clientChannels));
}, [clientChannels, channelsLoaded]);

useEffect(() => {
  if (!channelsLoaded) return;
  localStorage.setItem("clientChannelStyles", JSON.stringify(clientChannelStyles));
}, [clientChannelStyles, channelsLoaded]);

useEffect(() => {
  if (!channelsLoaded) return;
  localStorage.setItem("clientChannelCharacters", JSON.stringify(clientChannelCharacters));
}, [clientChannelCharacters, channelsLoaded]);

useEffect(() => {
  if (!channelsLoaded) return;
  localStorage.setItem("clientChannelCharacterModes", JSON.stringify(clientChannelCharacterModes));
}, [clientChannelCharacterModes, channelsLoaded]);

useEffect(() => {
  if (!channelsLoaded) return;
  localStorage.setItem("clientChannelDescriptions", JSON.stringify(clientChannelDescriptions));
}, [clientChannelDescriptions, channelsLoaded]);

useEffect(() => {
  if (!channelsLoaded) return;
  localStorage.setItem("clientChannelKeepCharacters", JSON.stringify(clientChannelKeepCharacters));
}, [clientChannelKeepCharacters, channelsLoaded]);

useEffect(() => {
  if (!channelsLoaded) return;
  localStorage.setItem("clientChannelLanguages", JSON.stringify(clientChannelLanguages));
}, [clientChannelLanguages, channelsLoaded]);

useEffect(() => {
  if (!channelsLoaded) return;
  // Сохраняем только имена файлов (File не сериализуется в localStorage) —
  // это справочная информация, восстановить сам файл из неё нельзя.
  const serializablePhotoNames: Record<string, string | null> = {};
  Object.keys(clientChannelPhotos).forEach((channel) => {
    serializablePhotoNames[channel] = clientChannelPhotos[channel]?.name ?? null;
  });
  localStorage.setItem("clientChannelPhotos", JSON.stringify(serializablePhotoNames));
}, [clientChannelPhotos, channelsLoaded]);
const [clientChannelStyle, setClientChannelStyle] = useState("");
const [keepCharacters, setKeepCharacters] = useState(false);
const [characterMode, setCharacterMode] = useState("auto");
const [characterPhoto, setCharacterPhoto] = useState<File | null>(null);
const [characterDescription, setCharacterDescription] = useState("");
const [channelCharacter, setChannelCharacter] = useState("");
const [visualPlan, setVisualPlan] = useState("");
const TEST_MODE = false;
const [voicePlanLoading, setVoicePlanLoading] = useState(false);
const generateVoicePlan = async () => {

  if (!autopilotData?.first_video) return;

  setVoicePlanLoading(true);
  setVoicePlan("");

  try {
    const response = await fetch(
      `http://127.0.0.1:8000/autopilot/voice-plan?topic=${encodeURIComponent(
        autopilotData.first_video
      )}`
    );

    const data = await response.json();
    setVoicePlan(data.voice_plan);
  } catch (error) {
    console.error("Ошибка плана озвучки:", error);
  } finally {
    setVoicePlanLoading(false);
  }
};
const generateVisualPlan = async () => {
if (TEST_MODE) {
  setVisualPlan("Тестовый план визуалов без расхода API.");
  return;
}
  // 5. Те же персонажи/стиль текущего канала, что и в startAutopilot —
  // раньше этот запрос уходил вообще без character/style и затирал
  // latest_visual_plan на бэкенде пустым планом для любого канала.
  const currentCharacter =
    characterMode === "description" ? characterDescription : channelCharacter;
  const currentStyle = clientChannelStyle;
  const currentUseCharacterPhoto = characterMode === "photo";
  // Тот же ключ канала, что и в startAutopilot (см. sceneChannelId) — им
  // на бэкенде зафиксирован постоянный character bible этого канала.
  const currentChannelId =
    selectedChannel === "custom" ? customChannelName : selectedChannel;

  const response = await fetch(
    "http://127.0.0.1:8000/autopilot/visual-plan?topic=" +
      encodeURIComponent(autopilotData.first_video) +
      "&character=" +
      encodeURIComponent(currentCharacter) +
      "&style=" +
      encodeURIComponent(currentStyle) +
      "&use_character_photo=" +
      encodeURIComponent(String(currentUseCharacterPhoto)) +
      "&channel_id=" +
      encodeURIComponent(currentChannelId)
  );

  const data = await response.json();

  console.log("Visual plan:", data.visual_plan);
setVisualPlan(data.visual_plan);
};
const [scriptLoading, setScriptLoading] = useState(false);
const generateScript = async () => {
  if (!autopilotData?.first_video) return;

  setScriptLoading(true);
  setScript("");

  try {
    const response = await fetch(
      `http://127.0.0.1:8000/autopilot/script?topic=${encodeURIComponent(
        autopilotData.first_video
      )}`
    );

    const data = await response.json();
    setScript(data.script);
  } catch (error) {
    console.error("Ошибка сценария:", error);
  } finally {
    setScriptLoading(false);
  }
};
  const startAutopilot = async () => {
if (TEST_MODE) {
  const data = {
    first_video: "7 бесплатных ИИ-инструментов, которые сэкономят вам 10 часов в неделю",
  };

  setAutopilotData(data);
  setMode("done");
  setCurrentStep(0);

  setScript("Тестовый сценарий без расхода API.");
  setVoicePlan("Тестовый план озвучки без расхода API.");
  setVisualPlan("");

  return;
}
  try {
console.log("CHANNEL ANALYSIS:", channelAnalysis);
console.log("CHANNEL LANGUAGE:", channelLanguage);
    const response = await fetch(
      `http://127.0.0.1:8000/autopilot/start?channel_analysis=${encodeURIComponent(channelAnalysis)}&channel_language=${encodeURIComponent(channelLanguage)}`
    );

    const data = await response.json();
setAutopilotData(data);
setMode("running");
setCurrentStep(0);
let step = 0;

const interval = setInterval(() => {
  step += 1;

  if (step >= steps.length) {
    clearInterval(interval);
    
    return;
  }

  setCurrentStep(step);
}, 900);
const topic = data.first_video;
const scriptResponse = await fetch(
  `http://127.0.0.1:8000/autopilot/script?topic=${encodeURIComponent(topic)}`
);

const scriptData = await scriptResponse.json();
setScript(scriptData.script);
await fetch(
  `http://127.0.0.1:8000/autopilot/voice?text=${encodeURIComponent(
    scriptData.script
  )}`
);
const voiceResponse = await fetch(
  `http://127.0.0.1:8000/autopilot/voice-plan?topic=${encodeURIComponent(topic)}`
);

const voiceData = await voiceResponse.json();
setVoicePlan(voiceData.voice_plan);
// Персонажи и стиль ТЕКУЩЕГО канала — считаем один раз и используем
// во всех запросах ниже (visual-plan и все три generate-scene), чтобы
// они гарантированно совпадали и не могли разъехаться между вызовами.
const sceneCharacter =
  characterMode === "description" ? characterDescription : channelCharacter;
const sceneStyle = clientChannelStyle;
// Явный признак режима фото ДЛЯ ТЕКУЩЕГО канала — чтобы backend не решал
// использовать character_photo.jpg просто по факту его наличия на диске
// (файл от предыдущего канала мог остаться, если тот прогон не дошёл до
// build-video). true только если для этого канала реально выбран режим
// "Загрузить фото персонажей".
const useCharacterPhoto = characterMode === "photo";
// Идентификатор канала для постоянного reference-изображения персонажей
// на бэкенде (character_ref_<channel_id>.png) — тот же "ключ канала",
// который уже используется для остальных per-channel словарей на
// фронтенде (имя custom-канала или id preset-канала).
const sceneChannelId =
  selectedChannel === "custom" ? customChannelName : selectedChannel;

const visualResponse = await fetch(
  "http://127.0.0.1:8000/autopilot/visual-plan?topic=" +
    encodeURIComponent(topic) +
    "&character=" +
    encodeURIComponent(sceneCharacter) +
    "&style=" +
    encodeURIComponent(sceneStyle) +
    "&use_character_photo=" +
    encodeURIComponent(String(useCharacterPhoto)) +
    "&channel_id=" +
    encodeURIComponent(sceneChannelId)
);

const visualData = await visualResponse.json();

console.log("Visual plan:", visualData.visual_plan);
console.log("Character mode:", characterMode);
console.log("Character description:", characterDescription);
console.log("Style:", sceneStyle);
setVisualPlan(visualData.visual_plan);
console.log("START SCENE 1");
// 6. character/style текущего канала передаются в каждый generate-scene —
// раньше сцена опиралась только на latest_visual_plan на бэкенде.
// use_character_photo — явный признак режима фото ДЛЯ ЭТОГО канала, чтобы
// backend не подхватывал чужое фото по факту его наличия на диске.
const sceneQuery =
  "?character=" + encodeURIComponent(sceneCharacter) +
  "&style=" + encodeURIComponent(sceneStyle) +
  "&use_character_photo=" + encodeURIComponent(String(useCharacterPhoto)) +
  "&keep_characters=" + encodeURIComponent(String(keepCharacters)) +
  "&channel_id=" + encodeURIComponent(sceneChannelId);
await fetch("http://127.0.0.1:8000/autopilot/generate-scene/1" + sceneQuery);
console.log("DONE SCENE 1");
await fetch("http://127.0.0.1:8000/autopilot/generate-scene/2" + sceneQuery);
await fetch("http://127.0.0.1:8000/autopilot/generate-scene/3" + sceneQuery);
await fetch("http://127.0.0.1:8000/autopilot/build-video");
setMode("done");
    console.log("Данные backend:", data);

    

   
  } catch (error) {
    console.error("Ошибка backend:", error);
    alert("Не удалось подключиться к backend");
  }
};

     

  if (mode === "running") {
    const progress = Math.round(
      ((currentStep + 1) / steps.length) * 100
    );

    return (
      <main className="min-h-screen bg-black text-white flex items-center justify-center p-6">
        <div className="w-full max-w-3xl">
          <div className="mb-10 text-center">
            <div className="text-6xl mb-5">🤖</div>

            <h1 className="text-4xl font-bold mb-3">
              Автопилот работает
            </h1>

            <p className="text-zinc-400">
              Софт сам готовит новый YouTube-канал.
            </p>
          </div>

          <div className="rounded-3xl border border-zinc-700 bg-zinc-900 p-7">
            <div className="flex justify-between mb-4">
              <span className="text-zinc-400">
                Прогресс
              </span>

              <span className="font-semibold">
                {progress}%
              </span>
            </div>

            <div className="w-full h-3 bg-zinc-800 rounded-full overflow-hidden mb-8">
              <div
                className="h-full bg-white transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>

            <div className="space-y-3">
              {steps.map((step, index) => (
                <div
                  key={step}
                  className={`rounded-xl border p-4 ${
                    index < currentStep
                      ? "border-zinc-700 bg-zinc-950 text-zinc-400"
                      : index === currentStep
                      ? "border-white bg-zinc-800"
                      : "border-zinc-800 bg-black text-zinc-600"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div>
                      {index < currentStep
                        ? "✓"
                        : index === currentStep
                        ? "●"
                        : "○"}
                    </div>

                    <div>{step}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    );
  }

  if (mode === "done") {
    return (
      <main className="min-h-screen bg-black text-white p-6">
        <div className="max-w-4xl mx-auto py-12">
          <div className="text-center mb-10">
            <div className="text-6xl mb-5">✅</div>

            <h1 className="text-4xl font-bold mb-3">
              Канал подготовлен
            </h1>

            <p className="text-zinc-400">
              Это пока демонстрация автопилота. Позже подключим реальные AI и
              YouTube API.
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-6 mb-8">
            <div className="rounded-3xl border border-zinc-700 bg-zinc-900 p-6">
              <div className="text-zinc-500 mb-2">
                Выбранная ниша
              </div>

              <h2 className="text-2xl font-semibold">
               {autopilotData?.niche ?? "AI-инструменты для начинающих"}
              </h2>
            </div>

            <div className="rounded-3xl border border-zinc-700 bg-zinc-900 p-6">
              <div className="text-zinc-500 mb-2">
                Название канала
              </div>

              <h2 className="text-2xl font-semibold">
                {autopilotData?.channel_name ?? "AI Start Lab"}
              </h2>
            </div>
          </div>

          <div className="rounded-3xl border border-zinc-700 bg-zinc-900 p-6 mb-8">
            <h2 className="text-2xl font-semibold mb-4">
              Что автопилот подготовил
            </h2>

            <div className="space-y-3 text-zinc-300">
              <p>✓ Ниша канала</p>
              <p>✓ Название</p>
              <p>✓ Описание</p>
              <p>✓ Слоган</p>
              <p>✓ Макет логотипа</p>
              <p>✓ Макет баннера</p>
              <p>✓ Контент-план</p>
              <p>✓ Тема первого ролика</p>
              <p>✓ Сценарий</p>
              <p>✓ План озвучки</p>
              <p>✓ Идея превью</p>
            </div>
          </div>

          <div className="rounded-3xl border border-zinc-700 bg-zinc-900 p-6 mb-8">
            <div className="text-zinc-500 mb-2">
              Первый ролик
            </div>

            <h2 className="text-2xl font-semibold mb-3">
              {autopilotData?.first_video ?? "5 бесплатных AI-инструментов, которые экономят часы работы"}
            </h2>

            <p className="text-zinc-400">
              Следующим этапом подключим настоящую генерацию сценария,
              озвучки, визуалов и сборку видео.
            </p>
          </div>

          <button
            onClick={() => setMode("home")}           
 className="w-full rounded-xl bg-white text-black font-semibold p-4 mb-4"
          >
            Вернуться на главный экран

</button>
<button
  onClick={generateScript}
  
  className="w-full rounded-xl bg-white text-black font-semibold p-4 mb-4"
>
  Сгенерировать сценарий
</button>
{script && (
  <div className="mt-4 rounded-xl border border-zinc-700 bg-zinc-900 p-4 text-left whitespace-pre-wrap">
    <h3 className="font-semibold mb-2">Сценарий</h3>
    <p>{script}</p>
  </div>
)}

 <div className="flex flex-col gap-4">
  <button
    onClick={generateVoicePlan}
    className="w-full rounded-xl bg-white text-black font-semibold py-4"
  >
    Создать план озвучки
  </button>

  <button
onClick={generateVisualPlan}
    className="w-full rounded-xl bg-white text-black font-semibold py-4"
  >
Создать план визуалов
</button>

<button
onClick={async () => {
  await fetch("http://127.0.0.1:8000/autopilot/build-video");
  alert("Видео готово!");
}}
  className="w-full rounded-xl bg-white text-black font-semibold py-4"
>
  Собрать видео

</button>

{visualPlan && (
  <div className="mt-4 rounded-xl border border-zinc-700 bg-zinc-900 p-4 text-left whitespace-pre-wrap">
    <h3 className="font-semibold mb-2">План визуалов</h3>
    <p>{visualPlan}</p>
<div className="mt-4">
  <img
    src="http://127.0.0.1:8000/autopilot/visual-image-file"
    alt="Первый визуал"
    className="w-full rounded-xl"
  />
</div>
<div className="mt-4">
  <video
    controls
    className="w-full rounded-xl"
    src="http://127.0.0.1:8000/autopilot/video-file"
  />
</div>
  </div>
)}
</div>
  {voicePlan && (<div className="mt-4 rounded-xl border border-zinc-700 bg-zinc-900 p-4 text-left whitespace-pre-wrap">
    <h3 className="font-semibold mb-2">План озвучки</h3>
    <p>{voicePlan}</p>
<div className="mt-4">
  <audio controls className="w-full">
    <source
      src="http://127.0.0.1:8000/autopilot/audio"
      type="audio/mpeg"
    />
   </audio>
 </div>
  </div>
)}
    </div>
      </main>
    );
  }

  if (mode === "newAuto") {
    return (
      <main className="min-h-screen bg-black text-white flex items-center justify-center p-6">
        <div className="w-full max-w-2xl">
          <button
            onClick={() => setMode("home")}
            className="mb-8 text-zinc-400 hover:text-white"
          >
            ← Назад
          </button>

          <div className="text-6xl mb-6">
            🤖
          </div>

          <h1 className="text-4xl font-bold mb-3">
            Новый канал — Автопилот
          </h1>

          <p className="text-zinc-400 mb-8">
            Софт сам выберет нишу, создаст бренд, подготовит контент-план и
            первый ролик.
          </p>

          <div className="rounded-3xl border border-zinc-700 bg-zinc-900 p-6 mb-8">
            <h2 className="text-xl font-semibold mb-4">
              Автопилот сделает сам
            </h2>

            <div className="space-y-3 text-zinc-300">
              <p>✓ Анализ ниш</p>
              <p>✓ Выбор лучшей ниши</p>
              <p>✓ Название канала</p>
              <p>✓ Описание и слоган</p>
              <p>✓ Логотип и баннер</p>
              <p>✓ Контент-план</p>
              <p>✓ Первый сценарий</p>
              <p>✓ Подготовка первого ролика</p>
            </div>
          </div>

          <button
            onClick={startAutopilot}
            className="w-full rounded-xl bg-white text-black font-semibold p-4"
          >
            Запустить автопилот
          </button>
        </div>
      </main>
    );
  }

  if (mode === "existingAuto") {
    return (
      <main className="min-h-screen bg-black text-white flex items-center justify-center p-6">
        <div className="w-full max-w-2xl text-center">
          <button
            onClick={() => setMode("home")}
            className="mb-8 text-zinc-400 hover:text-white"
          >
            ← Назад
          </button>

          <div className="text-6xl mb-6">
            📊
          </div>

          <h1 className="text-4xl font-bold mb-3">
            Существующий канал — Автопилот
          </h1>
<div className="mb-6 space-y-3">
  <button
  onClick={() => {
  setSelectedChannel("3d");
  setChannelCharacter(
    "Sabrina — маленькая девочка с коричневыми волосами в двух косичках, большими карими глазами и фиолетовым платьем. Unico — маленький белый единорог с большими глазами, радужной гривой и хвостом. Всегда сохранять одинаковые лица, прически, цвета, одежду, пропорции и общий 3D-мультяшный стиль во всех новых сценах."
  );
  setCharacterMode("auto");
  setCharacterDescription("");
  setCharacterPhoto(null);
  setClientChannelStyle("3d");
  setKeepCharacters(true);
  // Язык этого канала известен заранее (обучающий англоязычный канал) —
  // задаётся здесь же, как часть конфигурации канала, точно так же, как
  // character/style выше. Для каналов, у которых язык заранее не известен,
  // это поле просто остаётся "" (см. другие кнопки ниже) — auto-detect.
  setChannelLanguage("English");
}}
  className="w-full rounded-xl bg-zinc-900 border border-zinc-700 p-4 text-left"
>
    Sabrina & Unico | ABC English
  </button>

  <button 
  onClick={() => {
  setSelectedChannel("real-cats");
  setChannelCharacter("");
  setCharacterMode("auto");
  setCharacterDescription("");
  setCharacterPhoto(null);
  setClientChannelStyle("realistic");
  setKeepCharacters(false);
  setChannelLanguage("");
}}
 className="w-full rounded-xl bg-zinc-900 border border-zinc-700 p-4 text-left">
   cuteKittenStories2023
  </button>

  <button onClick={() => {
  setSelectedChannel("2d");
  setChannelCharacter(
    "Постоянные главные персонажи Little Friends Stories: маленькая девочка с каштановыми волосами, большими выразительными глазами и фиолетовой одеждой, и маленький коричневый медвежонок. Всегда сохранять одинаковые лица, прически, цвета одежды, пропорции, внешний вид медвежонка и общий яркий 2D-мультяшный стиль во всех новых сценах."
  );
  setCharacterMode("auto");
  setCharacterDescription("");
  setCharacterPhoto(null);
  setClientChannelStyle("2d");
  setKeepCharacters(true);
  setChannelLanguage("");
}} className="w-full rounded-xl bg-zinc-900 border border-zinc-700 p-4 text-left">
    Little Friends Stories
 </button>
<button
  onClick={() => {
    setSelectedChannel("custom");
    setChannelCharacter("");
setCharacterDescription("");
setCharacterPhoto(null);
setKeepCharacters(false);
setCharacterMode("auto");
setClientChannelStyle("");
setChannelLanguage("");
  }}
  className="w-full rounded-xl bg-zinc-900 border border-zinc-700 p-4 text-left"
>
  Другой канал
</button>
<button
onClick={() => {
  setSelectedChannel("custom");
setCharacterDescription("");

  if (customChannelName.trim()) {
    setClientChannels((prev) => [...prev, customChannelName.trim()]);
setClientChannelStyles((prev) => ({
  ...prev,
  [customChannelName.trim()]: clientChannelStyle,
}));
setClientChannelKeepCharacters((prev) => ({
  ...prev,
  [customChannelName.trim()]: keepCharacters,
}));
setClientChannelCharacterModes((prev) => ({
  ...prev,
  [customChannelName.trim()]: characterMode,
}));
setClientChannelDescriptions((prev) => ({
  ...prev,
  [customChannelName.trim()]: characterDescription,
}));
setClientChannelPhotos((prev) => ({
  ...prev,
  [customChannelName.trim()]: characterPhoto,
}));
setClientChannelCharacters((prev) => ({
  ...prev,
  [customChannelName.trim()]: channelCharacter,
}));
setClientChannelLanguages((prev) => ({
  ...prev,
  [customChannelName.trim()]: channelLanguage,
}));
setClientChannelStyle("");
setKeepCharacters(false);
setCharacterMode("auto");
setCharacterPhoto(null);
setChannelCharacter("");
setChannelLanguage("");
setCustomChannelName("");

  }
}}
  className="w-full rounded-xl bg-zinc-800 border border-zinc-600 p-4 text-left"
>
  + Добавить канал
</button>
{clientChannels.length > 0 && (
  <div className="mt-4 space-y-2">
    {clientChannels.map((channel, index) => (
  <div key={`${channel}-${index}`} className="flex gap-2">
    <button
      onClick={() => {
        setSelectedChannel(channel);
setClientChannelStyle(clientChannelStyles[channel] || "");
setKeepCharacters(clientChannelKeepCharacters[channel] || false);
setCharacterMode(clientChannelCharacterModes[channel] || "auto");
setCharacterDescription(clientChannelDescriptions[channel] || "");
setCharacterPhoto(clientChannelPhotos[channel] || null);
setChannelCharacter(clientChannelCharacters[channel] || "");
setChannelLanguage(clientChannelLanguages[channel] || "");
      }}
      className="flex-1 rounded-xl bg-zinc-900 border border-zinc-700 p-4 text-left"
    >
      {channel}
    </button>

    <button
      onClick={() =>
        setClientChannels((prev) => prev.filter((_, i) => i !== index))
      }
      className="rounded-xl border border-zinc-700 px-4"
    >
      Удалить
    </button>
  </div>
))}
  </div>
)}
 </div> 
{(selectedChannel === "custom" || clientChannels.includes(selectedChannel)) && (
<>
 <input
  type="text"
  value={customChannelName}
  onChange={(e) => setCustomChannelName(e.target.value)}
  placeholder="Введите название канала"
  className="w-full mb-6 rounded-xl bg-zinc-900 border border-zinc-700 p-4 text-white"
/>

<div className="mb-6">
  <p className="mb-2 text-sm text-zinc-400">Стиль канала</p>

  <select
    value={clientChannelStyle}
    onChange={(e) => setClientChannelStyle(e.target.value)}
    className="w-full rounded-xl bg-zinc-900 border border-zinc-700 p-4 text-white"
  >
    <option value="">Выберите стиль</option>
    <option value="3d">3D-мультфильм</option>
    <option value="2d">2D-мультфильм</option>
    <option value="realistic">Реалистичный</option>
  </select>
</div>
<label className="mb-6 flex items-center gap-3">
  <input
    type="checkbox"
    checked={keepCharacters}
    onChange={(e) => setKeepCharacters(e.target.checked)}
  />
  <span>Сохранять постоянных персонажей</span>
</label>
{keepCharacters && (
  <div className="mb-6">
    <p className="mb-2 text-sm text-zinc-400">
      Как сохранить персонажей
    </p>

  <select
  value={characterMode}
  onChange={(e) => setCharacterMode(e.target.value)}
  className="w-full rounded-xl bg-zinc-900 border border-zinc-700 p-4"
>
  <option value="auto">Автоанализ канала</option>
  <option value="photo">Загрузить фото персонажей</option>
  <option value="description">Описать персонажей</option>
</select>

{characterMode === "auto" && (
  <div className="mt-4">
    <input
      type="text"
      placeholder="Ссылка на YouTube-канал"
      value={channelUrl}
      onChange={(e) => setChannelUrl(e.target.value)}
      className="w-full rounded-xl bg-zinc-900 border border-zinc-700 p-4"
    />

    <div className="mt-4">
      <button
        onClick={analyzeChannel}
        className="rounded-xl border border-zinc-700 px-4 py-3"
      >
        Анализировать канал
      </button>
{channelAnalysis && (
  <div className="mt-4 whitespace-pre-wrap text-left text-sm">
    {channelAnalysis}
  </div>
)}
    </div>
  </div>
)}
{characterMode === "photo" && (
  <input
    type="file"
    accept="image/*"
    onChange={async (e) => {
  const file = e.target.files?.[0] || null;
if (file) {
  const formData = new FormData();
  formData.append("file", file);

  await fetch("http://127.0.0.1:8000/autopilot/upload-character-photo", {
    method: "POST",
    body: formData,
  });
}
  setCharacterPhoto(file);

  if (selectedChannel && selectedChannel !== "custom") {
    setClientChannelPhotos((prev) => ({
      ...prev,
      [selectedChannel]: file,
    }));
  }
}}
    className="mt-3 w-full rounded-xl border border-zinc-700 p-4"
  />
)}
{characterMode === "photo" && characterPhoto && (
  <p className="mt-2 text-sm text-green-400">
    Сохранено фото: {characterPhoto.name}
  </p>
)}
{characterMode === "description" && (
  <textarea
    placeholder="Опишите персонажей: внешность, одежду, цвета, особенности..."
    className="mt-3 w-full rounded-xl border border-zinc-700 bg-zinc-900 p-4 text-white"
value={characterDescription}
onChange={(e) => {
  const value = e.target.value;
  setCharacterDescription(value);

  if (selectedChannel && selectedChannel !== "custom") {
    setClientChannelDescriptions((prev) => ({
      ...prev,
      [selectedChannel]: value,
    }));
  }
}}
    rows={4}
  />
)}
  </div>
)}
</>
)}
{selectedChannel && (
  <p className="mb-6 text-green-400">
    Выбран канал: {selectedChannel === "custom" ? customChannelName : selectedChannel}
  </p>
)}
<p className="text-zinc-400 mb-8">
            Позже подключим YouTube. Софт проанализирует старые ролики и сам
            будет выбирать следующие темы.
          </p>

          <button
  onClick={() => {
  startAutopilot();
}}
  className="rounded-xl bg-white text-black font-bold px-6 py-3"
>
  Запустить автопилот
</button>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-black text-white flex items-center justify-center p-6">
      <div className="w-full max-w-4xl text-center">
        <div className="text-6xl mb-5">
          🤖
        </div>

        <h1 className="text-5xl font-bold mb-4">
          YouTube AI Autopilot
        </h1>

        <p className="text-zinc-400 text-lg mb-12">
          AI-система, которая помогает автоматически создавать и развивать
          YouTube-каналы.
        </p>

        <div className="grid gap-6 md:grid-cols-2">
          <button
            onClick={() => setMode("newAuto")}
            className="rounded-3xl border border-zinc-700 bg-zinc-900 p-8 text-left hover:bg-zinc-800 transition"
          >
            <div className="text-4xl mb-4">
              🚀
            </div>

            <h2 className="text-2xl font-semibold mb-2">
              Новый канал
            </h2>

            <p className="text-zinc-400">
              Автопилот сам анализирует нишу, создаёт бренд и готовит контент.
            </p>
          </button>

          <button
            onClick={() => setMode("existingAuto")}
            className="rounded-3xl border border-zinc-700 bg-zinc-900 p-8 text-left hover:bg-zinc-800 transition"
          >
            <div className="text-4xl mb-4">
              📈
            </div>

            <h2 className="text-2xl font-semibold mb-2">
              Существующий канал
            </h2>

            <p className="text-zinc-400">
              Автопилот анализирует канал и сам выбирает, какие ролики делать
              дальше.
            </p>
          </button>
        </div>
      </div>
    </main>
  );
}