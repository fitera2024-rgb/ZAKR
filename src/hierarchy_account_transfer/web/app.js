const state = { inspection: null, runId: null, summary: null };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function busy(value) { $("#loader").classList.toggle("hidden", !value); }
function notify(message, error = false) {
  const box = $("#notice"); box.textContent = message; box.className = `notice${error ? " error" : ""}`;
  setTimeout(() => box.classList.add("hidden"), 5000);
}
async function request(url, options = {}) {
  const response = await fetch(url, options); let payload;
  try { payload = await response.json(); } catch { payload = { detail: "Некорректный ответ сервера" }; }
  if (!response.ok) throw new Error(payload.detail || `Ошибка HTTP ${response.status}`);
  return payload;
}
function showPanel(name) {
  $$(".panel").forEach((panel) => panel.classList.toggle("active", panel.id === `${name}-panel`));
  const order = ["upload", "selection", "results"], current = order.indexOf(name);
  $$(".step").forEach((step, index) => { step.classList.toggle("active", index === current); step.classList.toggle("done", index < current); step.disabled = index > current || (index === 1 && !state.inspection) || (index === 2 && !state.runId); });
  window.scrollTo({ top: 260, behavior: "smooth" });
}
function monthBounds(periods) {
  const sorted = [...periods].sort(); if (!sorted.length) return ["", ""];
  const last = sorted.at(-1).split("-").map(Number); const end = new Date(Date.UTC(last[0], last[1], 0)).toISOString().slice(0, 10);
  return [`${sorted[0]}-01`, end];
}
function renderInspection(data) {
  $("#root").innerHTML = data.available_roots.map((root) => `<option value="${escapeHtml(root.code)}">${escapeHtml(root.name)} · ${escapeHtml(root.code)}</option>`).join("");
  $("#scenario").innerHTML = data.available_scenarios.map((value) => `<option>${escapeHtml(value)}</option>`).join("");
  const [from, to] = monthBounds(data.available_periods); $("#date-from").value = from; $("#date-to").value = to;
  $("#inspection-meta").textContent = `${data.source_files.length} файл(а) · ${data.available_accounts.length} счетов · ${data.available_periods.length} периодов`;
  updateScopeHint();
  $("#account-list").innerHTML = data.available_accounts.map((a) => `<label class="account"><input type="checkbox" value="${escapeHtml(a.account)}"><b>${escapeHtml(a.account)}</b><small>Дт ${a.debit_row_count} · Кт ${a.credit_row_count}</small></label>`).join("");
}
function updateScopeHint() { const selected = state.inspection?.available_roots.find((root) => root.code === $("#root").value); $("#scope-hint").textContent = selected ? `В область войдут ${selected.included_node_count} узлов: корень и все потомки` : ""; }
function escapeHtml(value) { const node = document.createElement("span"); node.textContent = String(value ?? ""); return node.innerHTML; }
function renderSummary(summary) {
  const cards = [["READY", summary.ready_count, "ready"], ["BLOCKED", summary.blocked_count, "blocked"], ["REVIEW", summary.review_count, ""], ["EXCLUDED", summary.excluded_count, ""]];
  $("#metrics").innerHTML = cards.map(([label, value, kind]) => `<div class="metric ${kind}"><span>${label}</span><strong>${value}</strong></div>`).join("");
  const status = $("#run-status"); status.textContent = summary.run_status; status.className = `status ${summary.run_status.toLowerCase()}`;
  $("#control-download").href = `/api/v1/runs/${state.runId}/artifacts/run_control.xlsx`;
  const allowed = summary.ready_count > 0 && summary.blocked_count === 0;
  $("#export-button").disabled = !allowed;
  $("#export-explanation").textContent = allowed ? `${summary.ready_count} проводок прошли все проверки и готовы к выгрузке.` : "Экспорт заблокирован: устраните причины в диагностике. Контрольный отчёт уже доступен.";
}
async function loadBlockers() {
  try { const rows = await request(`/api/v1/runs/${state.runId}/pair-candidates`); $("#blocker-rows").innerHTML = rows.length ? rows.map((b) => `<tr><td>${escapeHtml(b.code)}</td><td>${escapeHtml(b.description)}</td><td>${escapeHtml(b.period)}</td><td>${escapeHtml(b.account)}</td><td>${escapeHtml(b.analytics.department_code)}</td><td>${escapeHtml(b.amount)}</td></tr>`).join("") : `<tr><td class="empty" colspan="6">Блокировок нет — глобальные инварианты выполнены</td></tr>`; } catch (error) { notify(error.message, true); }
}
$$('input[type="file"]').forEach((input) => input.addEventListener("change", () => { const names = [...input.files].map((file) => file.name); input.closest(".dropzone").classList.toggle("has-file", names.length > 0); input.closest(".dropzone").querySelector("output").textContent = names.join(", "); }));
$("#upload-form").addEventListener("submit", async (event) => { event.preventDefault(); busy(true); try { const form = new FormData(event.currentTarget); state.inspection = await request("/api/v1/inspect", { method: "POST", body: form }); renderInspection(state.inspection); showPanel("selection"); notify("Файлы проверены. Выберите область анализа."); } catch (error) { notify(error.message, true); } finally { busy(false); } });
$("#analysis-form").addEventListener("submit", async (event) => { event.preventDefault(); const selected = $$('.account input:checked').map((input) => input.value); if (!selected.length) return notify("Выберите хотя бы один точный счёт.", true); busy(true); try { const body = { inspection_id: state.inspection.inspection_id, root_organization_code: $("#root").value, selected_accounts: selected, scenario: $("#scenario").value, date_from: $("#date-from").value, date_to: $("#date-to").value }; const response = await request("/api/v1/runs/analyze", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }); state.runId = response.run_id; state.summary = response.summary; renderSummary(response.summary); await loadBlockers(); showPanel("results"); } catch (error) { notify(error.message, true); } finally { busy(false); } });
$("#account-search").addEventListener("input", (event) => $$(".account").forEach((item) => item.hidden = !item.textContent.toLowerCase().includes(event.target.value.toLowerCase())));
$("#root").addEventListener("change", updateScopeHint);
$("#export-button").addEventListener("click", async () => { busy(true); try { const manifest = await request(`/api/v1/runs/${state.runId}/export`, { method: "POST" }); $("#export-files").innerHTML = manifest.files.map((file) => `<a class="secondary button" href="/api/v1/runs/${state.runId}/export-files/${encodeURIComponent(file)}">Скачать ${escapeHtml(file)}</a>`).join(""); notify("Выгрузка сформирована."); } catch (error) { notify(error.message, true); } finally { busy(false); } });
$("#refresh-blockers").addEventListener("click", loadBlockers);
$$('[data-back]').forEach((button) => button.addEventListener("click", () => showPanel(button.dataset.back)));
$$('.step').forEach((button) => button.addEventListener("click", () => !button.disabled && showPanel(button.dataset.step)));
