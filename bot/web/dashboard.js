"use strict";

let token = "", servers = [], selectedServer = null, requestCursor = null;
let requestVersion = 0, memoryOffset = null, nicknameOffset = null;
let healthLoading = false, healthVersion = 0;
const $ = id => document.getElementById(id);
const notice = message => { $("notice").textContent = message; };
let pageServerId = new URLSearchParams(location.search).get("server");
let selectedServerPanel = new URLSearchParams(location.search).get("panel") || "main";
let commandHistoryCursor = null, commandHistoryVersion = 0;
const serverWindows = new Map();
const serverWindowTimers = new Map();
const apiCache = new Map(), apiPending = new Map();
let cacheRevision = 0, lastServerRender = "", overviewScrollY = 0;
function invalidateApiCache() { cacheRevision++; apiCache.clear(); apiPending.clear(); }
function apiTTL(path) {
  if (path === "/api/servers" || path === "/api/overview") return 15000;
  if (/^\/api\/servers\/\d+\/(details|summary)(\?|$)/.test(path)) return 60000;
  if (/^\/api\/servers\/\d+\/(requests|command-history|commands|insights)(\?|$)/.test(path)) return 10000;
  return 0;
}
async function api(path, options = {}) {
  const method = options.method || "GET", ttl = method === "GET" ? apiTTL(path) : 0;
  const key = `${token}:${path}`, cached = apiCache.get(key);
  if (ttl && cached && cached.expires > Date.now()) return cached.data;
  if (ttl && apiPending.has(key)) return apiPending.get(key);
  const revision = cacheRevision;
  const task = fetchApi(path, options).then(data => {
    if (method !== "GET") invalidateApiCache();
    else if (ttl && revision === cacheRevision) {
      if (apiCache.size >= 128) apiCache.delete(apiCache.keys().next().value);
      apiCache.set(key, {expires: Date.now() + ttl, data});
    }
    return data;
  }).finally(() => { if (apiPending.get(key) === task) apiPending.delete(key); });
  if (ttl) apiPending.set(key, task);
  return task;
}
function saveOverviewSnapshot(data) {
  if (document.body.dataset.localDashboard !== "true") return;
  try { sessionStorage.setItem("meyaya:overview", JSON.stringify({at: Date.now(), data})); } catch (_) {}
}
function restoreOverviewSnapshot() {
  try {
    const snapshot = JSON.parse(sessionStorage.getItem("meyaya:overview"));
    if (snapshot && Date.now() - snapshot.at < 300000 && Array.isArray(snapshot.data?.servers)) {
      applyServerData(snapshot.data);
      $("connection").textContent = "● Showing recent data · updating…";
    }
  } catch (_) {}
}

