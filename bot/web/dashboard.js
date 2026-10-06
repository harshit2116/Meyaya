"use strict";

let token = "", servers = [], selectedServer = null, requestCursor = null;
let requestVersion = 0, memoryOffset = null, nicknameOffset = null;
let healthLoading = false, healthVersion = 0;
const $ = id => document.getElementById(id);
const notice = message => { $("notice").textContent = message; };
const pageServerId = new URLSearchParams(location.search).get("server");
const serverWindows = new Map();
const serverWindowTimers = new Map();

async function api(path, options = {}) {
  const session = token;
  const response = await fetch(path, {...options, headers: {"Authorization": `Bearer ${token}`, "Content-Type": "application/json"}});
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
  const memberSection = element("section", undefined, "server-members");
  const humans = (data.member_preview || []).filter(member => !member.bot).slice(0, 50);
  memberSection.append(element("h4", `Members (${humans.length} shown · up to 50 · bots excluded)`));
  if (data.member_preview_error) memberSection.append(element("p", data.member_preview_error, "details"));
  const memberList = element("div", undefined, "inventory-list");
  if (data.member_preview?.length === 0 && !data.member_preview_error) memberList.append(element("p", "No members returned.", "details"));
  for (const member of humans) {
    const row = element("article", undefined, "member-row");
    row.append(element("strong", `${member.name}${member.bot ? " · Bot" : ""}`));
    row.append(element("p", `@${member.username} · ${member.id}`, "details"));
    if (member.joined_at) row.append(element("p", `Joined ${new Date(member.joined_at).toLocaleDateString()}`, "details"));
    if (member.roles?.length) row.append(element("p", `Roles: ${member.roles.join(", ")}`, "details"));
    memberList.append(row);
  }
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
  closeRequests(); token = ""; servers = [];
  $("servers").replaceChildren(); $("memory-items").replaceChildren(); $("nickname-items").replaceChildren();
  $("operations-summary").replaceChildren(); $("operations-features").replaceChildren(); $("operations-models").replaceChildren(); $("operations-recent").replaceChildren();
  $("operations-commands").replaceChildren(); $("server-detail-content").replaceChildren(); $("server-controls").replaceChildren(); $("server-heading").replaceChildren();
  $("server-command-usage").replaceChildren();
  $("workspace").hidden = true; $("navigation").hidden = true; $("login").hidden = false;
  $("connection").textContent = "Locked";
}

