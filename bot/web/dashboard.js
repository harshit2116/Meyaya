"use strict";
let token = "", servers = [];
let selectedServer = null, requestCursor = null, requestVersion = 0;
const $ = id => document.getElementById(id);
const notice = message => { $("notice").textContent = message; };
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {"Authorization": `Bearer ${token}`, "Content-Type": "application/json"}});
  if (!response.ok) {
    if (response.status === 401) lock();
    throw new Error(response.status === 401 ? "Access denied. Check your dashboard token." : `Request failed (${response.status}). Check your settings or retry shortly.`);
  }
  return response.json();
}
function lock() {closeRequests(); token = ""; servers = []; $("servers").replaceChildren(); $("workspace").hidden = true; $("login").hidden = false; $("connection").textContent = "Locked";}
function element(tag, text, className) {const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el;}
function metric(label, value) {const el = element("div"); el.append(element("span", label), element("b", String(value))); return el;}
function render() {
  const query = $("search").value.toLowerCase();
  const visible = servers.filter(s => `${s.name} ${s.id}`.toLowerCase().includes(query));
  $("servers").replaceChildren(); $("empty").hidden = visible.length > 0;
  for (const s of visible) {
    const card = element("form", undefined, "card");
    card.append(element("h3", s.name), element("div", s.id, "id"), element("span", s.exempt ? "✦ Main server · Unlimited" : `${s.today_chats} / ${s.limit} AI messages today`, "badge"));
    const progress = element("progress"); progress.max = Math.max(1, s.limit); progress.value = s.exempt ? 0 : s.today_chats; progress.setAttribute("aria-label", "Daily allowance used"); card.append(progress);
    const metrics = element("div", undefined, "metrics"); metrics.append(metric("Members", s.members ?? "Unknown"), metric("Commands today", s.today_commands), metric("AI messages / 7 days", s.week_chats), metric("Commands / 7 days", s.week_commands)); card.append(metrics);
    card.append(element("p", `${s.available ? "Available" : "Unavailable"} · ${s.readable_channels} readable channels · ${s.monitored_channels} monitored · Timeout permission: ${s.can_timeout ? "yes" : "no"}`, "details"));
    card.append(element("p", `${s.active_games} active games · Voice ${s.voice_active ? "connected" : "disconnected"}`, "details"));
    const prefixLabel = element("label", "Command prefix"), prefix = element("input"); prefix.value = s.prefix; prefix.maxLength = 10; prefix.required = true; prefixLabel.append(prefix);
    const limitLabel = element("label", "Daily AI allowance (0 disables chat)"), limit = element("input"); limit.type = "number"; limit.min = "0"; limit.max = "10000"; limit.step = "1"; limit.required = true; limit.value = s.limit; limit.disabled = s.exempt; limitLabel.append(limit);
    const toggle = element("label", undefined, "toggle"), auto = element("input"); auto.type = "checkbox"; auto.checked = s.autoresponder; toggle.append(auto, element("span", "Automatic replies enabled"));
    const save = element("button", "Save changes", "save"); card.append(prefixLabel, limitLabel, toggle, save);
    const review = element("button", "View requests →", "quiet save"); review.type = "button";
    review.addEventListener("click", () => {closeRequests(); selectedServer = s; $("request-title").textContent = `Requests · ${s.name}`; $("request-panel").hidden = false; $("request-panel").scrollIntoView({behavior:"smooth"}); loadRequests(false);}); card.append(review);
    card.addEventListener("submit", async event => {event.preventDefault(); save.disabled = true; try {await api(`/api/servers/${s.id}`, {method:"PATCH", body:JSON.stringify({prefix:prefix.value, autoresponder:auto.checked, limit:Number(limit.value)})}); notice(`Saved settings for ${s.name}.`); await refresh();} catch(error) {notice(error.message);} finally {save.disabled = false;}});
    $("servers").append(card);
  }
}
async function refresh() {const data = await api("/api/servers"); servers = data.servers; $("connection").textContent = data.ready ? "● Connected" : "Connecting to Discord"; $("total").textContent = servers.length; $("chats").textContent = servers.reduce((n,s)=>n+s.today_chats,0); $("commands").textContent = servers.reduce((n,s)=>n+s.today_commands,0); render();}
$("login-form").addEventListener("submit", async event => {event.preventDefault(); token = $("token").value; $("token").value = ""; try {await refresh(); $("workspace").hidden = false; $("login").hidden = true; notice("");} catch(error) {notice(error.message);}});
$("logout").addEventListener("click", () => {lock(); notice("");});
$("refresh").addEventListener("click", () => refresh().catch(error => notice(error.message)));
$("search").addEventListener("input", render);

function closeRequests() {requestVersion++; selectedServer = null; requestCursor = null; $("request-panel").hidden = true; $("request-items").replaceChildren(); $("request-state").textContent = ""; $("request-more").hidden = true;}
async function loadRequests(older) {
  if (!selectedServer || !token) return;
  const version = ++requestVersion, guildId = selectedServer.id;
  $("request-state").textContent = "Loading…"; $("request-more").disabled = true;
  try {
    const query = older && requestCursor ? `?before=${encodeURIComponent(requestCursor)}` : "";
    const data = await api(`/api/servers/${guildId}/requests${query}`);
    if (version !== requestVersion || !token || selectedServer?.id !== guildId) return;
    if (!older) $("request-items").replaceChildren();
    for (const item of data.items) {
      const entry = element("article", undefined, "request-entry");
      entry.append(element("h3", `${item.user_name} · ${item.kind}`));
      entry.append(element("p", `${new Date(item.created_at).toLocaleString()} · User ${item.user_id} · Channel ${item.channel_id}`, "details"));
      entry.append(element("pre", item.content, "request-content"));
      const link = element("a", item.kind === "slash" ? "Open channel in Discord ↗" : "Open message in Discord ↗"); link.href = item.url; link.target = "_blank"; link.rel = "noopener noreferrer"; entry.append(link);
      $("request-items").append(entry);
    }
    requestCursor = data.next_cursor; $("request-more").hidden = !requestCursor;
    $("request-state").textContent = $("request-items").children.length ? `${$("request-items").children.length} requests shown` : "No recorded requests in the last seven days.";
  } catch(error) {if (version === requestVersion) $("request-state").textContent = error.message;}
  finally {if (version === requestVersion) $("request-more").disabled = false;}
}
$("request-close").addEventListener("click", closeRequests);
$("request-refresh").addEventListener("click", () => loadRequests(false));
$("request-more").addEventListener("click", () => loadRequests(true));