async function fetchApi(path, options = {}) {
  const session = token;
  const response = await fetch(path, {signal: AbortSignal.timeout(20000), ...options, headers: {"Authorization": `Bearer ${token}`, "Content-Type": "application/json"}});
  if (token !== session) throw new Error("Dashboard locked. Sign in again.");
  if (!response.ok) {
    if (response.status === 401) lock();
    const detail = await response.text();
    throw new Error(response.status === 401 ? "Session expired. Sign in again with uwu owner or your access token." : detail || `Request failed (${response.status}).`);
  }
  const data = await response.json();
  if (token !== session) throw new Error("Dashboard locked. Sign in again.");
  return data;
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function metric(label, value) {
  const node = element("div");
  node.append(element("span", label), element("b", String(value)));
  return node;
}

const known = value => value === null || value === undefined ? "Unavailable" : String(value);
const channelTypes = {0: "Text", 2: "Voice", 4: "Category", 5: "Announcements", 10: "Announcement thread", 11: "Thread", 12: "Private thread", 13: "Stage", 15: "Forum", 16: "Media"};

function renderServerDetails(target, data) {
    target.replaceChildren();
  if (data.stale) target.append(element("p", "Last-known information. Live Discord details are unavailable; saved records are retained.", "details"));
  const facts = element("div", undefined, "metrics server-facts");
  const channelName = id => id ? `${data.channels?.find(c => c.id === id)?.name || "Channel"} (${id})` : "Not set";
  for (const [label, value] of [
    ["Owner", data.owner_name || "Unavailable"], ["Owner username", data.owner_username], ["Owner ID", data.owner_id],
    [data.members_approximate ? "Members (approx.)" : "Total members", data.members], ["Online (approx.)", data.online_members],
    ["Created", data.created_at ? new Date(data.created_at).toLocaleString() : null],
    ["Bot joined", data.bot_joined_at ? new Date(data.bot_joined_at).toLocaleString() : null],
    ["Locale", data.locale],
    ["Channels", data.channels?.length], ["Roles", data.roles?.length],
    ["Vanity invite code", data.vanity_code],
  ]) facts.append(metric(label, known(value)));
  if (data.description) target.append(element("p", data.description, "details"));
  target.append(facts);
  const memberSection = element("details", undefined, "server-members");
  const memberSummary = element("summary", "Members");
  memberSection.append(memberSummary);
  const memberList = element("div", undefined, "inventory-list");
  function drawMembers(details) {
    const humans = (details.member_preview || []).filter(member => !member.bot).slice(0, 50);
    memberSummary.textContent = `Members (${humans.length} shown · up to 50 · bots excluded)`;
    memberList.replaceChildren();
    if (details.member_preview_error) memberList.append(element("p", details.member_preview_error, "details"));
    if (!humans.length && !details.member_preview_error) memberList.append(element("p", "No members returned.", "details"));
    for (const member of humans) {
      const row = element("article", undefined, "member-row");
      row.append(element("strong", member.name), element("p", `@${member.username} · ${member.id}`, "details"));
      if (member.joined_at) row.append(element("p", `Joined ${new Date(member.joined_at).toLocaleDateString()}`, "details"));
      if (member.roles?.length) row.append(element("p", `Roles: ${member.roles.join(", ")}`, "details"));
      memberList.append(row);
    }
  }
  drawMembers(data);
  let memberLoading = false, membersLoaded = !data.member_preview_lazy;
  memberSection.addEventListener("toggle", async () => {
    if (!memberSection.open || membersLoaded || memberLoading || !data.id) return;
    memberLoading = true;
    try {
      const details = await api(`/api/servers/${data.id}/details?members=1`);
      if (memberSection.isConnected) drawMembers(details);
      membersLoaded = true;
    } catch (error) { if (memberSection.isConnected) memberList.append(element("p", error.message, "details")); }
    finally { memberLoading = false; }
  });
  memberSection.append(memberList); target.append(memberSection);
  const features = element("p", `Features: ${data.features?.join(", ") || "None"}`, "details"); target.append(features);
  const assets = element("div", undefined, "card-actions");
  for (const key of ["icon", "banner", "splash"]) {
    const url = data[`${key}_url`];
    if (url && new URL(url).origin === "https://cdn.discordapp.com") {
      const link = element("a", `Open server ${key}`); link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; assets.append(link);
    }
  }
  target.append(assets);
  for (const [label, rows] of [["Channels", data.channels], ["Roles", data.roles]]) {
    const section = element("details", undefined, "server-inventory"); section.append(element("summary", `${label} (${rows?.length ?? "unavailable"})`));
    const list = element("div", undefined, "inventory-list");
    if (rows === null || rows === undefined) list.append(element("p", "Unavailable to the bot.", "details"));
    else for (const row of [...rows].sort((a, b) => a.position - b.position)) {
      let text = `${row.name} · ${row.id}`;
      if (label === "Channels") text += ` · ${channelTypes[row.type] || `Type ${row.type}`}${row.nsfw ? " · Age restricted" : ""}${row.slowmode ? ` · Slowmode ${row.slowmode}s` : ""}${row.category_id ? ` · In ${channelName(row.category_id)}` : ""}`;
      else text += ` · ${row.color}${row.managed ? " · Integration-managed" : ""}${row.mentionable ? " · Mentionable" : ""}`;
      list.append(element("p", text, "details"));
    }
    section.append(list); target.append(section);
  }
  if (data.bot_permissions) target.append(element("p", `Bot server permissions: ${data.bot_permissions.join(", ") || "None"}`, "details"));
  const status = [data.source, data.fetched_at ? `Fetched ${new Date(data.fetched_at * 1000).toLocaleString()}` : null,
    data.partial ? "Some fields unavailable to the bot" : null, data.stale ? "Showing previous data; Discord refresh failed" : null].filter(Boolean);
  target.append(element("p", status.join(" · "), "details"));
}

function lock() {
  healthVersion++;
  for (const id of ["health-summary", "health-services", "health-counts", "health-errors"]) $(id).replaceChildren();
  $("error-id").value = ""; $("error-state").textContent = ""; $("health-state").textContent = "";
  for (const child of serverWindows.values()) if (!child.closed) child.postMessage({type: "meyaya-lock"}, location.origin);
  serverWindows.clear();
  for (const timer of serverWindowTimers.values()) clearTimeout(timer);
  serverWindowTimers.clear();
  $("safety-state").textContent = "";
  $("blacklist-items")?.replaceChildren();
  invalidateApiCache(); lastServerRender = "";
  try { sessionStorage.removeItem("meyaya:overview"); } catch (_) {}
  closeRequests(); token = ""; servers = [];
  $("servers").replaceChildren(); $("memory-items").replaceChildren(); $("nickname-items").replaceChildren();
  $("operations-summary").replaceChildren(); $("operations-features").replaceChildren(); $("operations-models").replaceChildren(); $("operations-recent").replaceChildren();
  $("operations-commands").replaceChildren(); $("server-detail-content").replaceChildren(); $("server-controls").replaceChildren(); $("server-usage").replaceChildren(); $("server-heading").replaceChildren();
  $("server-command-usage").replaceChildren();
  $("workspace").hidden = true; $("navigation").hidden = true; $("login").hidden = false;
  $("connection").textContent = "Locked";
}

function switchView(name, autoLoad = true) {
  if (name !== "server") $("dashboard-header").hidden = false;
  $("global-navigation").hidden = name === "server";
  $("server-navigation").hidden = name !== "server";
  if (name !== "server" && pageServerId) { pageServerId = null; history.replaceState(null, "", "/"); }
  $("global-stats").hidden = name === "server";
  $("live-stats").hidden = name !== "overview";
  $("overview-scope").hidden = name !== "overview";
  for (const view of document.querySelectorAll(".view")) view.hidden = view.id !== `view-${name}`;
  for (const button of document.querySelectorAll(".nav")) button.classList.toggle("active", button.dataset.view === name);
  const copy = {
    overview: ["A little bird's-eye view.", "Your servers, activity, and operational controls."],
    server: ["Inside your server.", "Server details, members, and Meyaya settings."],
    operations: ["The engine room.", "Track model reliability, latency, token usage, and feature traffic."],
    health: ["Meyaya Health.", "Connections, host resources, AI budgets, and error diagnostics."],
    memories: ["The memory vault.", "Search every permanent fact Meyaya currently stores."],
    nicknames: ["Her nickname book.", "See who Meyaya knows well enough to name."],
    blacklist: ["Chat access.", "Review automatic restrictions and restore access when needed."],
  }[name];
  $("page-title").textContent = copy[0]; $("page-subtitle").textContent = copy[1];
  if (autoLoad && name === "memories" && !$("memory-items").children.length) loadMemories(false);
  if (autoLoad && name === "nicknames" && !$("nickname-items").children.length) loadNicknames(false);
  if (autoLoad && name === "operations" && !$("operations-summary").children.length) loadOperations();
  if (autoLoad && name === "health") loadHealth();
  if (autoLoad && name === "blacklist") loadBlacklist();
}

function populateGuildFilters() {
  for (const id of ["memory-guild", "nickname-guild", "operations-guild"]) {
    const select = $(id), selected = select.value;
    select.replaceChildren(new Option("All servers", ""));
    for (const server of servers) select.append(new Option(server.name, server.id));
    if ([...select.options].some(option => option.value === selected)) select.value = selected;
  }
}

function renderHealthErrors(items) {
  const target = $("health-errors"); target.replaceChildren();
  if (!items.length) target.append(element("p", "No matching errors retained.", "details"));
  for (const item of items) {
    const row = element("details", undefined, "operation-row outcome-error");
    row.append(element("summary", `${item.error_id} · ${item.command} · ${item.exception}`));
    const facts = [["Time", new Date(item.timestamp).toLocaleString()], ["Server", item.guild_id ?? "DM / unknown"],
      ["Channel", item.channel_id ?? "Unknown"], ["Invocation", item.invocation ?? "Unknown"],
      ["Stage", item.stage], ["Latency", item.latency_ms == null ? "Not measured" : `${item.latency_ms} ms`],
      ["Provider", item.provider ?? "None recorded"], ["Model", item.model ?? "None recorded"]];
    if (item.request_id) facts.push(["AI request ID", item.request_id]);
    if (item.reason) facts.push(["Reason", item.reason]);
    if (item.diagnosis) {
      facts.push(["Cause", item.diagnosis.cause], ["Next check", item.diagnosis.next_step]);
      if (item.diagnosis.location) facts.push(["Cause location", item.diagnosis.location]);
    }
    if (item.causes?.length) facts.push(["Exception chain", item.causes.map(cause => cause.exception).join(" → ")]);
    for (const [label, value] of facts) row.append(element("p", `${label}: ${value}`, "operation-detail"));
    for (const [stage, value] of Object.entries(item.stages || {})) row.append(element("p", `${stage}: ${value} ms`, "details"));
    for (const frame of item.frames || []) row.append(element("p", `${frame.file}:${frame.line} · ${frame.function}`, "health-frame"));
    target.append(row);
  }
}

async function searchErrors(event) {
  event?.preventDefault();
  const version = ++healthVersion;
  $("error-state").textContent = "Searching…";
  try {
    const id = $("error-id").value.trim().toUpperCase();
    const data = await api(`/api/errors${id ? `?id=${encodeURIComponent(id)}` : ""}`);
    if (version !== healthVersion) return;
    renderHealthErrors(data.items);
    $("error-state").textContent = id ? `${data.items.length} match(es) for ${id}` : "Latest errors from this process";
  } catch (error) { if (version === healthVersion) $("error-state").textContent = error.message; }
}

async function loadHealth() {
  if (healthLoading || !token) return;
  healthLoading = true;
  const version = healthVersion;
  $("health-state").textContent = "Checking health…";
  try {
    const data = await api("/api/health");
    if (version !== healthVersion) return;
    const host = data.host, queue = data.queue;
    const cards = [["AI running", `${queue.active} / ${queue.active_limit}`], ["AI waiting", `${queue.waiting} / ${queue.waiting_limit}`],
      ["RAM (process RSS)", host.rss_mb == null ? "Unavailable" : `${host.rss_mb} / ${host.memory_limit_mb ?? "?"} MB`],
      ["CPU throttled time / interval", host.throttle_percent == null ? "Unavailable" : `${host.throttle_percent}%`],
      ["Scheduler lag", host.wake_lag_ms == null ? "Unavailable" : `${host.wake_lag_ms} ms`],
      ["Connected servers", data.guilds], ["Users observed since startup", `${data.users_seen}${data.users_seen_capped ? "+" : ""}`],
      ["Live voice sessions", queue.voice_active]];
    $("health-summary").replaceChildren();
    for (const [label, value] of cards) {
      const card = element("article"); card.append(element("span", label), element("strong", String(value))); $("health-summary").append(card);
    }
    $("health-services").replaceChildren();
    const symbols = {healthy: "🟢", degraded: "🟡", unavailable: "🔴", unknown: "⚪", disabled: "⚪"};
    for (const service of [...data.dependencies, ...data.models]) {
      const row = element("article", undefined, `operation-row health-${service.status}`);
      row.append(element("h4", `${symbols[service.status] || "⚪"} ${service.name} · ${service.status}`));
      if (service.model) row.append(element("p", service.model, "details"));
      if (service.latency_ms != null) row.append(element("p", `${service.latency_ms} ms`, "operation-detail"));
      if (service.reason) row.append(element("p", service.reason, "details"));
      if (service.last_observation) row.append(element("p", `Last observed ${new Date(service.last_observation.observed_at * 1000).toLocaleString()}`, "details"));
      if (service.quota) {
        const q = service.quota;
        row.append(element("p", `Daily attempts: ${q.daily_used} / ${q.daily_limit ?? "unlimited"}${q.daily_percent == null ? "" : ` (${q.daily_percent}%)`} · ${q.rpm_limit} RPM`, "operation-detail"));
        row.append(element("p", `Budget source: ${q.source} · reset in ${Math.ceil(q.reset_in_seconds / 60)} min${q.blocked_seconds ? ` · blocked ${q.blocked_seconds}s` : ""}`, "details"));
      }
      $("health-services").append(row);
    }
    $("health-counts").replaceChildren();
    const labels = {gemini_429: "Gemini 429", gemini_503: "Gemini 503", discord_429: "Discord 429", db_errors: "DB errors"};
    for (const [key, count] of Object.entries(data.errors_24h)) $("health-counts").append(element("p", `${labels[key]}: ${count}`));
    if (!$("error-id").value.trim()) renderHealthErrors(data.recent_errors);
    $("health-state").textContent = `Updated ${new Date(data.generated_at).toLocaleTimeString()} · dependency probes cached 30s · models use real outcomes, not test calls · same model routes share one budget · telemetry since ${new Date(data.started_at).toLocaleString()}`;
  } catch (error) { if (version === healthVersion) $("health-state").textContent = error.message; }
  finally { healthLoading = false; }
}

$("health-refresh").addEventListener("click", loadHealth);
$("error-search").addEventListener("submit", searchErrors);
setInterval(() => {
  if (token && !document.hidden && !$("view-health").hidden) loadHealth();
}, 30000);

function renderServerUsage(target, server) {
    target.replaceChildren();
    const card = element("article", undefined, "card");
    card.append(element("h3", "Server activity"));
    const metrics = element("div", undefined, "metrics");
    if (server.local) {
      metrics.append(metric("Members (approx.)", server.members ?? "Unavailable"), metric("Commands today", server.today_commands), metric("Meyaya replies / 7 days", server.week_chats), metric("Commands / 7 days", server.week_commands));
      card.append(metrics, element("p", "Discord metadata is fetched on demand. Process counters are available on the hosted dashboard. Settings apply on the updated host within 60 seconds.", "details"));
    } else {
    metrics.append(metric("Members", server.members ?? "Unknown"), metric("Commands today", server.today_commands), metric("Meyaya replies / 7 days", server.week_chats), metric("Commands / 7 days", server.week_commands), metric("Response success", `${server.model_success_rate}%`), metric("Failed responses", server.model_failures), metric("Average latency", server.model_average_latency_ms === null ? "No data" : `${server.model_average_latency_ms} ms`), metric("Tokens this process", (server.model_tokens ?? 0).toLocaleString())); card.append(metrics);
    card.append(element("p", `${server.available ? "Available" : "Unavailable"} - ${server.readable_channels} readable - ${server.monitored_channels} monitored - Timeout: ${server.can_timeout ? "yes" : "no"}`, "details"));
    card.append(element("p", `Voice ${server.voice_active ? "connected" : "disconnected"}`, "details"));
    }
    const voiceTime = element("div", undefined, "metrics");
    const hours = value => `${((value || 0)/3600).toFixed(2)} h`;
    voiceTime.append(metric("Voice today", hours(server.today_voice_seconds)), metric("Voice / 7 days", hours(server.week_voice_seconds)), metric("Voice all time", hours(server.total_voice_seconds)));
    card.append(element("h4", "Voice chat usage"), voiceTime, element("p", "Meyaya session time, including active sessions. UTC days; tracking starts with this update.", "details"));
    target.append(card);
}

function renderServerControls(target, server) {
    if (target.dataset.guildId === server.id && target.querySelector("form")?.dataset.dirty === "true" && !server.readOnly) return;
    target.dataset.guildId = server.id;
    target.replaceChildren();
    const card = element("form", undefined, "card");
    card.append(element("h3", `Settings for ${server.name}`), element("div", server.id, "id"), element("span", server.exempt ? "✦ Main server - Unlimited" : `${server.today_chats} / ${server.limit} Meyaya replies today`, "badge"));
    const progress = element("progress"); progress.max = Math.max(1, server.limit); progress.value = server.exempt ? 0 : server.today_chats; progress.setAttribute("aria-label", "Daily allowance used"); card.append(progress);
    const prefixLabel = element("label", "Command prefix"), prefix = element("input"); prefix.value = server.prefix; prefix.maxLength = 10; prefix.required = true; prefixLabel.append(prefix);
    const limitLabel = element("label", "Daily Meyaya reply allowance (0 disables chat)"), limit = element("input"); limit.type = "number"; limit.min = "0"; limit.max = "10000"; limit.required = true; limit.value = server.limit; limit.disabled = server.exempt; limitLabel.append(limit);
    const toggle = element("label", undefined, "toggle"), auto = element("input"); auto.type = "checkbox"; auto.checked = server.autoresponder; toggle.append(auto, element("span", "Automatic replies enabled"));
    const save = element("button", server.readOnly ? "Read-only AWS console" : "Save changes", "save"); save.disabled = !!server.readOnly; if (server.readOnly) { prefix.disabled = true; limit.disabled = true; auto.disabled = true; } card.append(prefixLabel, limitLabel, element("p", "This allowance applies only to this server and is shared by AI chat, roleplay, and automatic replies. Increasing it does not reset usage. Resets at 00:00 UTC.", "details"), toggle);
    const featureInputs = new Map();
    if (server.features && typeof server.features === "object") {
      const featureSet = element("fieldset", undefined, "server-feature-grid");
      featureSet.append(element("legend", "Enable or disable features"));
      for (const [name, enabled] of Object.entries(server.features)) {
        const label = element("label", undefined, "toggle feature-toggle"), input = element("input");
        input.type = "checkbox"; input.checked = enabled; input.disabled = !!server.readOnly;
        label.append(input, element("span", name)); featureSet.append(label); featureInputs.set(name, input);
      }
      card.append(featureSet, element("p", "Help and server administration stay available. Switches control new commands and conversations; saved profiles, memories, and history are kept. Existing games and voice sessions can finish.", "details"));
    } else card.append(element("p", "Feature switches require the updated AWS bot. Prefix, allowance, and automatic replies remain editable.", "details"));
    if (server.exempt) card.append(element("p", "This is the quota-exempt server. Its chat allowance stays unlimited.", "details"));
    card.append(save);
    card.addEventListener("input", () => { card.dataset.dirty = "true"; });
    card.addEventListener("change", () => { card.dataset.dirty = "true"; });
    const resetSection = element("section", undefined, "usage-reset-section");
    const reset = element("button", "Reset today's chat usage", "quiet"); reset.type = "button";
    reset.disabled = !!server.readOnly || !server.features;
    resetSection.append(element("h4", "Give this server a fresh allowance"),
      element("p", "Resets today's used chat slots to zero. Command counts, chat history, and the daily limit stay unchanged. Disabled features and a zero allowance stay disabled.", "details"), reset);
    reset.addEventListener("click", async () => {
      reset.disabled = true;
      try {
        await api(`/api/servers/${server.id}/reset-usage`, {method:"POST", body:JSON.stringify({confirm:true})});
        notice(`Reset today's chat usage for ${server.name}. The saved daily allowance is available again.`);
        await refresh();
      } catch (error) { notice(error.message); }
      finally { reset.disabled = !!server.readOnly; }
    });
    card.append(resetSection);
    const review = element("button", "View AI chat log", "quiet save"); review.type = "button";
    review.addEventListener("click", () => switchServerPanel("chat")); card.append(review);
    const shortcuts = element("div", undefined, "card-actions");
    const memories = element("button", "Memories", "quiet"); memories.type = "button";
    memories.addEventListener("click", () => { $("memory-guild").value = server.id; switchView("memories", false); loadMemories(false); });
    const nicknames = element("button", "Nicknames", "quiet"); nicknames.type = "button";
    nicknames.addEventListener("click", () => { $("nickname-guild").value = server.id; switchView("nicknames", false); loadNicknames(false); });
    shortcuts.append(memories, nicknames); card.append(shortcuts);
    card.addEventListener("submit", async event => { event.preventDefault(); save.disabled = true; try { await api(`/api/servers/${server.id}`, {method: "PATCH", body: JSON.stringify({prefix: prefix.value, autoresponder: auto.checked, limit: Number(limit.value), ...(featureInputs.size ? {features: Object.fromEntries([...featureInputs].map(([name, input]) => [name, input.checked]))} : {})})}); card.dataset.dirty = "false"; notice(`Saved settings for ${server.name}.`); await refresh(); } catch (error) { notice(error.message); } finally { save.disabled = !!server.readOnly; } });
    target.append(card);
}

function serverIcon(server, className = "server-icon") {
  const frame = element("div", server.name?.slice(0, 2).toUpperCase() || "M", className);
  if (server.icon_url && new URL(server.icon_url).origin === "https://cdn.discordapp.com") {
    const img = element("img"); img.src = server.icon_url; img.alt = `${server.name} icon`;
    img.loading = "lazy"; img.referrerPolicy = "no-referrer";
    img.addEventListener("error", () => { frame.replaceChildren(document.createTextNode(server.name?.slice(0, 2).toUpperCase() || "M")); }, {once: true});
    frame.replaceChildren(img);
  }
  return frame;
}

async function openServerWindow(server) {
  const previous = serverWindows.get(server.id);
  if (previous && !previous.closed) { previous.focus(); return; }
  const child = window.open(`/?server=${server.id}`, `meyaya-server-${server.id}`, "popup,width=1240,height=900");
  if (!child) { await showWindowFallback(server); return; }
  serverWindows.set(server.id, child);
  serverWindowTimers.set(server.id, setTimeout(() => {
    serverWindowTimers.delete(server.id);
    if (token) showWindowFallback(server).catch(error => notice(error.message));
  }, 3000));
  try {
    const url = document.body.dataset.localDashboard === "true" ? `/?server=${server.id}` : (await api("/api/window", {method: "POST", body: JSON.stringify({guild_id: server.id})})).url;
    const destination = new URL(url, location.origin);
    if (destination.origin !== location.origin) throw new Error("Invalid server window destination.");
    if (!child.closed && token && document.body.dataset.localDashboard !== "true") child.location.replace(destination.href);
  } catch (error) {
    clearTimeout(serverWindowTimers.get(server.id)); serverWindowTimers.delete(server.id);
    child.close(); serverWindows.delete(server.id); notice(error.message);
  }
}

async function showWindowFallback(server) {
  const url = document.body.dataset.localDashboard === "true" ? `/?server=${server.id}` : (await api("/api/window", {method: "POST", body: JSON.stringify({guild_id: server.id})})).url;
  const destination = new URL(url, location.origin);
  if (destination.origin !== location.origin || !token) return;
  const link = element("a", "Open server details in a new tab ↗");
  link.href = destination.href; link.target = "_blank"; link.rel = "noopener noreferrer";
  $("notice").replaceChildren(document.createTextNode("If your browser didn't open the window, "), link);
}

const isFormerServer = server => server.membership === "removed" || (server.local && server.available === false);

function renderServers() {
  const query = $("search").value.toLowerCase();
  const filter = $("server-filter").value;
  const visible = servers.filter(server => `${server.name} ${server.id} ${server.owner_name || ""}`.toLowerCase().includes(query))
    .filter(server => filter === "all" || (filter === "active" && (server.today_chats + server.today_commands > 0)) ||
      (filter === "quota" && !isFormerServer(server) && !server.exempt && server.today_chats >= server.limit) ||
      (filter === "unavailable" && (isFormerServer(server) || server.available === false)));
  const sort = $("server-sort").value;
  visible.sort((a,b) => {
    const score = server => sort === "activity" ? (server.today_chats + server.today_commands) :
      sort === "members" ? (server.members ?? -1) : sort === "joined" ? (Date.parse(server.joined_at) || 0) : 0;
    return score(b) - score(a) || a.name.localeCompare(b.name);
  });
  const signature = JSON.stringify(visible);
  if (signature === lastServerRender && $("servers").children.length + $("former-servers").children.length) return;
  lastServerRender = signature;
  const current = visible.filter(server => !isFormerServer(server));
  const former = visible.filter(isFormerServer);
  $("servers").replaceChildren(); $("former-servers").replaceChildren();
  $("empty").hidden = current.length > 0; $("former-empty").hidden = former.length > 0;
  $("current-server-count").textContent = current.length;
  $("former-server-count").textContent = former.length;
  for (const server of visible) {
    const card = element("button", undefined, "server-tile"); card.type = "button";
    const icon = serverIcon(server), owner = element("p", `Owner · ${server.owner_name || (isFormerServer(server) ? "Not previously recorded" : "Loading…")}`, "server-owner");
    const activity = element("div", undefined, "server-tile-activity");
    activity.append(metric("AI chats today", known(server.today_chats)), metric("Commands today", known(server.today_commands)));
    card.append(icon, element("h3", server.name), owner, activity, element("span", server.id, "id"), element("span", "View server →", "tile-link"));
    if (server.membership === "removed" || (server.local && server.available === false)) card.append(element("span", "No longer in server · saved records", "details"));
    card.setAttribute("aria-label", `View ${server.name}`);
    card.addEventListener("click", () => navigateServer(server.id)); $(isFormerServer(server) ? "former-servers" : "servers").append(card);
    if (!server.owner_name && !isFormerServer(server)) api(`/api/servers/${server.id}/summary`).then(data => {
      if (!card.isConnected || !token) return;
      server.owner_name = data.owner_name; server.icon_url = data.icon_url || server.icon_url;
      owner.textContent = `Owner · ${data.owner_name || "Unavailable"}`;
      icon.replaceWith(serverIcon(server));
    }).catch(() => { if (card.isConnected) owner.textContent = `Owner · ${server.owner_name || "Temporarily unavailable"}`; });
  }
}

async function showServer(guildId) {
  switchView("server", false); $("global-stats").hidden = true;
  const server = servers.find(item => item.id === guildId);
  if (!server) { $("server-state").textContent = "Server not found or no longer available to Meyaya."; return; }
  $("page-title").textContent = server.name;
  $("server-heading").replaceChildren(serverIcon(server), element("div", `Owner · ${server.owner_name || "Loading…"}`));
  renderServerUsage($("server-usage"), server);
  renderServerControls($("server-controls"), server);
  $("sidebar-server-name").textContent = server.name;
  switchServerPanel(selectedServerPanel, false);
}

async function loadServerBasics(guildId) {
  const server = servers.find(item => item.id === guildId);
  if (!server) return;
  $("server-state").textContent = "Loading server details…";
  try {
    const data = await api(`/api/servers/${guildId}/details`);
    if (!token || pageServerId !== guildId) return;
    renderServerDetails($("server-detail-content"), data);
    $("server-heading").replaceChildren(serverIcon({...server, icon_url: data.icon_url || server.icon_url}), element("div", `Owner · ${data.owner_name || "Unavailable"}`));
    $("server-state").textContent = "";
  } catch (error) { if (pageServerId === guildId) $("server-state").textContent = error.message; }
}

async function loadServerCommands(guildId) {
  const target = $("server-command-usage"); target.dataset.guildId = guildId;
  target.replaceChildren(element("h3", "Command usage"), element("p", "Loading command counts…", "details"));
  try {
    const data = await api(`/api/servers/${guildId}/commands`);
    if (!token || target.dataset.guildId !== guildId) return;
    target.replaceChildren(element("h3", "Command usage"), element("p", data.scope, "details"));
    if (data.unclassified_total) target.append(element("p", `${data.unclassified_total.toLocaleString()} earlier completions have no recorded command name.`, "details"));
    if (!data.items.length) { target.append(element("p", "No named command usage recorded yet.", "details")); return; }
    const table = element("table", undefined, "command-usage-table"), heading = element("tr"), head = element("thead"), body = element("tbody");
    for (const label of ["Command", "Today", "Last 7 days", "Total recorded"]) { const cell = element("th", label); cell.scope = "col"; heading.append(cell); }
    head.append(heading);
    for (const item of data.items) {
      const row = element("tr"); row.append(element("td", item.command));
      for (const field of ["today", "week", "total"]) row.append(element("td", Number(item[field]).toLocaleString()));
      body.append(row);
    }
    table.append(head, body); const scroll = element("div", undefined, "command-usage-scroll"); scroll.append(table); target.append(scroll);
  } catch (error) { if (token && target.dataset.guildId === guildId) target.replaceChildren(element("h3", "Command usage"), element("p", error.message, "details")); }
}

async function refresh() {
  const data = await api("/api/servers");
  saveOverviewSnapshot(data);
  applyServerData(data);
}
function applyServerData(data) {
  servers = data.servers;
  servers.forEach(server => { server.readOnly = isFormerServer(server) || (data.mode === "remote" && !data.can_edit); });
  $("connection").textContent = data.mode === "remote" ? `● Live AWS bot · ${data.can_edit ? "editing enabled" : "read-only"}` : data.mode === "local" ? "● Local dashboard · cloud database" : data.ready ? "● Connected" : "Connecting to Discord";
  $("total").textContent = servers.filter(server => !isFormerServer(server)).length; $("chats").textContent = servers.reduce((n, server) => n + server.today_chats, 0); $("commands").textContent = servers.reduce((n, server) => n + server.today_commands, 0);
  populateGuildFilters();
  if (!pageServerId) { renderServers(); loadOverviewInsights(); }
  if (pageServerId) {
    for (const id of ["memory-guild", "nickname-guild", "operations-guild"]) $(id).value = pageServerId;
    showServer(pageServerId);
  }
}

function closeRequests() {
  requestVersion++; selectedServer = null; requestCursor = null; $("request-panel").hidden = true;
  $("request-items").replaceChildren(); $("request-state").textContent = ""; $("request-more").hidden = true;
}

async function loadRequests(older) {
  if (!selectedServer || !token) return;
  const version = ++requestVersion, guildId = selectedServer.id;
  $("request-state").textContent = "Loading"; $("request-more").disabled = true;
  try {
    const params = new URLSearchParams({kind: $("chat-kind").value});
    if (older && requestCursor) params.set("before", requestCursor);
    const query = `?${params}`;
    const data = await api(`/api/servers/${guildId}/requests${query}`);
    if (version !== requestVersion || selectedServer?.id !== guildId) return;
    if (!older) $("request-items").replaceChildren();
    for (const item of data.items) {
      const entry = element("article", undefined, "discord-exchange");
      const user = discordMessage(item.user_name, item.content);
      const reply = discordMessage("Meyaya", item.response ?? "Reply not recorded.", true);
      if (item.kind === "auto_chat") user.querySelector(".discord-message-heading").append(element("span", "Automatic reply", "conversation-type auto-reply"));
      entry.append(user, reply); $("request-items").append(entry);
    }
    requestCursor = data.next_cursor; $("request-more").hidden = !requestCursor;
    $("request-state").textContent = $("request-items").children.length ? `${$("request-items").children.length} AI chats shown` : "No recorded AI chats in the last seven days.";
  } catch (error) { if (version === requestVersion) $("request-state").textContent = error.message; }
  finally { if (version === requestVersion) $("request-more").disabled = false; }
}

function buildQuery(prefix, guild, query, extra = {}) {
  const params = new URLSearchParams({limit: "50", offset: String(extra.offset || 0)});
  if (guild) params.set("guild_id", guild);
  if (query.trim()) params.set("q", query.trim());
  for (const [key, value] of Object.entries(extra)) if (key !== "offset" && value) params.set(key, value);
  return `${prefix}?${params}`;
}

async function loadMemories(older) {
  const offset = older ? memoryOffset : 0; if (older && offset === null) return;
  $("memory-state").textContent = "Loading memories"; $("memory-more").disabled = true;
  try {
    const data = await api(buildQuery("/api/memories", $("memory-guild").value, $("memory-query").value, {offset, status: $("memory-status").value}));
    if (!older) $("memory-items").replaceChildren();
    for (const item of data.items) {
      const entry = element("article", undefined, "memory-entry");
      const heading = element("div", undefined, "record-heading"); heading.append(element("h3", `${item.user_name} - ${item.relation}`), element("span", item.status, `status ${item.status}`)); entry.append(heading);
      entry.append(element("p", `${item.guild_name} - User ${item.user_id} - Memory #${item.id} - ${item.category}:${item.subject}`, "details"));
      entry.append(element("p", item.value, "record-value"));
      const meta = element("div", undefined, "record-meta"); meta.append(metric("Confidence", `${item.confidence}%`), metric("Lifecycle", item.lifecycle_reason || "unknown"), metric("Updated", item.updated_at ? new Date(item.updated_at).toLocaleString() : "unknown")); entry.append(meta);
      if (item.conflict_value) entry.append(element("p", `Conflicting value: ${item.conflict_value}`, "conflict"));
      if (item.conversation_summary) entry.append(element("details", undefined, "memory-summary"));
      const details = entry.querySelector("details"); if (details) details.append(element("summary", "Conversation summary"), element("p", item.conversation_summary));
      if (item.source_url) { const link = element("a", "Open source message"); link.href = item.source_url; link.target = "_blank"; link.rel = "noopener noreferrer"; entry.append(link); }
      $("memory-items").append(entry);
    }
    memoryOffset = data.next_offset; $("memory-more").hidden = memoryOffset === null;
    $("memory-state").textContent = `${data.total} permanent ${data.total === 1 ? "memory" : "memories"} found`;
  } catch (error) { $("memory-state").textContent = error.message; }
  finally { $("memory-more").disabled = false; }
}

async function loadNicknames(older) {
  const offset = older ? nicknameOffset : 0; if (older && offset === null) return;
  $("nickname-state").textContent = "Loading nicknames"; $("nickname-more").disabled = true;
  try {
    const data = await api(buildQuery("/api/nicknames", $("nickname-guild").value, $("nickname-query").value, {offset}));
    if (!older) $("nickname-items").replaceChildren();
    for (const item of data.items) {
      const card = element("article", undefined, "nickname-card"); card.append(element("span", item.nickname, "nickname"), element("h3", item.user_name), element("p", `${item.guild_name} - ${item.user_id}`, "details"));
      const metrics = element("div", undefined, "record-meta"); metrics.append(metric("Familiarity", item.familiarity), metric("Affection", item.affection), metric("Annoyance", item.annoyance)); card.append(metrics); $("nickname-items").append(card);
    }
    nicknameOffset = data.next_offset; $("nickname-more").hidden = nicknameOffset === null;
    $("nickname-state").textContent = `${data.total} ${data.total === 1 ? "nickname" : "nicknames"} found`;
  } catch (error) { $("nickname-state").textContent = error.message; }
  finally { $("nickname-more").disabled = false; }
}

function renderOperationGroup(target, items) {
  $(target).replaceChildren();
  if (!items.length) { $(target).append(element("p", "No model requests recorded yet.", "details")); return; }
  for (const item of items) {
    const row = element("article", undefined, "operation-row");
    row.append(element("h4", item.name), element("p", `${item.requests} requests - ${item.successes} successful - ${item.failures} failed`, "details"));
    const values = element("div", undefined, "operation-values");
    values.append(element("span", `${item.tokens.toLocaleString()} tokens`), element("span", item.average_latency_ms === null ? "No latency" : `${item.average_latency_ms} ms average`));
    row.append(values); $(target).append(row);
  }
}

function renderCommandTimings(data) {
  $("operations-commands").replaceChildren();
  if (!data?.groups?.length) { $("operations-commands").append(element("p", "No command callbacks recorded yet.", "details")); return; }
  const labels = {database_ms: "DB session", context_ms: "Optional context", quota_ms: "Quota", ai_ms: "AI", discord_metadata_ms: "Discord metadata", asset_fetch_ms: "Asset downloads", render_ms: "Rendering", image_queue_ms: "Image queue", delivery_ms: "Discord API call (includes waits)", loading_cleanup_ms: "Loading cleanup"};
  for (const item of data.groups) {
    const row = element("article", undefined, "operation-row");
    row.append(element("h4", item.command), element("p", `${item.calls} calls · ${item.failures} errors · ${item.cancelled} cancelled · ${item.average_ms} ms average · ${item.p95_ms} ms P95`, "details"));
    const stages = element("div", undefined, "operation-values");
    for (const [key, label] of Object.entries(labels)) if (item.stages[key] !== undefined) stages.append(element("span", `${label}: ${item.stages[key]} ms`));
    row.append(stages); $("operations-commands").append(row);
  }
}

async function loadOperations() {
  api("/api/safety").then(data => {
    if (!token) return;
    if (data.mode === "local") { $("safety-state").textContent = "Hosted runtime counters are unavailable in local mode."; return; }
    $("safety-state").textContent = `AI ${data.enabled ? "enabled" : "paused"} · Member cooldown ${data.member_cooldown_seconds}s · Running requests ${data.active_requests}/${data.max_concurrent} · Voice sessions ${data.active_voice_sessions}/${data.max_voice_sessions}`;
  }).catch(() => { if (token) $("safety-state").textContent = "Safety counters unavailable."; });
  $("operations-state").textContent = "Loading operational telemetry";
  try {
    const guild = $("operations-guild").value;
    const data = await api(`/api/operations${guild ? `?guild_id=${encodeURIComponent(guild)}` : ""}`);
    const summary = data.summary;
    $("operations-summary").replaceChildren();
    for (const [label, value] of [
      ["Model requests", summary.requests],
      ["Success rate", `${summary.success_rate}%`],
      ["Failures", summary.failures],
      ["Recovered attempts", summary.recovered_attempts],
      ["Average latency", summary.average_latency_ms === null ? "No data" : `${summary.average_latency_ms} ms`],
      ["P95 latency", summary.p95_latency_ms === null ? "No data" : `${summary.p95_latency_ms} ms`],
      ["Tokens", summary.total_tokens.toLocaleString()],
      ["Requests last hour", summary.last_hour],
    ]) {
      const card = element("article"); card.append(element("span", label), element("strong", String(value))); $("operations-summary").append(card);
    }
    renderOperationGroup("operations-features", data.features);
    renderOperationGroup("operations-models", data.models);
    renderCommandTimings(data.commands);
    $("operations-recent").replaceChildren();
    if (!data.recent.length) $("operations-recent").append(element("p", "No model outcomes recorded yet.", "details"));
    for (const item of data.recent) {
      const row = element("article", undefined, `operation-row outcome-${item.status}`);
      row.append(element("h4", `${item.feature} - ${item.status}`), element("p", `${new Date(item.timestamp).toLocaleString()} - ${item.model} - ${item.operation}`, "details"));
      const detail = [item.latency_ms === null ? "No latency" : `${item.latency_ms} ms`, `${item.total_tokens.toLocaleString()} tokens`, item.guild_id ? `Server ${item.guild_id}` : "No server context"];
      if (item.fallback_reason) detail.push(`Fallback: ${item.fallback_reason}`);
      row.append(element("p", detail.join(" - "), "operation-detail")); $("operations-recent").append(row);
    }
    $("operations-state").textContent = `Process telemetry since ${new Date(data.started_at).toLocaleString()} - no prompts or responses stored`;
  } catch (error) { $("operations-state").textContent = error.message; }
}

$("login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const credential = $("token").value;
  $("token").value = "";
  try {
    const response = await fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({token: credential})});
    if (!response.ok) throw new Error("Sign-in failed. Check your token or wait before trying again.");
    token = (await response.json()).token;
    await refresh();
    $("workspace").hidden = false; $("navigation").hidden = false; $("login").hidden = true;
    notice(""); if (!pageServerId) switchView("overview");
  } catch (error) { lock(); notice(error.message); }
});

