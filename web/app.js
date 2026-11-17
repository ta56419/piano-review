"use strict";

const $ = id => document.getElementById(id);
const state = { sample: "real", report: null, measure: null, selectedId: null, pinUntil: null, request: 0, jobTimer: null };
const video = $("performance-video");
const audio = $("controlled-audio");
const narrowRows = window.matchMedia("(max-width: 1100px)");
const LEAD_IN = 0.45;

function media() { return state.sample === "real" ? video : audio; }
function setText(id, value) { $(id).textContent = value; }
function time(seconds, decimals = 0) {
  const raw = Math.max(0, Number(seconds) || 0);
  const value = decimals ? Math.round(raw * 10 ** decimals) / 10 ** decimals : Math.floor(raw);
  const minutes = Math.floor(value / 60).toString().padStart(2, "0");
  const rest = (value % 60).toFixed(decimals).padStart(decimals ? 3 + decimals : 2, "0");
  return `${minutes}:${rest}`;
}
function add(parent, tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text != null) node.textContent = text;
  parent.append(node);
  return node;
}
function comparison() { return state.report?.comparisons.find(item => item.measure === state.measure); }
function notice(message, error = false) {
  $("notice").hidden = !message;
  $("notice").textContent = message;
  $("notice").classList.toggle("error", error);
}
function errorMessage(error) {
  return error instanceof TypeError ? "Нет связи с приложением. Проверьте, что Demo.cmd открыт." : error.message;
}