function switchView(name, autoLoad = true) {
  $("global-stats").hidden = name === "server";
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

function renderServerControls(target, server) {
    target.replaceChildren();
    const card = element("form", undefined, "card");
    card.append(element("h3", "Meyaya settings"), element("div", server.id, "id"), element("span", server.exempt ? "✦ Main server - Unlimited" : `${server.today_chats} / ${server.limit} Meyaya replies today`, "badge"));
    const progress = element("progress"); progress.max = Math.max(1, server.limit); progress.value = server.exempt ? 0 : server.today_chats; progress.setAttribute("aria-label", "Daily allowance used"); card.append(progress);
    const metrics = element("div", undefined, "metrics");
    if (server.local) {
      metrics.append(metric("Members (approx.)", server.members ?? "Unavailable"), metric("Commands today", server.today_commands), metric("Meyaya replies / 7 days", server.week_chats), metric("Commands / 7 days", server.week_commands));
      card.append(metrics, element("p", "Discord metadata is fetched on demand. Process counters are available on the hosted dashboard. Settings apply on the updated host within 60 seconds.", "details"));
    } else {
    metrics.append(metric("Members", server.members ?? "Unknown"), metric("Commands today", server.today_commands), metric("Meyaya replies / 7 days", server.week_chats), metric("Commands / 7 days", server.week_commands), metric("Response success", `${server.model_success_rate}%`), metric("Failed responses", server.model_failures), metric("Average latency", server.model_average_latency_ms === null ? "No data" : `${server.model_average_latency_ms} ms`), metric("Tokens this process", server.model_tokens.toLocaleString())); card.append(metrics);
    card.append(element("p", `${server.available ? "Available" : "Unavailable"} - ${server.readable_channels} readable - ${server.monitored_channels} monitored - Timeout: ${server.can_timeout ? "yes" : "no"}`, "details"));
    card.append(element("p", `${server.active_games} active games - Voice ${server.voice_active ? "connected" : "disconnected"}`, "details"));
    }
    const prefixLabel = element("label", "Command prefix"), prefix = element("input"); prefix.value = server.prefix; prefix.maxLength = 10; prefix.required = true; prefixLabel.append(prefix);
    const limitLabel = element("label", "Daily Meyaya reply allowance (0 disables chat)"), limit = element("input"); limit.type = "number"; limit.min = "0"; limit.max = "10000"; limit.required = true; limit.value = server.limit; limit.disabled = server.exempt; limitLabel.append(limit);
    const toggle = element("label", undefined, "toggle"), auto = element("input"); auto.type = "checkbox"; auto.checked = server.autoresponder; toggle.append(auto, element("span", "Automatic replies enabled"));
    const save = element("button", "Save changes", "save"); card.append(prefixLabel, limitLabel, toggle, save);
    const review = element("button", "View AI chat log", "quiet save"); review.type = "button";
    review.addEventListener("click", () => { closeRequests(); selectedServer = server; $("request-title").textContent = `Requests - ${server.name}`; $("request-panel").hidden = false; $("request-panel").scrollIntoView({behavior: "smooth"}); loadRequests(false); }); card.append(review);
    const shortcuts = element("div", undefined, "card-actions");
    const memories = element("button", "Memories", "quiet"); memories.type = "button";
    memories.addEventListener("click", () => { $("memory-guild").value = server.id; switchView("memories", false); loadMemories(false); });
    const nicknames = element("button", "Nicknames", "quiet"); nicknames.type = "button";
    nicknames.addEventListener("click", () => { $("nickname-guild").value = server.id; switchView("nicknames", false); loadNicknames(false); });
    shortcuts.append(memories, nicknames); card.append(shortcuts);
    card.addEventListener("submit", async event => { event.preventDefault(); save.disabled = true; try { await api(`/api/servers/${server.id}`, {method: "PATCH", body: JSON.stringify({prefix: prefix.value, autoresponder: auto.checked, limit: Number(limit.value)})}); notice(`Saved settings for ${server.name}.`); await refresh(); } catch (error) { notice(error.message); } finally { save.disabled = false; } });
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

function renderServers() {
  const query = $("search").value.toLowerCase();
  const visible = servers.filter(server => `${server.name} ${server.id} ${server.owner_name || ""}`.toLowerCase().includes(query));
  $("servers").replaceChildren(); $("empty").hidden = visible.length > 0;
  for (const server of visible) {
    const card = element("button", undefined, "server-tile"); card.type = "button";
    const icon = serverIcon(server), owner = element("p", `Owner · ${server.owner_name || "Loading…"}`, "server-owner");
    const activity = element("div", undefined, "server-tile-activity");
    activity.append(metric("AI chats today", known(server.today_chats)), metric("Commands today", known(server.today_commands)));
    card.append(icon, element("h3", server.name), owner, activity, element("span", server.id, "id"), element("span", "Open server ↗", "tile-link"));
    card.setAttribute("aria-label", `Open ${server.name} in a new window`);
    card.addEventListener("click", () => openServerWindow(server)); $("servers").append(card);
    if (!server.owner_name) api(`/api/servers/${server.id}/summary`).then(data => {
      if (!card.isConnected || !token) return;
      server.owner_name = data.owner_name; server.icon_url = data.icon_url || server.icon_url;
      owner.textContent = `Owner · ${data.owner_name || "Unavailable"}`;
      icon.replaceWith(serverIcon(server));
    }).catch(() => { if (card.isConnected) owner.textContent = "Owner · Unavailable"; });
  }
}

async function showServer(guildId) {
  switchView("server", false); $("global-stats").hidden = true;
  const server = servers.find(item => item.id === guildId);
  if (!server) { $("server-state").textContent = "Server not found or no longer available to Meyaya."; return; }
  $("page-title").textContent = server.name;
  $("server-heading").replaceChildren(serverIcon(server), element("div", `Owner · ${server.owner_name || "Loading…"}`));
  renderServerControls($("server-controls"), server);
  loadServerCommands(guildId);
  $("server-state").textContent = "Loading server details…";
  try {
    const data = await api(`/api/servers/${guildId}/details`);
    if (!token) return;
    renderServerDetails($("server-detail-content"), data);
    $("server-heading").replaceChildren(serverIcon({...server, icon_url: data.icon_url || server.icon_url}), element("div", `Owner · ${data.owner_name || "Unavailable"}`));
    $("server-state").textContent = "";
  } catch (error) { $("server-state").textContent = error.message; }
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
  const data = await api("/api/servers"); servers = data.servers;
  $("connection").textContent = data.mode === "local" ? "● Local dashboard · cloud database" : data.ready ? "● Connected" : "Connecting to Discord";
  $("total").textContent = servers.length; $("chats").textContent = servers.reduce((n, server) => n + server.today_chats, 0); $("commands").textContent = servers.reduce((n, server) => n + server.today_commands, 0);
  populateGuildFilters();
  if (!pageServerId) renderServers();
  if (pageServerId) {
    for (const id of ["memory-guild", "nickname-guild", "operations-guild"]) $(id).value = pageServerId;
    await showServer(pageServerId);
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
    const query = older && requestCursor ? `?before=${encodeURIComponent(requestCursor)}` : "";
    const data = await api(`/api/servers/${guildId}/requests${query}`);
    if (version !== requestVersion || selectedServer?.id !== guildId) return;
    if (!older) $("request-items").replaceChildren();
    for (const item of data.items) {
      const entry = element("article", undefined, "request-entry");
      entry.append(element("h3", `${item.user_name} - ${item.kind}`), element("p", `${new Date(item.created_at).toLocaleString()} - User ${item.user_id} - Channel ${item.channel_id}`, "details"), element("h4", "User request"), element("pre", item.content, "request-content"), element("h4", "Meyaya's response"));
      entry.append(item.response === null || item.response === undefined ? element("p", "Reply not recorded.", "details") : element("pre", item.response, "request-content response-content"));
      const link = element("a", item.kind === "slash" ? "Open channel in Discord" : "Open message in Discord"); link.href = item.url; link.target = "_blank"; link.rel = "noopener noreferrer"; entry.append(link); $("request-items").append(entry);
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
  refresh().then(() => {
    $("workspace").hidden = false; $("navigation").hidden = false; $("login").hidden = true;
    if (!pageServerId) switchView("overview"); notice("");
  }).catch(error => notice(error.message));
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
$("request-close").addEventListener("click", closeRequests); $("request-refresh").addEventListener("click", () => loadRequests(false)); $("request-more").addEventListener("click", () => loadRequests(true));
$("memory-refresh").addEventListener("click", () => loadMemories(false)); $("memory-more").addEventListener("click", () => loadMemories(true));
$("memory-guild").addEventListener("change", () => loadMemories(false)); $("memory-status").addEventListener("change", () => loadMemories(false)); $("memory-query").addEventListener("change", () => loadMemories(false));
$("nickname-refresh").addEventListener("click", () => loadNicknames(false)); $("nickname-more").addEventListener("click", () => loadNicknames(true));
$("nickname-guild").addEventListener("change", () => loadNicknames(false)); $("nickname-query").addEventListener("change", () => loadNicknames(false));
$("operations-refresh").addEventListener("click", loadOperations); $("operations-guild").addEventListener("change", loadOperations);
$("server-refresh").addEventListener("click", () => refresh().catch(error => notice(error.message)));
$("workspace").append($("request-panel"));
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