async function useOwnerLink() {
  const code = new URLSearchParams(location.hash.slice(1)).get("login");
  if (!code) return;
  history.replaceState(null, "", location.pathname + location.search);
  try {
    const response = await fetch("/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({code})});
    if (!response.ok) throw new Error("Dashboard link expired or already used. Run uwu owner again.");
    token = (await response.json()).token;
    await refresh();
    $("workspace").hidden = false; $("navigation").hidden = false; $("login").hidden = true;
    if (!pageServerId) switchView("overview"); notice("");
  } catch (error) { lock(); notice(error.message); }
}
if (document.body.dataset.localDashboard === "true") {
  token = "local"; // UI state only; local server enforces loopback and origin checks.
  $("logout").hidden = true;
  $("workspace").hidden = false; $("navigation").hidden = false; $("login").hidden = true;
  $("connection").textContent = "Connecting";
  if (!pageServerId) switchView("overview");
  $("servers").replaceChildren(element("p", "Loading your servers…", "details"));
  async function loadLocalOverview() {
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        await refresh(); notice(""); return;
      } catch (error) {
        if (!attempt) { notice("The first request did not finish. Retrying…"); continue; }
        $("connection").textContent = "Could not load servers";
        if (!servers.length) $("servers").replaceChildren(element("p", "Server loading failed. Use Refresh to try again.", "details"));
        notice(error.name === "TimeoutError" ? "The dashboard took too long to respond. Check its terminal for errors, then select Refresh." : error.message);
      }
    }
  }
  queueMicrotask(() => { restoreOverviewSnapshot(); loadLocalOverview(); });
} else {
  useOwnerLink();
}