async function loadReport(sample = state.sample) {
  const request = ++state.request;
  video.pause(); audio.pause();
  state.sample = sample;
  state.report = null;
  state.selectedId = null;
  state.pinUntil = null;
  $("summary").hidden = true;
  $("analysis-details").open = false;
  for (const id of ["note-comparison", "key-findings", "measure-findings", "measure-strip", "extra-note-hint"]) $(id).replaceChildren();
  for (const id of ["verification-status", "measure-status", "excerpt-label"]) setText(id, "");
  setText("comparison-title", "Загружаем ноты…");
  $("selected-event").hidden = true;
  for (const id of ["play-button", "play-measure", "playback-position", "summary-button"]) $(id).disabled = true;
  setText("result-title", "Загружаем разбор…");
  notice("");
  video.hidden = sample !== "real";
  $("audio-description").hidden = sample !== "controlled";
  document.querySelectorAll("[data-sample]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.sample === sample)));
  setText("source-label", sample === "real" ? "Исходная запись · TikTok" : "Тестовая аудиозапись");
  try {
    const response = await fetch(`/api/report?sample=${sample}`, { cache: "no-store" });
    const report = await response.json();
    if (!response.ok) throw new Error(report.detail || "Не удалось загрузить отчёт");
    if (request !== state.request) return;
    if (report.schema_version !== 2 || !report.comparisons?.length) throw new Error("Обновите разбор: нажмите «Пересчитать».");
    state.report = report;
    state.measure = sample === "controlled" ? (report.summary.problem_measures[0] ?? report.comparisons[0].measure) : report.comparisons[0].measure;
    media().src = report.media_url;
    media().playbackRate = 1;
    setText("speed-button", "1×");
    renderOverview(); renderMeasures(); renderComparison(); renderSummary(); renderDetails();
    for (const id of ["play-button", "play-measure", "playback-position", "summary-button"]) $(id).disabled = false;
    updatePlayback(); updatePlayButton();
  } catch (error) {
    if (request === state.request) { notice(errorMessage(error), true); setText("result-title", "Отчёт пока недоступен"); }
  }
}

function findingLabel(finding) {
  return finding.title;
}
function icon(name) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  node.classList.add("icon");
  node.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(node.namespaceURI, "use");
  use.setAttribute("href", `/icons.svg#${name}`);
  node.append(use);
  return node;
}
function findingButton(parent, finding) {
  const button = add(parent, "button", `finding-link ${finding.status}`, null);
  button.dataset.findingId = finding.id;
  button.dataset.timestamp = finding.timestamp;
  add(button, "span", "", findingLabel(finding));
  add(button, "span", "finding-time", time(finding.timestamp, 2));
  button.append(icon("play"));
  button.title = "Слушать за 450 мс до ноты";
  button.addEventListener("click", () => {
    selectMeasure(finding.measure, false);
    const event = comparison()?.events.find(item => item.finding_ids.includes(finding.id));
    if (event) selectEvent(event, "observed");
    seekWithLead(finding.timestamp, finding.measure);
  });
}
function renderOverview() {
  const report = state.report;
  const summary = report.summary;
  const controlled = report.sample === "controlled";
  setText("result-title", controlled ? `${summary.accuracy?.toLocaleString("ru-RU") ?? "—"}% точности · ошибок: ${summary.error_count}` : `${summary.pitch_match_count} из ${summary.expected_note_count} нот совпали по высоте`);
  setText("verification-status", controlled ? "Тест с намеренными ошибками. Результат рассчитан по звуку." : "Точность исполнения пока не подтверждена. Отмеченные места нужно переслушать.");
  const findings = $("key-findings");
  findings.replaceChildren();
  report.findings.filter(item => item.status === "confirmed" || item.kind === "timing").forEach(item => findingButton(findings, item));
  setText("excerpt-label", `ТАКТЫ ${report.excerpt.start_measure}–${report.excerpt.end_measure}`);
}
function renderMeasures() {
  const strip = $("measure-strip");
  strip.replaceChildren();
  state.report.comparisons.forEach(item => {
    const findings = state.report.findings.filter(f => f.measure === item.measure && f.kind !== "extra");
    const button = add(strip, "button", "measure-button", item.measure);
    button.dataset.measure = item.measure;
    button.setAttribute("aria-pressed", String(item.measure === state.measure));
    button.setAttribute("aria-label", `Выбрать такт ${item.measure}`);
    button.classList.toggle("has-finding", findings.length > 0);
    button.classList.toggle("needs-review", findings.length > 0 && findings.every(f => f.status !== "confirmed"));
    button.addEventListener("click", () => selectMeasure(item.measure, true));
  });
}
function selectMeasure(number, seek) {
  if (!state.report?.comparisons.some(item => item.measure === number)) return;
  state.measure = number;
  state.selectedId = null;
  state.pinUntil = null;
  renderComparison(); renderDetails();
  document.querySelectorAll(".measure-button").forEach(button => button.setAttribute("aria-pressed", String(Number(button.dataset.measure) === number)));
  if (seek) {
    // Choosing a measure is also an inspection action; preserve pause/play.
    media().currentTime = Math.max(0, comparison().start);
    updatePlayback();
  }
}
function noteButton(row, event, side) {
  const note = event[side];
  if (!note) { add(row, "span", "missing-note", "не распознано"); return; }
  const button = add(row, "button", `note ${side} ${event.status}`, null);
  button.dataset.eventId = event.id;
  button.dataset.onset = note.onset;
  button.dataset.side = side;
  button.setAttribute("aria-label", `${side === "expected" ? "По партитуре" : "Распознано"}: ${note.name}, ${time(note.onset, 2)}. Слушать за 450 мс до ноты`);
  add(button, "span", "note-name", note.name);
  add(button, "span", "note-time", time(note.onset, 2));
  button.addEventListener("click", () => { selectEvent(event, side); seekWithLead(note.onset, state.measure); });
}
function renderComparison() {
  const measure = comparison();
  if (!measure) return;
  setText("comparison-title", `Такт ${measure.measure}`);
  $("measure-status").replaceChildren();
  add($("measure-status"), "span", "", `${measure.pitch_matches} из ${measure.reference_count} нот совпали по высоте`);
  add($("measure-status"), "span", "measure-range", `${time(measure.start, 2)}–${time(measure.end, 2)}`);
  const container = $("note-comparison");
  container.replaceChildren();
  const size = narrowRows.matches ? 4 : 8;
  for (let index = 0; index < measure.events.length; index += size) {
    const group = add(container, "div", "note-group");
    for (const side of ["expected", "observed"]) {
      const row = add(group, "div", "note-row");
      add(row, "span", "row-label", side === "expected" ? "Партитура" : "Распознано");
      measure.events.slice(index, index + size).forEach(event => noteButton(row, event, side));
    }
  }
  $("selected-event").hidden = true;
  const findings = $("measure-findings");
  findings.replaceChildren();
  state.report.findings.filter(f => f.measure === state.measure && f.kind !== "extra").forEach(f => findingButton(findings, f));
  const extraHint = $("extra-note-hint");
  extraHint.replaceChildren();
  if (measure.extra_detections.length) {
    add(extraHint, "span", "", `Ноты для проверки: ${measure.extra_detections.length}. `);
    const button = add(extraHint, "button", "", "Открыть");
    button.addEventListener("click", () => { $("analysis-details").open = true; $("extra-title").scrollIntoView({ block: "center", behavior: "smooth" }); });
  } else extraHint.textContent = "Других распознанных нот в этом такте нет.";
}
function selectEvent(event, side) {
  state.selectedId = event.id;
  const expected = event.expected;
  const observed = event.observed;
  const status = event.status === "confirmed" ? "Ошибка в тестовой записи." : event.status === "uncertain" ? "Нужно переслушать." : "Высота совпала.";
  setText("selected-event", `Такт ${state.measure} · Партитура: ${expected.name}, ${time(expected.onset, 3)} · Распознано: ${observed ? `${observed.name}, ${time(observed.onset, 3)}` : "—"}. ${status}`);
  $("selected-event").hidden = false;
  document.querySelectorAll(".note").forEach(button => button.classList.toggle("active", button.dataset.eventId === event.id && button.dataset.side === side));
}
async function play() {
  if (!state.report) return;
  const active = media();
  try { await active.play(); } catch (error) {
    if (active === media() && error.name !== "AbortError") notice("Не удалось включить запись. Нажмите воспроизведение ещё раз.", true);
  }
}
function seekWithLead(onset, measureNumber) {
  if (!state.report) return;
  state.pinUntil = onset;
  state.measure = measureNumber;
  media().currentTime = Math.max(0, onset - LEAD_IN);
  $("playback-position").dataset.lastSeekTarget = onset;
  $("playback-position").dataset.lastSeekStart = media().currentTime;
  updatePlayback();
  play();
}
function updatePlayback(followSeek = false) {
  const active = media();
  const duration = Number.isFinite(active.duration) ? active.duration : state.report?.duration || 0;
  setText("current-time", time(active.currentTime));
  setText("total-time", time(duration));
  $("playback-position").max = duration || 100;
  $("playback-position").value = active.currentTime;
  const measures = state.report?.comparisons ?? [];
  const currentMeasure = measures.find(item => active.currentTime >= item.start && active.currentTime < item.end)
    ?? (active.currentTime < measures[0]?.start ? measures[0]
      : active.currentTime >= measures.at(-1)?.end ? measures.at(-1) : null);
  setText("playback-measure", `ТАКТ ${currentMeasure?.measure ?? state.measure ?? "—"}`);
  if (state.pinUntil != null && active.currentTime >= state.pinUntil) state.pinUntil = null;
  if ((!active.paused || followSeek) && state.pinUntil == null && currentMeasure && currentMeasure.measure !== state.measure) selectMeasure(currentMeasure.measure, false);
}
function updatePlayButton() {
  const paused = media().paused;
  $("play-button").replaceChildren(icon(paused ? "play" : "pause"));
  $("play-button").setAttribute("aria-label", paused ? "Воспроизвести" : "Пауза");
}
function renderSummary() {
  const summary = state.report.summary;
  const controlled = state.sample === "controlled";
  setText("summary-score", controlled ? `${summary.accuracy?.toLocaleString("ru-RU") ?? "—"}% точности` : "Точность исполнения не подтверждена");
  const timingMeasures = [...new Set(state.report.findings.filter(f => f.kind === "timing" && f.status !== "confirmed").map(f => f.measure))];
  setText("summary-breakdown", controlled ? `Ошибок: ${summary.error_count} · Ноты: ${summary.breakdown.pitch} · Ритм: ${summary.breakdown.timing}. Такты: ${summary.problem_measures.join(", ") || "—"}.` : `Подтверждённых ошибок: ${summary.error_count}. По высоте совпали ${summary.pitch_match_count} из ${summary.expected_note_count} нот.${timingMeasures.length ? ` Переслушайте ${timingMeasures.length === 1 ? "такт" : "такты"} ${timingMeasures.join(", ")}.` : ""}`);
  $("summary-advice").replaceChildren();
  summary.advice.forEach(text => add($("summary-advice"), "li", "", text));
  setText("summary-caveat", controlled ? `${summary.expected_note_count} нот в полных тактах. Замена ноты считается одной ошибкой.` : "Ноты для проверки в число ошибок не входят.");
}
function openSummary() {
  if (!state.report) return;
  $("summary").hidden = false;
  $("summary").scrollIntoView({ behavior: "smooth", block: "start" });
}
function renderDetails() {
  if (!state.report) return;
  const report = state.report;
  const measure = comparison();
  setText("details-model", `${report.model.name} ${report.model.version} · допуск по времени ±${report.scoring.timing_tolerance_ms} мс. Рассчитано: ${new Date(report.generated_at).toLocaleString("ru-RU")}.`);
  setText("details-score", `Совпадение модели с MIDI: ${report.summary.model_agreement}%. На проверку: ${report.summary.uncertain_count}. Подтверждённых ошибок: ${report.summary.error_count}.`);
  setText("details-rule", report.scoring.description);
  const settings = report.decoder.settings;
  setText("details-decoder", `Декодер: ${report.decoder.name}; onset ${settings.onset_thresh}; infer_onsets ${settings.infer_onsets}; melodia ${settings.melodia_trick}. Число рядом с нотой — сила отклика модели, не вероятность ошибки.`);
  $("raw-link").href = report.debug.raw_detections_url;
  setText("extra-title", "Ноты для проверки");
  setText("extra-count", `Такт ${measure.measure} · ${measure.extra_detections.length}`);
  $("extra-events").replaceChildren();
  measure.extra_detections.forEach(note => {
    const button = add($("extra-events"), "button", "extra-event");
    add(button, "span", "", note.name);
    add(button, "small", "", `${time(note.onset, 2)} · ${note.confidence.toFixed(2)}`);
    button.addEventListener("click", () => seekWithLead(note.onset, measure.measure));
  });
  if (!measure.extra_detections.length) setText("extra-events", "В этом такте таких нот нет.");
  const low = measure.detected_notes.filter(note => note.confidence < .65);
  setText("low-confidence-events", `Слабый отклик модели (ниже 0,65): ${low.length}. ${low.map(note => `${note.name} ${time(note.onset, 2)} (${note.confidence.toFixed(2)})`).join("; ")}`);
  $("limitations").replaceChildren();
  report.limitations.forEach(text => add($("limitations"), "li", "", text));
}
async function recompute() {
  $("reanalyze-button").disabled = true;
  notice("Анализируем звук… Запись можно слушать.");
  const sample = state.sample;
  try {
    const response = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sample }) });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Не удалось запустить анализ");
    pollJob(body.job_id, sample);
  } catch (error) { notice(errorMessage(error), true); $("reanalyze-button").disabled = false; }
}
async function pollJob(id, sample) {
  try {
    const response = await fetch(`/api/jobs/${id}`, { cache: "no-store" });
    const job = await response.json();
    if (!response.ok || job.status === "failed") throw new Error(job.message || "Ошибка анализа");
    if (job.status === "completed") {
      if (sample === state.sample) await loadReport(sample);
      notice(sample === state.sample ? "Готово. Ноты и отчёт обновлены." :
        `${sample === "real" ? "Исходная" : "Тестовая"} запись готова. Откройте её разбор.`);
      $("reanalyze-button").disabled = false;
    } else state.jobTimer = setTimeout(() => pollJob(id, sample), 1200);
  } catch (error) { notice(errorMessage(error), true); $("reanalyze-button").disabled = false; }
}