async function loadBlacklist() {
  try {
    const data = await api("/api/blacklist");
    if (!token) return;
    $("blacklist-items").replaceChildren();
    for (const item of data.items) {
      const card = element("article", undefined, "record-card");
      const server = servers.find(server => server.id === item.guild_id);
      card.append(element("h3", `Member ${item.user_id} - ${item.active ? "Blocked" : "Restored"}`), element("p", `${server?.name || item.guild_id} - ${item.source} - ${new Date(item.updated_at).toLocaleString()}`), element("p", item.reason));
      if (item.active) {
        const button = element("button", "Restore access");
        button.onclick = async () => {
          button.disabled = true;
          try { await api("/api/blacklist", {method: "PATCH", body: JSON.stringify({guild_id: item.guild_id, user_id: item.user_id, active: false})}); await loadBlacklist(); }
          catch (error) { notice(error.message); button.disabled = false; }
        };
        card.append(button);
      }
      $("blacklist-items").append(card);
    }
    $("blacklist-state").textContent = `${data.items.length} decisions shown`;
  } catch (error) { notice(error.message); }
}
$("blacklist-refresh").addEventListener("click", loadBlacklist);
$("blacklist-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await api("/api/blacklist", {method: "PATCH", body: JSON.stringify({guild_id: $("blacklist-guild").value, user_id: $("blacklist-user").value, active: true, reason: $("blacklist-reason").value})});
    await loadBlacklist(); notice("");
  } catch (error) { notice(error.message); }
});
$("logout").addEventListener("click", () => {
  const session = token;
  lock(); notice("");
  if (session) fetch("/api/logout", {method: "POST", headers: {"Authorization": `Bearer ${session}`, "Content-Type": "application/json"}, body: "{}"})
    .catch(() => notice("Locked locally. Server sign-out could not be confirmed; the session expires within one hour."));
});
$("refresh").addEventListener("click", () => refresh().catch(error => notice(error.message)));
$("search").addEventListener("input", renderServers);
for (const button of document.querySelectorAll(".nav")) button.addEventListener("click", () => switchView(button.dataset.view));
$("request-refresh").addEventListener("click", () => loadRequests(false)); $("request-more").addEventListener("click", () => loadRequests(true));
$("memory-refresh").addEventListener("click", () => loadMemories(false)); $("memory-more").addEventListener("click", () => loadMemories(true));
$("memory-guild").addEventListener("change", () => loadMemories(false)); $("memory-status").addEventListener("change", () => loadMemories(false)); $("memory-query").addEventListener("change", () => loadMemories(false));
$("nickname-refresh").addEventListener("click", () => loadNicknames(false)); $("nickname-more").addEventListener("click", () => loadNicknames(true));
$("nickname-guild").addEventListener("change", () => loadNicknames(false)); $("nickname-query").addEventListener("change", () => loadNicknames(false));
$("operations-refresh").addEventListener("click", loadOperations); $("operations-guild").addEventListener("change", loadOperations);
$("server-refresh").addEventListener("click", () => refresh().catch(error => notice(error.message)));
$("server-panel-chat").append($("request-panel"));
window.addEventListener("message", event => {
  if (event.origin === location.origin && event.data?.type === "meyaya-server-ready" && serverWindows.get(event.data.guild_id) === event.source) {
    clearTimeout(serverWindowTimers.get(event.data.guild_id)); serverWindowTimers.delete(event.data.guild_id);
    return;
  }
  if (event.origin !== location.origin || event.source !== window.opener || event.data?.type !== "meyaya-lock") return;
  const session = token; lock();
  if (session && session !== "local") fetch("/api/logout", {method: "POST", headers: {"Authorization": `Bearer ${session}`, "Content-Type": "application/json"}, body: "{}"}).catch(() => {});
});
if (pageServerId && window.opener) window.opener.postMessage({type: "meyaya-server-ready", guild_id: pageServerId}, location.origin);

// Keep the overview current without interrupting an open server or an edit.
let autoRefreshRunning = false;
setInterval(async () => {
  if (!token || document.hidden || $("view-overview").hidden || autoRefreshRunning) return;
  autoRefreshRunning = true;
  try { await refresh(); } catch (error) { notice(error.message); }
  finally { autoRefreshRunning = false; }
}, 15000);

async function navigateServer(guildId) {
  overviewScrollY = window.scrollY;
  pageServerId = guildId; selectedServerPanel = "main";
  history.pushState(null, "", `/?server=${encodeURIComponent(guildId)}`);
  closeRequests(); await showServer(guildId); window.scrollTo({top:0});
}
$("server-back").addEventListener("click", () => {
  pageServerId = null; history.pushState(null, "", "/"); closeRequests(); switchView("overview");
  window.scrollTo({top: overviewScrollY});
});
window.addEventListener("popstate", () => {
  closeRequests();
  pageServerId = new URLSearchParams(location.search).get("server");
  selectedServerPanel = new URLSearchParams(location.search).get("panel") || "main";
  if (pageServerId) showServer(pageServerId); else { switchView("overview"); window.scrollTo({top: overviewScrollY}); }
});
for (const id of ["server-sort", "server-filter"]) $(id).addEventListener("change", renderServers);