document.querySelectorAll("[data-sample]").forEach(button => button.addEventListener("click", () => loadReport(button.dataset.sample)));
$("play-button").addEventListener("click", () => media().paused ? play() : media().pause());
$("play-measure").addEventListener("click", () => { if (comparison()) seekWithLead(comparison().start, state.measure); });
$("playback-position").addEventListener("input", event => { state.pinUntil = null; media().currentTime = Number(event.target.value); updatePlayback(true); });
$("speed-button").addEventListener("click", () => { const rates = [1, .75, .5]; media().playbackRate = rates[(rates.indexOf(media().playbackRate) + 1) % rates.length]; setText("speed-button", `${media().playbackRate.toLocaleString("ru-RU")}×`); });
$("demo-button").addEventListener("click", async () => { if (!state.report || state.sample !== "real") await loadReport("real"); if (state.report) { selectMeasure(state.report.comparisons[0].measure, false); media().currentTime = 0; play(); } });
$("summary-button").addEventListener("click", openSummary);
$("close-summary").addEventListener("click", () => { $("summary").hidden = true; $("summary-button").focus(); });
$("reanalyze-button").addEventListener("click", recompute);
narrowRows.addEventListener("change", () => { if (state.report) renderComparison(); });
for (const item of [video, audio]) {
  item.addEventListener("timeupdate", () => { if (item === media()) updatePlayback(); });
  item.addEventListener("loadedmetadata", () => { if (item === media()) updatePlayback(); });
  item.addEventListener("play", updatePlayButton);
  item.addEventListener("pause", updatePlayButton);
  item.addEventListener("ended", () => { if (item === media()) openSummary(); });
}
loadReport();