let overviewLoading = false;
async function loadOverviewInsights() {
  if (overviewLoading) return;
  overviewLoading = true;
  try {
    const data = await api("/api/overview");
    if (!token) return;
    const seconds = data.uptime_seconds;
    $("bot-uptime").textContent = `${Math.floor(seconds/86400)}d ${Math.floor(seconds/3600)%24}h ${Math.floor(seconds/60)%60}m`;
    $("bot-response-latency").textContent = data.response_latency_ms == null ? "No data yet" : `${(data.response_latency_ms/1000).toFixed(2)}s`;
    $("bot-voice").textContent = data.active_voice_sessions;
    $("bot-failures").textContent = data.failed_requests_today;
    $("overview-scope").textContent = `Updated ${new Date(data.generated_at).toLocaleTimeString()} · Gateway ${data.gateway_latency_ms ?? "unavailable"} ms · ${data.observation_scope}`;
    $("attention-items").replaceChildren();
    if (!data.issues.length) $("attention-items").append(element("p", "All quiet for now. No server issues detected in the available observations.", "status-ok"));
    for (const issue of data.issues) {
      const row = element("article", undefined, "attention-item"), copy = element("div");
      const server = servers.find(s => s.id === issue.guild_id);
      copy.append(element("strong", `${server?.name || issue.guild_id} · ${issue.title}`), element("p", issue.detail, "details"));
      const open = element("button", "View diagnostics", "quiet"); open.addEventListener("click", async () => {
        await navigateServer(issue.guild_id);
        if (issue.diagnostic === "errors") switchServerPanel("diagnostics");
        if (issue.diagnostic === "settings") switchServerPanel("edit");
        const section = issue.diagnostic === "settings" ? "server-controls" : issue.diagnostic === "permissions" ? "server-detail-content" : "server-insights";
        $(section).scrollIntoView({behavior:"smooth"});
      });
      row.append(copy, open); $("attention-items").append(row);
    }
  } catch (error) {
    for (const id of ["bot-uptime", "bot-response-latency", "bot-voice", "bot-failures"]) $(id).textContent = "Unavailable";
    $("overview-scope").textContent = error.message;
    $("attention-items").replaceChildren(element("p", "Diagnostics could not be refreshed. Use Refresh to try again.", "details"));
  } finally { overviewLoading = false; }
}

async function loadServerInsights(guildId) {
  const target = $("server-insights"); target.dataset.guildId = guildId;
  target.replaceChildren(element("p", "Loading server history and diagnostics…", "details"));
  try {
    const data = await api(`/api/servers/${guildId}/insights`);
    if (!token || target.dataset.guildId !== guildId) return;
    target.replaceChildren();
    const identity = data.identity || {}, facts = element("div", undefined, "metrics");
    const date = value => value ? new Date(value).toLocaleString() : "Not recorded";
    const server = servers.find(s => s.id === guildId);
    facts.append(metric("Membership", isFormerServer(server || {}) ? "Removed" : "Current"),
      metric("Joined", date(identity.joined_at || server?.joined_at)), metric("Left", date(identity.left_at)), metric("Last activity", date(identity.last_activity_at)));
    target.append(element("h3", "Server history & diagnostics"), facts);
    const historyPanel = element("details"); historyPanel.open = true; historyPanel.append(element("summary", "Membership history & settings audit"));
    const events = element("ol", undefined, "history-list");
    for (const event of data.history) {
      const labels = {joined:"Meyaya joined", left:"Meyaya left", first_observed:"First observed", settings_changed:"Settings updated", usage_reset:"Chat usage reset"};
      const item = element("li"); item.append(element("strong", `${labels[event.type] || event.type} · ${date(event.timestamp)}`));
      if (event.type === "settings_changed") {
        const changes = Object.entries(event.details.after || {}).flatMap(([key, value]) => {
          const before = event.details.before?.[key];
          if (key === "features") return Object.entries(value).filter(([name, enabled]) => before?.[name] !== enabled)
            .map(([name, enabled]) => `${name}: ${enabled ? "enabled" : "disabled"}`);
          return before === value ? [] : [`${key}: ${before} → ${value}`];
        });
        item.append(element("p", `${event.actor || "Owner"} · ${changes.join(" · ") || "Settings saved without changes"}`, "details"));
      } else if (event.type !== "usage_reset") item.append(element("p", `${event.details.name || "Server"}${event.details.owner_name ? ` · Owner: ${event.details.owner_name}` : ""}`, "details"));
      if (event.type === "usage_reset") item.append(element("p", `${event.actor || "Owner"} · ${event.details.previous_chats || 0} used chat slots reset to 0 for ${event.details.day}. Command history kept.`, "details"));
      events.append(item);
    }
    if (!data.history.length) historyPanel.append(element("p", "No history recorded yet. New membership events and settings changes will appear here.", "details"));
    historyPanel.append(events); target.append(historyPanel);
    const trends = element("details"); trends.open = true; trends.append(element("summary", "Usage over the last 14 days"));
    const table = element("table", undefined, "trend-table"), head = element("tr");
    for (const text of ["Day (UTC)", "Replies", "Commands"]) head.append(element("th", text)); table.append(head);
    for (const day of data.trend) { const row = element("tr"); for (const value of [day.day, day.chats, day.commands]) row.append(element("td", String(value))); table.append(row); }
    if (!data.trend.length) trends.append(element("p", "No usage recorded in this period.", "details")); else trends.append(table);
    target.append(trends, element("h3", "Recent server errors"));
    if (!data.errors.length) target.append(element("p", "No errors retained for this server in the current bot process.", "status-ok"));
    for (const error of data.errors) {
      const row = element("article", undefined, "attention-item"), copy = element("div");
      copy.append(element("strong", `${error.command} · ${error.exception}`), element("p", `${date(error.timestamp)} · Stage: ${error.stage}`, "details"));
      const button = element("button", error.error_id, "quiet"); button.addEventListener("click", () => { switchView("health", false); $("error-id").value = error.error_id; searchErrors({preventDefault(){}}); });
      row.append(copy,button); target.append(row);
    }
  } catch (error) { if (target.dataset.guildId === guildId) target.replaceChildren(element("p", error.message, "details")); }
}

function switchServerPanel(panel, updateUrl = true) {
  if (!["main", "edit", "chat", "commands", "diagnostics"].includes(panel)) panel = "main";
  selectedServerPanel = panel;
  $("dashboard-header").hidden = panel !== "main";
  $("server-main-chrome").hidden = panel !== "main";
  for (const node of document.querySelectorAll(".server-panel")) node.hidden = node.id !== `server-panel-${panel}`;
  for (const node of document.querySelectorAll(".server-nav")) node.classList.toggle("active", node.dataset.panel === panel);
  const server = servers.find(s => s.id === pageServerId);
  if (!server) return;
  const subtitles = {main:"Basic server information.",edit:"Features, command prefix, and daily allowance.",chat:"Conversations with Meyaya, including automatic replies.",commands:"Successful commands and usage counts.",diagnostics:"Membership history, settings audit, and diagnostics."};
  $("page-title").textContent = server.name; $("page-subtitle").textContent = subtitles[panel];
  if (updateUrl) history.pushState(null, "", `/?server=${server.id}&panel=${panel}`);
  if (panel === "main") loadServerBasics(server.id);
  if (panel === "chat") {
    closeRequests(); selectedServer = server; $("request-panel").hidden = false;
    $("request-title").textContent = "AI chat"; loadRequests(false);
  } else { requestVersion++; }
  if (panel === "commands") { loadServerCommands(server.id); loadCommandHistory(false); }
  if (panel === "diagnostics") loadServerInsights(server.id);
}
for (const button of document.querySelectorAll(".server-nav")) button.addEventListener("click", () => switchServerPanel(button.dataset.panel));
$("sidebar-all-servers").addEventListener("click", () => $("server-back").click());
$("chat-kind").addEventListener("change", () => loadRequests(false));
$("command-history-refresh").addEventListener("click", () => loadCommandHistory(false));
$("command-history-more").addEventListener("click", () => loadCommandHistory(true));
async function loadCommandHistory(older) {
  const gid = pageServerId, version = ++commandHistoryVersion;
  if (!gid) return;
  $("command-history-state").textContent = "Loading command history…";
  $("command-history-more").disabled = true;
  try {
    const query = older && commandHistoryCursor ? `?before=${encodeURIComponent(commandHistoryCursor)}` : "";
    const data = await api(`/api/servers/${gid}/command-history${query}`);
    if (!token || pageServerId !== gid || version !== commandHistoryVersion) return;
    if (!older) $("command-history-items").replaceChildren();
    for (const item of data.items) {
      const row = element("article", undefined, "command-history-row");
      row.append(element("code", `${item.response === "slash" ? "/" : ""}${item.content}`), element("span", item.user_name), element("span", item.response === "slash" ? "Slash command" : "Prefix command", "conversation-type"), element("time", new Date(item.created_at).toLocaleString(), "details"));
      $("command-history-items").append(row);
    }
    commandHistoryCursor = data.next_cursor;
    $("command-history-more").hidden = !commandHistoryCursor;
    $("command-history-state").textContent = $("command-history-items").children.length ? `${$("command-history-items").children.length} completed commands shown` : "No command history yet. New completed commands will appear here.";
  } catch (error) { if (version === commandHistoryVersion) $("command-history-state").textContent = error.message; }
  finally { if (version === commandHistoryVersion) $("command-history-more").disabled = false; }
}

function discordMessage(name, content, isBot = false) {
  const row = element("div", undefined, `discord-message${isBot ? " discord-bot-message" : ""}`);
  const heading = element("div", undefined, "discord-message-heading");
  heading.append(element("strong", name));
  row.append(heading, element("div", content, "discord-message-text"));
  return row;
}
$("diagnostics-refresh").addEventListener("click", () => { if (pageServerId) loadServerInsights(pageServerId); });

// Explicit refreshes always bypass the in-memory cache; normal navigation reuses it.
for (const button of document.querySelectorAll('button[id$="refresh"], #refresh')) {
  button.addEventListener("click", invalidateApiCache, {capture: true});
}
