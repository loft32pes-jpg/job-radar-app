/* Job Radar, app per telefono e computer. Tutto il testo che arriva dagli annunci viene scritto come testo, mai come HTML. */
(() => {
"use strict";
const $app = document.getElementById("app");
const store = {
  get(k, d){ try { const v = localStorage.getItem("jr." + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v){ try { localStorage.setItem("jr." + k, JSON.stringify(v)); } catch (e) {} },
  del(k){ try { localStorage.removeItem("jr." + k); } catch (e) {} },
};
const S = { token: store.get("token", null), data: null, place: null, appFilter: "active", tab: "jobs", shown: 40, poll: null,
            f: Object.assign({q:"", min:0, fam:"", country:"", mode:"", fresh:false, sort:"score"}, store.get("filters", {})) };

/* ---------- utilità ---------- */
function h(tag, attrs, ...kids){
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})){
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "html") n.innerHTML = v;          // solo per disegni scritti in questo file
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) n.append(c.nodeType ? c : document.createTextNode(String(c)));
  return n;
}
const ICON = {
  refresh: '<svg viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4v5h-5"/></svg>',
  search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>',
  star: '<svg viewBox="0 0 24 24"><path d="M12 3.6l2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z"/></svg>',
  list: '<svg viewBox="0 0 24 24"><path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/></svg>',
  user: '<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 20c1.5-4 5-5 8-5s6.500 1 8 5"/></svg>',
  close: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  board: '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="5" height="16" rx="1.5"/><rect x="10" y="4" width="5" height="11" rx="1.5"/><rect x="17" y="4" width="4" height="7" rx="1.5"/></svg>',
  out: '<svg viewBox="0 0 24 24"><path d="M14 5h5v14h-5"/><path d="M4 12h11M11 8l4 4-4 4"/></svg>',
  mic: '<svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
  logo: '<svg viewBox="0 0 32 32" aria-hidden="true"><circle class="ring" cx="16" cy="16" r="14"/><circle class="ring" cx="16" cy="16" r="8.500"/><g class="sweep"><path d="M16 16L16 2A14 14 0 0 1 28.100 9z" fill="#36F2A0" opacity=".28"/></g><circle cx="16" cy="16" r="2.200" fill="#36F2A0"/><circle cx="22" cy="10" r="1.800" fill="#36F2A0"/></svg>',
};
const masc = who => h("span", {class:"masc", html: window.MASC[who]});
const says = (who, name, text) => h("div", {class:"says"}, masc(who), h("div", {class:"bubble"}, h("b", null, name), text));
let toastT;
function toast(text){ const t = document.getElementById("toast"); t.textContent = text; t.classList.add("on"); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("on"), 3200); }
async function api(action, body){
  let r;
  try {
    r = await fetch("/api/index?a=" + action, { method: body ? "POST" : "GET", cache: "no-store",
      headers: Object.assign({"Content-Type":"application/json"}, S.token ? {Authorization: "Bearer " + S.token} : {}),
      body: body ? JSON.stringify(body) : undefined });
  } catch (e) { return {ok:false, error:"Non riesco a collegarmi. Controlla la connessione e riprova."}; }
  let j; try { j = await r.json(); } catch (e) { j = {ok:false, error:"Il servizio non risponde. Riprova tra un momento."}; }
  if (r.status === 401 && action !== "login"){ logout(true); }
  return j;
}
const keyOf = j => j.url;
const tracker = () => (S.data && S.data.tracker) || {};
const favs = () => tracker().favs || {};
const hidden = () => tracker().hidden || {};
function fmtWhen(iso){
  if (!iso) return "";
  const d = new Date(iso); if (isNaN(d)) return "";
  const mins = Math.round((Date.now() - d) / 60000);
  if (mins < 60) return mins <= 1 ? "adesso" : mins + " minuti fa";
  if (mins < 60 * 24) return Math.round(mins / 60) + " ore fa";
  return d.toLocaleDateString("it-IT", {day:"numeric", month:"long"}) + " alle " + d.toLocaleTimeString("it-IT", {hour:"2-digit", minute:"2-digit"});
}
const MODE = {remote:"Da remoto", hybrid:"Ibrido", onsite:"In sede"};
const modeOf = j => { const m = String(j.mode || "").toLowerCase(); return m.includes("remot") ? "remote" : m.includes("ibrid") || m.includes("hybrid") ? "hybrid" : m.includes("sede") || m.includes("site") ? "onsite" : ""; };
const asText = v => Array.isArray(v) ? v.join(", ") : (v == null ? "" : String(v));
const EN_COUNTRY = new Set("italy spain france germany united kingdom uk ireland netherlands belgium switzerland portugal austria luxembourg sweden denmark norway finland poland czechia czech republic hungary romania greece estonia latvia lithuania croatia slovenia slovakia bulgaria malta cyprus europe emea".split(" "));
const place = j => [j.city && !EN_COUNTRY.has(String(j.city).toLowerCase()) && j.city !== j.country ? j.city : "", j.country].filter(Boolean).join(", ");

/* ---------- accesso ---------- */
const myLink = () => location.origin + "/#t=" + encodeURIComponent(S.token || "");
function linkBox(){
  const copy = h("button", {class:"btn", type:"button", onclick: async () => {
    try { await navigator.clipboard.writeText(myLink()); toast("Link copiato"); } catch (e) { prompt("Copia il tuo link personale:", myLink()); } }}, "Copia il mio link");
  const share = navigator.share ? h("button", {class:"btn", type:"button", onclick: () => navigator.share({title: "Job Radar", url: myLink()}).catch(() => {})}, "Mandalo a me stesso") : null;
  return h("div", null,
    h("p", {class:"hint"}, "Per usare Job Radar anche sul computer o su un altro telefono, apri lì questo link: ritrovi gli stessi annunci e le stesse candidature. È la tua chiave: mandalo solo a te stesso (per esempio su WhatsApp, nella chat con te)."),
    h("div", {class:"actions", style:"flex-wrap:wrap"}, copy, share));
}
function logout(expired){
  if (expired){ S.token = null; S.data = null; store.del("token"); idb.set("cache", null).catch(() => {}); stopPoll(); closeSheet(); return viewLogin("L'accesso su questo dispositivo è scaduto: apri il tuo link personale, oppure ricomincia."); }
  openSheet(h("h2", null, "Uscire da Job Radar?"),
    h("div", null, h("p", {class:"lead"}, "Per rientrare con il tuo profilo ti servirà il tuo link personale. Copialo prima di uscire, se non l'hai già."), linkBox()),
    h("div", {class:"actions"}, h("button", {class:"btn", type:"button", onclick: closeSheet}, "Resto"),
      h("button", {class:"btn solid", type:"button", onclick: () => { S.token = null; S.data = null; store.del("token"); idb.set("cache", null).catch(() => {}); stopPoll(); closeSheet(); viewLogin(""); }}, "Esci")));
}
function viewLogin(message){
  const inp = h("input", {type:"text", id:"name", autocomplete:"given-name", maxlength:"40", placeholder:"Il tuo nome", "aria-label":"Come ti chiami"});
  const msg = h("p", {class:"msg", role:"alert"}, message || "");
  const go = h("button", {class:"btn solid", type:"submit"}, "Inizia");
  const form = h("form", {onsubmit: async e => {
    e.preventDefault(); if (inp.value.trim().length < 2){ msg.textContent = "Scrivi come ti chiami."; return; }
    go.disabled = true; go.textContent = "Un momento..."; msg.textContent = "";
    const r = await api("entra", {name: inp.value});
    go.disabled = false; go.textContent = "Inizia";
    if (!r.ok){ msg.textContent = r.error; return; }
    S.token = r.token; store.set("token", r.token); boot();
  }}, h("div", {class:"field"}, h("label", {for:"name"}, "Come ti chiami?"), inp), msg, h("div", {class:"actions"}, go));
  // chi ha già un profilo (su un altro dispositivo) rientra con il link personale; resta anche il vecchio codice
  const code = h("input", {class:"code", type:"text", autocomplete:"off", autocapitalize:"characters", spellcheck:"false", placeholder:"XXXX-XXXX-XXXX", "aria-label":"Codice di accesso"});
  const cmsg = h("p", {class:"msg", role:"alert"});
  const old = h("details", {class:"oldaccess"}, h("summary", null, "Hai già un profilo su un altro dispositivo?"),
    h("p", {class:"hint"}, "Sul dispositivo dove usi già Job Radar vai in Profilo e premi «Copia il mio link», poi apri quel link qui."),
    h("form", {onsubmit: async e => {
      e.preventDefault(); if (code.value.trim().length < 6) return;
      const r = await api("login", {code: code.value});
      if (!r.ok){ cmsg.textContent = r.error; return; }
      S.token = r.token; store.set("token", r.token); boot();
    }}, h("p", {class:"hint"}, "Se ti era stato dato un codice di accesso, puoi ancora usarlo:"), code, cmsg, h("div", {class:"actions"}, h("button", {class:"btn", type:"submit"}, "Entra con il codice"))));
  $app.replaceChildren(
    h("header", {class:"top"}, h("div", {class:"brand", html: ICON.logo + "<span>Job Radar</span>"})),
    h("main", null, h("div", {class:"center"},
      h("h1", null, "Il lavoro giusto, ", h("em", null, "trovato per te")),
      h("p", {class:"lead"}, "Ogni giorno Job Radar legge gli annunci nuovi, nella tua città e in Europa, e tiene solo quelli adatti a te."),
      says("ada", "Vale", "Ciao! Sono Vale. Dimmi come ti chiami e partiamo: niente password, niente registrazione."),
      form, old)));
  inp.focus();
}

/* ---------- avvio e struttura ---------- */
async function boot(){
  const fromLink = /^#t=(.+)$/.exec(location.hash);  // link personale aperto su un altro dispositivo
  if (fromLink){ S.token = decodeURIComponent(fromLink[1]); store.set("token", S.token); history.replaceState(null, "", location.pathname); }
  if (!S.token) return viewLogin();
  // apertura istantanea: si mostra subito l'ultima copia salvata su questo dispositivo, intanto arrivano i dati freschi
  const me_ = String(S.token).split(".")[0], cached = await idb.get("cache");
  const fromCache = !!(cached && cached.uid === me_ && cached.data && cached.data.profile);
  if (fromCache){ S.data = cached.data; render(); }
  else $app.replaceChildren(h("main", null, h("div", {class:"center"}, h("div", {class:"radarbox", html: radarSvg()}), h("p", {class:"lead", style:"text-align:center"}, "Carico i tuoi annunci..."))));
  const r = await api("dati");
  if (!r.ok){ if (fromCache){ toast("Non riesco ad aggiornare: ti mostro gli ultimi annunci scaricati"); return; }
    if (S.token) $app.replaceChildren(h("main", null, h("div", {class:"center"}, h("p", {class:"lead"}, r.error), h("button", {class:"btn solid", onclick: boot}, "Riprova")))); return; }
  S.data = r;
  idb.set("cache", {uid: me_, data: r}).catch(() => {});
  if (fromCache && (sheetEl || recog)) return;  // non si cambia lo schermo sotto le mani di chi sta scrivendo o parlando
  if (r.token){ S.token = r.token; store.set("token", r.token); }  // accesso rinnovato a ogni apertura
  if (!r.profile) return viewInterview();
  render();
  if (r.state && r.state.running) startPoll();
}
function shell(content){
  const run = S.data.state && S.data.state.running;
  const refresh = h("button", {class:"pill" + (run ? " busy" : ""), type:"button", onclick: refreshNow, html: ICON.refresh + "<span>" + (run ? "Ricerca in corso" : "Aggiorna") + "</span>"});
  const nApps = Object.values(favs()).filter(f => f.state !== "discarded").length;
  const tab = (id, icon, label, count) => h("button", {type:"button", "aria-current": S.tab === id ? "page" : null, onclick: () => { stopRecog(); if (id === "int") S.cid = null; S.merc = false; S.tab = id; S.shown = 40; render(); window.scrollTo(0, 0); }, html: icon},
    h("span", null, label, count ? h("span", {class:"count"}, " " + count) : null));
  $app.replaceChildren(
    h("header", {class:"top"}, h("div", {class:"brand", html: ICON.logo + "<span>Job Radar</span>"}), refresh),
    h("main", {class: S.tab === "favs" && !S.merc ? "wide" : null}, content),
    h("nav", {class:"tabs", "aria-label":"Sezioni"}, tab("jobs", ICON.list, "Annunci"), tab("favs", ICON.board, "Candidature", nApps),
      tab("int", ICON.mic, "Colloqui", Object.values(colloqui()).filter(c => !isPast(c)).length + Object.entries(favs()).filter(([k, f]) => f.state === "interview" && !Object.values(colloqui()).some(c => c.key === k)).length), tab("me", ICON.user, "Profilo")));
}
function render(){
  if (S.tab === "favs") return shell(S.merc ? viewMercato() : viewApps());
  if (S.tab === "me") return shell(viewMe());
  if (S.tab === "int") return shell(S.cid ? viewColloquio(S.cid) : viewColloqui());
  shell(S.data.state && S.data.state.running && !S.data.jobs.length ? viewWaiting() : viewJobs());
}

/* ---------- annunci ---------- */
/* "nuovo" = trovato per la prima volta nelle ultime 24 ore (le ricerche sono tre al giorno: non solo l'ultima) */
const recent = j => { const t = Date.parse(j.first_seen || ""); return !isNaN(t) && Date.now() - t < 864e5; };
function ring(score){
  const c = 2 * Math.PI * 22, cls = score >= 75 ? "" : score >= 55 ? " mid" : " low";
  return h("div", {class:"ring" + cls, html: `<svg viewBox="0 0 52 52"><circle class="bgc" cx="26" cy="26" r="22"/><circle class="fg" cx="26" cy="26" r="22" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - Math.max(0, Math.min(100, score)) / 100)}"/></svg>`},
    h("b", null, String(score)));
}
function starBtn(j){
  const f = favs()[keyOf(j)], on = !!f && f.state !== "discarded";
  return h("button", {class:"star", type:"button", "aria-pressed": String(on), "aria-label": on ? "Togli dalle candidature" : "Mi interessa: aggiungi alle candidature", html: ICON.star,
    onclick: e => { e.stopPropagation(); toggleFav(j); }});
}
function card(j, fav){
  const isNew = recent(j);
  const f = fav || favs()[keyOf(j)];
  const tags = [isNew && !f ? h("span", {class:"tag new"}, "Nuovo") : null,
    f ? h("span", {class:"tag st st-" + f.state}, STATE[f.state] || "Mi interessa") : null,
    j.preferred ? h("span", {class:"tag pref"}, "Settore che preferisci") : null,
    MODE[modeOf(j)] ? h("span", {class:"tag"}, MODE[modeOf(j)]) : null,
    S.data.families[j.role_family] ? h("span", {class:"tag"}, S.data.families[j.role_family]) : null,
    j.local_ad ? h("span", {class:"tag loc"}, "Annuncio in lingua locale") : null];
  return h("div", {class:"card", role:"button", tabindex:"0", onclick: () => openJob(j), onkeydown: e => { if (e.key === "Enter" || e.key === " "){ e.preventDefault(); openJob(j); } }},
    ring(j.score),
    h("div", null, h("h3", null, j.title_it || j.title), h("div", {class:"co"}, [j.company, place(j)].filter(Boolean).join(" · ")),
      j.ai_why ? h("div", {class:"why"}, j.ai_why) : null, h("div", {class:"tags"}, tags)),
    starBtn(j));
}
/* città scritta in qualsiasi lingua: il server la riconosce ("Torino", "Turin", "都灵") e qui si tengono gli annunci entro 35 km */
const RADIUS_KM = 35;
function km(a, b, c, d){ const r = Math.PI / 180, x = Math.sin((c - a) * r / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin((d - b) * r / 2) ** 2; return 12742 * Math.asin(Math.sqrt(x)); }
function inPlace(j, p){
  if (!p) return false;
  if (p.type === "country") return j.country === p.country;
  if (j.near && j.near === p.name) return true;  // trovato cercando proprio in quella città
  if (j.lat != null && j.geo === "city") return km(p.lat, p.lon, j.lat, j.lon) <= RADIUS_KM;
  return String(j.city || "").toLowerCase() === String(p.name).toLowerCase();
}
let placeT, placeQ = "";
function lookPlace(q){
  clearTimeout(placeT);
  const v = q.trim();
  if (v.length < 2){ S.place = null; drawList(); return; }
  placeT = setTimeout(async () => {
    placeQ = v;
    const r = await api("luogo", {q: v});
    if (placeQ !== v) return;  // nel frattempo ha scritto altro
    S.place = r.ok && r.place ? Object.assign(r.place, {typed: v}) : null;
    drawList();
  }, 350);
}
function filtered(){
  const f = S.f, q = f.q.trim().toLowerCase(), hid = hidden(), runAt = S.data.run && S.data.run.at, p = S.place;
  let out = S.data.jobs.filter(j => !hid[keyOf(j)] && j.score >= f.min && (!f.fam || j.role_family === f.fam) && (!f.country || j.country === f.country) &&
    (!f.mode || modeOf(j) === f.mode) && (!f.fresh || recent(j)) &&
    (!q || inPlace(j, p) || (j.title + " " + (j.title_it || "") + " " + j.company + " " + (j.city || "") + " " + j.country).toLowerCase().includes(q)));
  if (f.sort === "date") out = out.slice().sort((a, b) => String(b.posted_at || "").localeCompare(String(a.posted_at || "")));
  return out;
}
function setF(k, v){ S.f[k] = v; S.shown = 40; store.set("filters", Object.assign({}, S.f, {q:""})); drawList(); }
function viewJobs(){
  const d = S.data, jobs = d.jobs.filter(j => !hidden()[keyOf(j)]);
  if (!d.run && !jobs.length) return viewWaiting();
  const countries = [...new Set(jobs.map(j => j.country))].sort((a, b) => a.localeCompare(b, "it"));
  const famCount = {}; jobs.forEach(j => { famCount[j.role_family] = (famCount[j.role_family] || 0) + 1; });
  const top = jobs.filter(j => j.score >= 80).length;
  const hero = h("section", {class:"hero"},
    h("div", {class:"eyebrow"}, (myPlaces().length ? myPlaces().map(p => p.typed || p.name).join(", ") + ": ultima settimana · " : "") + "Europa: ultime 24 ore" + (d.run ? " · aggiornato " + fmtWhen(d.run.at) : "")),
    h("h1", null, h("em", null, String(jobs.length)), " annunci adatti a te"),
    h("div", {class:"stats"},
      h("div", {class:"stat"}, h("b", null, String(top)), h("span", null, "voto da 80 in su")),
      h("div", {class:"stat"}, h("b", null, String(jobs.filter(recent).length)), h("span", null, "nuovi nelle ultime 24 ore")),
      h("div", {class:"stat"}, h("b", null, String(countries.length)), h("span", null, "paesi")),
      h("div", {class:"stat"}, h("b", null, String(jobs.filter(j => modeOf(j) === "remote").length)), h("span", null, "da remoto"))),
    (d.run && d.run.notes || []).map(n => h("div", {class:"note"}, n)),
    d.state && d.state.ok === false && d.state.error ? h("div", {class:"note"}, d.state.error) : null);
  const q = h("input", {type:"search", placeholder:"Cerca ruolo, azienda, città (in qualsiasi lingua)", value: S.f.q, "aria-label":"Cerca tra gli annunci",
    oninput: e => { S.f.q = e.target.value; S.shown = 40; drawList(); lookPlace(e.target.value); }});
  if (S.f.q && !S.place) lookPlace(S.f.q);
  const chip = (label, on, fn) => h("button", {class:"chip", type:"button", "aria-pressed": String(!!on), onclick: fn}, label);
  const placeChips = myPlaces().map(p => { const name = p.typed || p.name, on = S.f.q.trim().toLowerCase() === name.toLowerCase();
    return chip("📍 " + name, on, () => { S.f.q = on ? "" : name; q.value = S.f.q; S.shown = 40; S.place = null; lookPlace(S.f.q); drawList(); render(); }); });
  const sel = (label, value, opts, fn) => { const s = h("select", {class:"chip", "aria-label": label, onchange: e => fn(e.target.value)}, opts.map(([v, t]) => h("option", {value: v, selected: v === value}, t))); if (value && value !== "0" && value !== "score") s.setAttribute("aria-pressed", "true"); return s; };
  const chips = h("div", {class:"chips"}, placeChips,
    sel("Voto minimo", String(S.f.min), [["0","Tutti i voti"],["60","Voto da 60"],["75","Voto da 75"],["85","Voto da 85"]], v => { setF("min", +v); render(); }),
    sel("Tipo di ruolo", S.f.fam, [["","Tutti i ruoli"]].concat(Object.entries(d.families).filter(([k]) => famCount[k]).map(([k, n]) => [k, `${n} (${famCount[k]})`])), v => { setF("fam", v); render(); }),
    sel("Paese", S.f.country, [["","Tutti i paesi"]].concat(countries.map(c => [c, c])), v => { setF("country", v); render(); }),
    chip("Da remoto", S.f.mode === "remote", () => { setF("mode", S.f.mode === "remote" ? "" : "remote"); render(); }),
    chip("Ibrido", S.f.mode === "hybrid", () => { setF("mode", S.f.mode === "hybrid" ? "" : "hybrid"); render(); }),
    chip("Solo nuovi", S.f.fresh, () => { setF("fresh", !S.f.fresh); render(); }),
    sel("Ordine", S.f.sort, [["score","Per voto"],["date","Più recenti"]], v => { setF("sort", v); render(); }));
  const box = h("div", {id:"listbox"});
  const wrap = h("div", null, hero, h("div", {class:"filters"}, h("label", {class:"search", html: ICON.search}, q), chips), box);
  queueMicrotask(drawList);
  return wrap;
}
function drawList(){
  const box = document.getElementById("listbox"); if (!box) return;
  const all = filtered(), part = all.slice(0, S.shown), p = S.place && S.f.q.trim() ? S.place : null;
  const near = p ? all.filter(j => inPlace(j, p)).length : 0;
  box.replaceChildren(...[
    p ? h("div", {class:"placeline"}, h("span", {class:"pin"}, "📍"),
      p.type === "city" ? `${p.typed} = ${p.name}, ${p.country}: ${near} ${near === 1 ? "annuncio" : "annunci"} entro ${RADIUS_KM} km` : `${p.typed} = ${p.country}: ${near} annunci`) : null,
    p && p.type === "city" && !myPlaces().some(x => x.name === p.name) ? h("div", {class:"note"}, `Vuoi che cerchi ogni giorno anche a ${p.typed}, con gli annunci dell'ultima settimana? `,
      myPlaces().length >= 3 ? "Puoi avere al massimo tre città: cambiale in Profilo." :
      h("button", {class:"linkbtn", type:"button", onclick: e => addPlace(p.typed, e.target)}, `Sì, cerca anche a ${p.typed}`)) : null,
    h("div", {class:"countline"}, all.length === 1 ? "1 annuncio" : all.length + " annunci" + (all.length !== S.data.jobs.length ? " con questi filtri" : "")),
    all.length ? h("div", {class:"list"}, part.map(j => card(j))) :
      h("div", {class:"empty"}, "Nessun annuncio con questi filtri.", h("div", null, h("button", {class:"linkbtn", type:"button", onclick: () => { Object.assign(S.f, {q:"", min:0, fam:"", country:"", mode:"", fresh:false}); S.place = null; store.set("filters", S.f); render(); }}, "Azzera i filtri"))),
    all.length > S.shown ? h("button", {class:"pill more", type:"button", onclick: () => { S.shown += 40; drawList(); }}, `Mostra altri (${all.length - S.shown})`) : null].filter(Boolean));
}

const myPlaces = () => (S.data && S.data.profile && S.data.profile.answers && S.data.profile.answers.places) || [];
async function saveCities(list, btn, search){
  if (btn) btn.disabled = true;
  const r = await api("citta", {cities: list, cerca: search});
  if (btn) btn.disabled = false;
  if (!r.ok){ toast(r.error); return false; }
  const a = S.data.profile.answers; a.places = r.places; a.cities = r.places.map(p => p.typed);
  if (r.started){ S.data.state = {running: true, started_at: new Date().toISOString()}; startPoll(); toast("Ricerca avviata: tra circa un quarto d'ora trovi i nuovi annunci"); }
  else toast(search ? "Salvato: la cerco alla prossima ricerca (l'ultima è di poco fa)" : "Salvato: vale dalla prossima ricerca");
  render(); return true;
}
function addPlace(typed, btn){ return saveCities(myPlaces().map(p => p.typed || p.name).concat(typed), btn, true); }

/* ---------- schede (pannello che sale dal basso sul telefono, laterale sul computer) ---------- */
const STATE = {interested:"Mi interessa", applied:"Candidatura inviata", replied:"Mi hanno risposto", cv_requested:"Mi hanno chiesto il CV",
               interview:"Colloquio", offer:"Offerta", closed:"Non è andata", discarded:"Scartato"};
const STATE_ORDER = Object.keys(STATE);
let sheetEl, scrimEl;
function closeSheet(){
  if (!sheetEl) return;
  const s = sheetEl, c = scrimEl; sheetEl = scrimEl = null;
  s.classList.remove("on"); c.classList.remove("on"); document.body.style.overflow = "";
  setTimeout(() => { s.remove(); c.remove(); }, 260);
}
function openSheet(head, body, foot, wide){
  const keep = sheetEl && sheetEl.querySelector(".body") && sheetEl.dataset.k === String(wide || "");
  const top = keep ? sheetEl.querySelector(".body").scrollTop : 0;
  if (sheetEl){ sheetEl.remove(); scrimEl.remove(); sheetEl = scrimEl = null; }
  scrimEl = h("div", {class:"scrim on", onclick: closeSheet});
  sheetEl = h("section", {class:"sheet" + (wide ? " wide" : "") + (keep ? " on" : ""), role:"dialog", "aria-modal":"true", "data-k": String(wide || "")},
    h("div", {class:"grab"}, h("i")), h("div", {class:"head"}, head, h("button", {class:"iconbtn", type:"button", "aria-label":"Chiudi", html: ICON.close, onclick: closeSheet, style:"margin-left:auto;flex:none"})),
    h("div", {class:"body"}, body), foot ? h("div", {class:"foot"}, foot) : null);
  document.body.append(scrimEl, sheetEl); document.body.style.overflow = "hidden";
  if (keep) sheetEl.querySelector(".body").scrollTop = top;
  else requestAnimationFrame(() => { sheetEl && sheetEl.classList.add("on"); });
}
document.addEventListener("keydown", e => { if (e.key === "Escape") closeSheet(); });
function statusChips(key, job, current){
  return h("div", {class:"seg", role:"group", "aria-label":"Stato della candidatura"},
    STATE_ORDER.map(s => h("button", {type:"button", class:"segb st-" + s, "aria-pressed": String(current === s), onclick: () => setState(key, job, s)}, STATE[s])));
}
function openJob(j){
  const key = keyOf(j), fav = favs()[key];
  if (fav && fav.state !== "discarded") return openApp(key);
  const facts = [["Dove", place(j) || "Non indicato"], ["Modalità", MODE[modeOf(j)]], ["Stipendio", asText(j.salary)], ["Lingue", asText(j.languages)],
    ["Contratto", asText(j.contract)], ["Livello", asText(j.level)], ["Pubblicato", fmtWhen(j.posted_at)], ["Fonte", j.source], ["Tipo di ruolo", S.data.families[j.role_family]]].filter(x => x[1]);
  const body = [
    j.ai_fit != null ? h("div", {class:"verdict"}, masc("vaglio"), h("div", null, h("small", null, "Il parere di Tina"), h("p", null, j.ai_why || "Valutato sul testo dell'annuncio."),
      j.ai_like != null ? h("small", null, `Adatta a te ${j.ai_fit} su 100 · Vicino a ciò che scegli ${j.ai_like} su 100`) : null,
      j.ai_gap ? h("p", null, "Da sapere: " + j.ai_gap) : null), h("div", {class:"fit"}, String(j.ai_fit))) : null,
    h("div", {class:"sec"}, h("h4", null, "In breve"), h("div", {class:"facts"}, facts.map(([k, v]) => h("div", {class:"fact"}, h("span", null, k), h("b", null, v))))),
    (j.reasons || []).length ? h("div", {class:"sec"}, h("h4", null, "Perché questo voto"), h("ul", {class:"reasons"}, j.reasons.map(r => h("li", {class: r.k === "ok" ? "" : r.k === "bad" ? "bad" : "warn"}, r.t)))) : null,
    (j.skills || []).length ? h("div", {class:"sec"}, h("h4", null, "Competenze citate"), h("div", {class:"tags"}, j.skills.map(s => h("span", {class:"tag"}, s)))) : null,
    j.excerpt ? h("div", {class:"sec"}, h("h4", null, "Dall'annuncio"), h("p", {class:"excerpt"}, j.excerpt)) : null,
    h("div", {class:"sec"}, h("h4", null, "Che ne pensi?"), h("div", {class:"duo"},
      h("button", {class:"btn", type:"button", onclick: () => setState(key, j, "discarded")}, "Scarta"),
      h("button", {class:"btn solid", type:"button", onclick: () => setState(key, j, "interested")}, "Mi interessa"))),
    h("button", {class:"linkbtn", type:"button", onclick: () => hideJob(j)}, "Nascondi questo annuncio dall'elenco")];
  const open = h("a", {class:"btn", href: /^https?:\/\//.test(j.url) ? j.url : "#", target:"_blank", rel:"noopener noreferrer"}, "Apri l'annuncio");
  const apply = h("button", {class:"btn solid", type:"button", onclick: () => setState(key, j, "interested", true)}, "Candidati con l'AI");
  openSheet(h("div", null, h("h2", null, j.title_it || j.title), h("div", {class:"co"}, [j.company, place(j)].filter(Boolean).join(" · ")),
    j.title_it ? h("div", {class:"co", style:"font-size:13px"}, "Titolo originale: " + j.title) : null), body, [open, apply]);
}
async function track(body, okText){
  const r = await api("preferito", body);
  if (!r.ok){ toast(r.error); return false; }
  S.data.tracker = r.tracker; if (okText) toast(okText); return true;
}
/* stato di una candidatura: si aggiorna subito sullo schermo, il salvataggio segue (se non riesce si ricarica) */
async function setState(key, job, state, thenKit){
  const t = S.data.tracker = S.data.tracker || {}; t.favs = t.favs || {};
  const isNew = !t.favs[key];
  if (isNew) t.favs[key] = {job, state, note:"", log:[{s: state, t: new Date().toISOString().slice(0, 10)}]};
  else { t.favs[key].state = state; (t.favs[key].log = t.favs[key].log || []).push({s: state, t: new Date().toISOString().slice(0, 10)}); }
  const label = state === "discarded" ? "Scartato" : isNew ? "Aggiunto alle candidature" : "Stato: " + STATE[state];
  if (state === "interview" && !Object.values(colloqui()).some(c => c.key === key && !isPast(c))){ closeSheet(); render(); setTimeout(() => openSchedule(null, key), 280); }
  else if (state === "discarded"){ closeSheet(); render(); setTimeout(() => askWhy(key, job), 280); }
  else { render(); openApp(key, thenKit); }
  const ok = await track(isNew ? {key, fav: true, job, state} : {key, state}, label);
  if (!ok){ const r = await api("dati"); if (r.ok) S.data = r; render(); return; }
  if (sheetEl && sheetEl.dataset.k === key && !thenKit && state !== "interview") openApp(key);
}
const WHY = ["Ruolo diverso da quello che cerco", "Settore che non mi interessa", "Troppo senior", "Troppo junior", "Città o zona",
             "Agenzia per il lavoro", "Lingua richiesta", "Non mi convince l'azienda"];
function askWhy(key, job){  /* facoltativo: un tocco basta, e la ricerca impara */
  const f = favs()[key]; if (!f) return;
  const other = h("input", {type:"text", maxlength:"120", placeholder:"Altro motivo (facoltativo)", "aria-label":"Altro motivo"});
  const send = async why => { closeSheet(); f.why = why; await track({key, why}, "Grazie: ne terrò conto per i prossimi annunci"); };
  openSheet(h("div", null, h("h2", null, "Perché lo scarti?"), h("div", {class:"co"}, [job.title, job.company].filter(Boolean).join(" · "))),
    h("div", null, h("p", {class:"hint"}, "Facoltativo. Con il motivo imparo a toglierti gli annunci simili, non solo questo."),
      h("div", {class:"wrap"}, WHY.map(w => h("button", {class:"chip", type:"button", onclick: () => send(w)}, w))),
      h("div", {class:"cityrow"}, other, h("button", {class:"btn", type:"button", onclick: () => { const v = other.value.trim(); if (v) send(v); }}, "Invia"))),
    h("div", {class:"actions"}, h("button", {class:"btn", type:"button", onclick: closeSheet}, "Salta")));
}
async function toggleFav(j){
  const key = keyOf(j), f = favs()[key];
  if (f && f.state !== "discarded"){
    delete S.data.tracker.favs[key]; render();
    if (!await track({key, fav: false}, "Tolto dalle candidature")){ const r = await api("dati"); if (r.ok) S.data = r; render(); }
    return;
  }
  setState(key, j, "interested");
}
async function hideJob(j){ closeSheet(); (S.data.tracker.hidden = S.data.tracker.hidden || {})[keyOf(j)] = "1"; render(); await track({key: keyOf(j), hide: true}, "Annuncio nascosto"); }

/* ---------- candidature: bacheca a colonne sul computer, elenco con filtro sul telefono ---------- */
const COLS = ["interested", "applied", "replied", "cv_requested", "interview", "offer", "closed"];
function appCard(key, f){
  const j = f.job || {}, last = (f.log || []).slice(-1)[0];
  const el = h("div", {class:"acard", role:"button", tabindex:"0", draggable:"true", "data-key": key,
      onclick: () => openApp(key), onkeydown: e => { if (e.key === "Enter"){ e.preventDefault(); openApp(key); } },
      ondragstart: e => { e.dataTransfer.setData("text/plain", key); e.dataTransfer.effectAllowed = "move"; el.classList.add("drag"); },
      ondragend: () => el.classList.remove("drag")},
    h("div", {class:"atop"}, h("b", null, j.title_it || j.title || "Annuncio"), j.score != null ? h("span", {class:"mini"}, String(j.score)) : null),
    h("div", {class:"co"}, [j.company, place(j)].filter(Boolean).join(" · ")),
    h("div", {class:"ameta"}, f.kit ? h("span", {class:"tag new"}, "Materiale pronto") : null, last ? h("span", null, "dal " + new Date(last.t).toLocaleDateString("it-IT", {day:"numeric", month:"short"})) : null));
  return el;
}
function openImport(){
  const inp = h("input", {type:"url", inputmode:"url", placeholder:"https://...", "aria-label":"Link dell'annuncio"});
  const msg = h("p", {class:"msg", role:"alert"});
  const go = h("button", {class:"btn solid", type:"button", onclick: async () => {
    const url = inp.value.trim(); if (!url){ msg.textContent = "Incolla il link dell'annuncio."; return; }
    go.disabled = true; go.textContent = "Leggo l'annuncio..."; msg.textContent = "";
    const r = await api("importa", {url});
    go.disabled = false; go.textContent = "Aggiungi";
    if (!r.ok){ msg.textContent = r.error; return; }
    S.data.tracker = r.tracker; closeSheet(); render();
    toast("Aggiunto: dalla prossima ricerca cerco anche annunci come questo");
  }}, "Aggiungi");
  openSheet(h("h2", null, "Un annuncio che ti piace"),
    h("div", null, h("p", {class:"lead"}, "Hai trovato altrove un annuncio che ti interessa? Incolla il link (LinkedIn, sito dell'azienda, qualsiasi portale). Lo metto tra le tue candidature e imparo a trovarne di simili."),
      h("div", {class:"field"}, inp), msg),
    h("div", {class:"actions"}, go));
  setTimeout(() => inp.focus(), 300);
}
function viewApps(){
  const all = Object.entries(favs());
  const addBtn = h("button", {class:"pill", type:"button", onclick: openImport}, "+ Aggiungi un annuncio trovato altrove");
  if (!all.length) return h("div", {class:"center"}, mercatoCard(), says("ada", "Vale", "Qui tieni traccia delle tue candidature. Negli annunci tocca la stella o «Mi interessa»: l'annuncio arriva qui con il suo testo completo, e puoi farti preparare dall'AI tutto il materiale per candidarti."), h("div", {class:"actions"}, addBtn));
  const active = all.filter(([, f]) => f.state !== "discarded");
  const count = s => all.filter(([, f]) => f.state === s).length;
  const head = h("section", {class:"hero"}, h("div", {class:"eyebrow"}, "Le tue candidature, non scadono mai"),
    h("h1", null, h("em", null, String(active.length)), active.length === 1 ? " annuncio in corso" : " annunci in corso"),
    h("div", {class:"stats"}, ["applied", "replied", "interview", "offer"].map(s => h("div", {class:"stat"}, h("b", null, String(count(s))), h("span", null, STATE[s])))),
    h("div", {style:"margin-top:14px"}, addBtn), mercatoCard());
  if (window.matchMedia("(min-width:900px)").matches){
    const board = h("div", {class:"board"}, COLS.concat(["discarded"]).map(s => {
      const items = all.filter(([, f]) => f.state === s);
      const col = h("div", {class:"col st-" + s, "data-state": s,
          ondragover: e => { e.preventDefault(); col.classList.add("over"); }, ondragleave: () => col.classList.remove("over"),
          ondrop: e => { e.preventDefault(); col.classList.remove("over"); const k = e.dataTransfer.getData("text/plain"); const f = favs()[k]; if (f && f.state !== s){ closeSheet(); setStateQuiet(k, s); } }},
        h("div", {class:"colh"}, h("span", null, STATE[s]), h("span", {class:"count"}, String(items.length))),
        h("div", {class:"colb"}, items.map(([k, f]) => appCard(k, f)), items.length ? null : h("p", {class:"hint", style:"text-align:center;margin:14px 6px"}, "Trascina qui")));
      return col;
    }));
    return h("div", null, head, board);
  }
  const pick = S.appFilter || "active";
  const shown = pick === "active" ? active : all.filter(([, f]) => f.state === pick);
  const chips = h("div", {class:"chips"}, [["active", "In corso", active.length]].concat(STATE_ORDER.map(s => [s, STATE[s], count(s)])).filter(([, , n], i) => i === 0 || n)
    .map(([v, t, n]) => h("button", {class:"chip", type:"button", "aria-pressed": String(pick === v), onclick: () => { S.appFilter = v; render(); }}, `${t} (${n})`)));
  shown.sort((a, b) => STATE_ORDER.indexOf(b[1].state) - STATE_ORDER.indexOf(a[1].state));
  return h("div", null, head, h("div", {class:"filters"}, chips), h("div", {class:"list", style:"margin-top:10px"}, shown.map(([k, f]) => appCard(k, f))));
}
async function setStateQuiet(key, s){
  const f = favs()[key]; f.state = s; (f.log = f.log || []).push({s, t: new Date().toISOString().slice(0, 10)}); render();
  if (!await track({key, state: s}, "Stato: " + STATE[s])){ const r = await api("dati"); if (r.ok) S.data = r; render(); return; }
  if (s === "interview" && !Object.values(colloqui()).some(c => c.key === key && !isPast(c))) openSchedule(null, key);
}

/* ---------- scheda di una candidatura: annuncio completo, stato, note, materiale dell'AI ---------- */
const me = () => store.get("me", {});
const fullName = () => [me().nome, me().cognome].filter(Boolean).join(" ");
const sign = t => String(t || "").replace(/\[NOME\]/g, fullName() || "[Nome e cognome]");
function copyBtn(text, label){
  return h("button", {class:"copy", type:"button", onclick: async e => { try { await navigator.clipboard.writeText(sign(text)); e.target.textContent = "Copiato ✓"; setTimeout(() => { e.target.textContent = label || "Copia"; }, 1600); } catch (er) { toast("Copia non riuscita: seleziona il testo a mano"); } }}, label || "Copia");
}
function block(title, text, extra){ return h("div", {class:"kitb"}, h("div", {class:"kith"}, h("b", null, title), copyBtn(text)), h("p", {class:"kitt"}, sign(text)), extra || null); }
function kitView(key, f){
  const k = f.kit;
  if (!k) return h("div", {class:"kitempty"}, says("ada", "Vale", "Ti preparo lettera di presentazione, email, messaggio per chi recluta e le risposte alle domande che i moduli fanno di solito. Uso solo quello che c'è nel tuo profilo e nel CV: niente di inventato."),
    h("button", {class:"btn solid", type:"button", onclick: e => makeKit(key, e.currentTarget)}, "Prepara il materiale"),
    !store.get("cvtext", "") ? h("p", {class:"hint", style:"margin-top:8px"}, "Consiglio: carica il CV in «Profilo», così il materiale è molto più preciso.") : null);
  return h("div", null,
    k.attenzione && k.attenzione.length ? h("div", {class:"note"}, h("b", null, "Da sapere: "), k.attenzione.join(" · ")) : null,
    k.punti_forti && k.punti_forti.length ? h("div", {class:"kitb"}, h("div", {class:"kith"}, h("b", null, "Cosa giocarti")), h("ul", {class:"reasons"}, k.punti_forti.map(p => h("li", null, p)))) : null,
    block("Lettera di presentazione", k.lettera, h("button", {class:"btn", type:"button", style:"margin-top:8px;width:100%", onclick: () => letterPdf(f).then(file => {
      const a = h("a", {href: URL.createObjectURL(file), download: file.name}); document.body.append(a); a.click(); a.remove(); }).catch(() => toast("PDF non riuscito"))}, "Scarica la lettera in PDF")),
    k.email ? block("Email di candidatura", (k.oggetto_email ? "Oggetto: " + k.oggetto_email + "\n\n" : "") + k.email,
      h("div", {class:"duo", style:"margin-top:8px"}, h("a", {class:"btn", href: "mailto:?subject=" + encodeURIComponent(k.oggetto_email || "") + "&body=" + encodeURIComponent(sign(k.email))}, "Apri nella posta"),
        navigator.canShare ? h("button", {class:"btn", type:"button", onclick: shareCv}, "Condividi il CV") : null)) : null,
    k.messaggio_linkedin ? block("Messaggio a chi recluta", k.messaggio_linkedin) : null,
    k.aspettativa ? block("Retribuzione richiesta", k.aspettativa) : null,
    k.perche_noi ? block("Perché questa azienda", k.perche_noi) : null,
    (k.domande || []).length ? h("div", {class:"kitb"}, h("div", {class:"kith"}, h("b", null, "Risposte per i moduli")),
      k.domande.map(q => h("div", {class:"qa2"}, h("div", {class:"kith"}, h("span", null, q.d), copyBtn(q.r)), h("p", {class:"kitt"}, sign(q.r))))) : null,
    (k.parole_chiave_cv || []).length ? h("div", {class:"kitb"}, h("div", {class:"kith"}, h("b", null, "Parole da far emergere nel CV")), h("div", {class:"tags"}, k.parole_chiave_cv.map(w => h("span", {class:"tag"}, w)))) : null,
    h("p", {class:"hint"}, `Scritto il ${new Date(k.creato).toLocaleDateString("it-IT")}${k.modello ? " con " + String(k.modello).replace(/^models\//, "") : ""}. Rileggi sempre prima di inviare.`),
    h("button", {class:"linkbtn", type:"button", onclick: e => makeKit(key, e.currentTarget)}, "Riscrivi il materiale"));
}
async function makeKit(key, btn){
  const f = favs()[key]; if (!f) return;
  if (btn){ btn.disabled = true; btn.textContent = "Vale sta scrivendo... (20-40 secondi)"; }
  const r = await api("kit", {key, job: f.job, cv: cvForAi()});
  if (!r.ok){ toast(r.error); if (btn){ btn.disabled = false; btn.textContent = "Riprova"; } return; }
  S.data.tracker = r.tracker; render(); openApp(key);
}
async function shareCv(){
  const file = await idb.get("cvfile");
  if (!file){ toast("Carica prima il CV in «Profilo»"); return; }
  try { await navigator.share({files: [file], title: file.name}); } catch (e) {}
}
function openApp(key, autoKit){
  const f = favs()[key]; if (!f) return;
  const j = f.job || {};
  let noteT;
  const isUrl = /^https?:\/\//.test(j.url || "");
  if (f.jd === undefined && f.has_jd && !f._jdLoading){  // testo completo caricato solo adesso, quando serve
    f._jdLoading = true;
    api("testo", {key}).then(r => { if (r.ok){ f.jd = r.jd; if (sheetEl && sheetEl.dataset.k === key) openApp(key); } });
  }
  const jd = f.jd || j.excerpt || (f._jdLoading ? "Carico il testo dell'annuncio..." : "");
  const jdBox = h("div", {class:"jd" + (jd.length > 900 ? " fold" : "")}, jd ? jd : "Testo completo non disponibile: apri l'annuncio originale.");
  const body = [
    h("div", {class:"sec"}, h("h4", null, "Stato"), statusChips(key, j, f.state)),
    (f.log || []).length > 1 ? h("ol", {class:"timeline"}, f.log.slice().reverse().map(l => h("li", null, h("b", null, STATE[l.s] || l.s), " · " + new Date(l.t).toLocaleDateString("it-IT", {day:"numeric", month:"long"})))) : null,
    colloquiOf(key),
    h("div", {class:"sec"}, h("h4", null, "Candidati"), kitView(key, f),
      h("div", {class:"applyhow"}, h("b", null, "Per inviare: "), "apri l'annuncio e vai al modulo. ",
        h("span", {class:"desk"}, "Sul computer premi il segnalibro «Compila con Job Radar»: compila lui i campi con i tuoi dati e il CV, tu controlli e premi Invia."),
        h("span", {class:"mob"}, "Dal telefono copia i testi qui sopra con «Copia» e incollali nel modulo."))),
    h("div", {class:"sec"}, h("h4", null, "Note"), h("textarea", {class:"note2", placeholder:"A chi hai scritto, quando, cosa ti hanno risposto", "aria-label":"Note",
      oninput: e => { clearTimeout(noteT); const v = e.target.value; noteT = setTimeout(() => { f.note = v; track({key, note: v}, "Nota salvata"); }, 900); }}, f.note || "")),
    h("div", {class:"sec"}, h("h4", null, "L'annuncio"), jdBox, jd.length > 900 ? h("button", {class:"linkbtn", type:"button", onclick: e => { jdBox.classList.toggle("fold"); e.target.textContent = jdBox.classList.contains("fold") ? "Leggi tutto" : "Riduci"; }}, "Leggi tutto") : null),
    h("button", {class:"linkbtn", type:"button", onclick: async () => { closeSheet(); delete S.data.tracker.favs[key]; render(); await track({key, fav: false}, "Tolto dalle candidature"); }}, "Togli dalle candidature")];
  const open = h("a", {class:"btn solid", href: isUrl ? j.url : "#", target:"_blank", rel:"noopener noreferrer"}, "Vai all'annuncio");
  const sent = f.state === "interested" ? h("button", {class:"btn", type:"button", onclick: () => setState(key, j, "applied")}, "Ho inviato") : null;
  openSheet(h("div", null, h("h2", null, j.title_it || j.title), h("div", {class:"co"}, [j.company, place(j)].filter(Boolean).join(" · "))), body, [sent, open].filter(Boolean), key);
  // il materiale si scrive da solo la prima volta che si apre la candidatura: alla persona resta solo da rivedere
  if (!f.kit && !f._kitAsked){ f._kitAsked = true; const b = sheetEl && sheetEl.querySelector(".kitempty .btn"); if (b) makeKit(key, b); }
}

function colloquiOf(key){
  const mine = Object.entries(colloqui()).filter(([, c]) => c.key === key);
  const f = favs()[key];
  if (!mine.length && !(f && ["interview", "replied", "cv_requested", "offer"].includes(f.state))) return null;
  return h("div", {class:"sec"}, h("h4", null, "Colloqui"),
    mine.map(([id, c]) => h("button", {class:"ccard", type:"button", onclick: () => { closeSheet(); openColloquio(id); }},
      h("div", {class:"cwhen"}, whenLabel(c)), h("b", null, ROUND[c.round] || "Colloquio"), h("div", {class:"co"}, c.plan ? "Preparazione pronta: apri la pagina" : "Apri la preparazione"))),
    h("button", {class:"btn" + (mine.length ? "" : " solid"), type:"button", style:"width:100%;margin-top:8px", onclick: () => openSchedule(null, key, mine.length ? "manager" : "hr")},
      mine.length ? "Programma un altro colloquio" : "Hai un colloquio? Preparati con Tina e Vale"));
}

/* lettera di presentazione in PDF (per i moduli che la chiedono come allegato) */
async function letterPdf(f){
  if (!window.jspdf) await new Promise((ok, ko) => { const s = document.createElement("script"); s.src = "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"; s.onload = ok; s.onerror = ko; document.head.appendChild(s); });
  const plain = t => String(t || "").replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/[–—]/g, "-").replace(/…/g, "...").replace(/[‑ ]/g, " ");
  const doc = new window.jspdf.jsPDF({unit: "mm", format: "a4"}), m = me();
  const head = [fullName(), [m.citta, m.email, m.telefono].filter(Boolean).join("  |  "), m.linkedin || ""].filter(Boolean);
  doc.setFont("helvetica", "bold"); doc.setFontSize(15); doc.text(plain(head[0] || ""), 22, 26);
  doc.setFont("helvetica", "normal"); doc.setFontSize(9.5); doc.setTextColor(90); head.slice(1).forEach((l, i) => doc.text(plain(l), 22, 32 + i * 5));
  doc.setTextColor(20); doc.setFontSize(11);
  let y = 32 + head.length * 5 + 8;
  doc.text(new Date().toLocaleDateString(f.kit.lingua === "it" ? "it-IT" : "en-GB", {day:"numeric", month:"long", year:"numeric"}), 22, y); y += 10;
  for (const par of plain(sign(f.kit.lettera)).split(/\n+/)){
    for (const line of doc.splitTextToSize(par, 166)){ if (y > 280){ doc.addPage(); y = 22; } doc.text(line, 22, y); y += 5.6; }
    y += 3;
  }
  const name = ("Lettera_" + (f.job.company || "candidatura") + "_" + (m.cognome || "")).replace(/[^\w-]+/g, "_").replace(/_+$/, "") + ".pdf";
  return new File([doc.output("blob")], name, {type: "application/pdf"});
}

/* ---------- CV e file salvati solo su questo dispositivo ---------- */
const idb = {
  db: null,
  open(){ return this.db || (this.db = new Promise((ok, ko) => { const r = indexedDB.open("jobradar", 1); r.onupgradeneeded = () => r.result.createObjectStore("f"); r.onsuccess = () => ok(r.result); r.onerror = () => ko(r.error); })); },
  async get(k){ try { const db = await this.open(); return await new Promise(ok => { const q = db.transaction("f").objectStore("f").get(k); q.onsuccess = () => ok(q.result || null); q.onerror = () => ok(null); }); } catch (e) { return null; } },
  async set(k, v){ const db = await this.open(); return new Promise((ok, ko) => { const tx = db.transaction("f", "readwrite"); tx.objectStore("f").put(v, k); tx.oncomplete = ok; tx.onerror = () => ko(tx.error); }); },
};
async function pdfText(file){
  if (!window.pdfjsLib){
    await new Promise((ok, ko) => { const s = document.createElement("script"); s.src = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"; s.onload = ok; s.onerror = ko; document.head.appendChild(s); });
    window.pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
  }
  const pdf = await window.pdfjsLib.getDocument({data: await file.arrayBuffer()}).promise;
  let out = "";
  for (let i = 1; i <= Math.min(pdf.numPages, 6); i++){
    const c = await (await pdf.getPage(i)).getTextContent();
    let lastY = null;
    for (const it of c.items){ if (lastY !== null && Math.abs(it.transform[5] - lastY) > 4) out += "\n"; out += it.str; lastY = it.transform[5]; }
    out += "\n";
  }
  return out.replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
}

/* ---------- profilo: la ricerca, i dati per candidarsi (solo su questo dispositivo), il segnalibro che compila i moduli ---------- */
const ME_FIELDS = [["nome","Nome"],["cognome","Cognome"],["email","Email","email"],["telefono","Telefono","tel"],["citta","Città in cui vivi"],
  ["linkedin","Profilo LinkedIn (link)","url"],["sito","Sito o portfolio (link)","url"]];
function cvForAi(){
  const m = me(), extra = [["Città in cui vive", m.citta]].filter(x => x[1]), li = store.get("litext", "");
  return store.get("cvtext", "") + (li ? "\n\nPROFILO LINKEDIN\n" + li.slice(0, 3000) : "") + (extra.length ? "\n\nINFORMAZIONI PER I MODULI\n" + extra.map(([k, v]) => k + ": " + v).join("\n") : "");
}
function bookmarklet(){
  const src = BOOKMARKLET.toString().replace("__ORIGIN__", location.origin);
  return "javascript:(" + encodeURIComponent(src) + ")()";
}
function viewMe(){
  const d = S.data, a = (d.profile && d.profile.answers) || {};
  const on = (d.profile.clusters || []).filter(c => c.on).map(c => c.name);
  const light = document.documentElement.dataset.theme === "light";
  const m = me();
  const msg = h("p", {class:"hint", role:"status"});
  const form = h("div", {class:"mefields"}, ME_FIELDS.map(([k, label, type]) => h("label", {class:"field"}, h("span", {class:"ql"}, label),
    h("input", {type: type || "text", value: m[k] || "", autocomplete: {nome:"given-name", cognome:"family-name", email:"email", telefono:"tel", citta:"address-level2", linkedin:"url", sito:"url"}[k] || "off",
      oninput: e => { const x = me(); x[k] = e.target.value.trim(); store.set("me", x); msg.textContent = "Salvato su questo dispositivo"; }}))));
  const cvName = store.get("cvname", "");
  const cvInfo = h("p", {class:"hint"}, cvName ? `CV caricato: ${cvName} (${store.get("cvtext", "").length} caratteri letti)` : "Nessun CV caricato.");
  const cvInput = h("input", {type:"file", accept:"application/pdf", class:"visually-hidden", id:"cvfile", onchange: async e => {
    const file = e.target.files[0]; if (!file) return;
    cvInfo.textContent = "Leggo il CV...";
    try {
      const text = await pdfText(file);
      if (text.length < 200) throw new Error("vuoto");
      await idb.set("cvfile", file); store.set("cvtext", text.slice(0, 20000)); store.set("cvname", file.name);
      cvInfo.textContent = `CV caricato: ${file.name} (${text.length} caratteri letti)`;
    } catch (er) { cvInfo.textContent = "Non riesco a leggere questo PDF: serve un PDF con testo selezionabile, non una foto o una scansione."; }
  }});
  const liName = store.get("liname", "");
  const liInfo = h("p", {class:"hint"}, liName ? `Profilo LinkedIn caricato: ${liName} (${store.get("litext", "").length} caratteri letti)` : "Facoltativo. Su LinkedIn apri il tuo profilo, premi «Altro» (o «Risorse») e poi «Salva in PDF». Serve a Tina e Vale per prepararti ai colloqui con tutto quello che hai fatto.");
  const liInput = h("input", {type:"file", accept:"application/pdf", class:"visually-hidden", id:"lifile", onchange: async e => {
    const file = e.target.files[0]; if (!file) return;
    liInfo.textContent = "Leggo il profilo...";
    try {
      const text = await pdfText(file);
      if (text.length < 200) throw new Error("vuoto");
      store.set("litext", text.slice(0, 12000)); store.set("liname", file.name);
      liInfo.textContent = `Profilo LinkedIn caricato: ${file.name} (${text.length} caratteri letti)`;
    } catch (er) { liInfo.textContent = "Non riesco a leggere questo PDF: scaricalo di nuovo da LinkedIn con «Salva in PDF»."; }
  }});
  const cityInp = h("input", {type:"text", placeholder:"Aggiungi una città (es. Torino)", "aria-label":"Aggiungi una città", maxlength:"60"});
  const cityAdd = h("button", {class:"btn", type:"button", onclick: async () => { const v = cityInp.value.trim(); if (v && await addPlace(v, cityAdd)) cityInp.value = ""; }}, "Aggiungi");
  cityInp.addEventListener("keydown", e => { if (e.key === "Enter"){ e.preventDefault(); cityAdd.click(); } });
  const cities = h("div", {class:"sec"}, h("h4", null, "Le tue città"),
    h("p", {class:"hint"}, "Qui cerco tutti gli annunci adatti a te entro circa 40 km, pubblicati nell'ultima settimana, su LinkedIn e sui portali italiani ed europei. Fino a tre città."),
    myPlaces().length ? h("div", {class:"wrap"}, myPlaces().map(p => h("button", {class:"chip", type:"button", "aria-pressed":"true", title:"Togli",
      onclick: e => saveCities(myPlaces().filter(x => x !== p).map(x => x.typed || x.name), e.target, false)}, "📍 " + (p.typed || p.name) + "  ✕"))) : h("p", {class:"hint"}, "Nessuna città: cerco solo nei paesi scelti, annunci delle ultime 24 ore."),
    myPlaces().length < 3 ? h("div", {class:"cityrow"}, cityInp, cityAdd) : null);
  const lr = Object.assign({titles: [], companies: [], likes: [], dislikes: [], changes: [], off: []}, (d.profile && d.profile.learned) || {});
  const offChip = (t, done) => h("button", {class:"chip", type:"button", "aria-pressed":"true", title:"Togli",
    onclick: async e => { e.target.disabled = true; const r = await api("impara", {off: t}); if (!r.ok) return toast(r.error); d.profile.learned = r.learned; toast(done); render(); }}, t + "  ✕");
  const lrList = (label, items) => items.length ? h("div", {class:"kv", style:"margin:8px 0"}, h("div", null, h("span", null, label), items.join(". "))) : null;
  const lrAny = lr.titles.length || lr.companies.length || lr.likes.length;
  const learned = h("div", {class:"sec"}, h("h4", null, "Imparato dalle tue scelte"),
    h("p", {class:"hint"}, lrAny ? (lr.summary ? lr.summary + " " : "") + "Gli annunci che salvi, le candidature, quelli che aggiungi tu e quelli che scarti contano più dell'intervista: se nel tempo cambi idea, cambio anch'io." :
      "Quando salvi annunci, ti candidi, ne aggiungi di trovati altrove o ne scarti, imparo cosa ti piace e adatto la ricerca. Le tue scelte contano più dell'intervista."),
    lrList("Cosa è cambiato rispetto all'intervista", lr.changes),
    lrList("Cosa scegli", lr.likes),
    lrList("Cosa scarti", lr.dislikes),
    lr.titles.length ? [h("p", {class:"hint"}, "Ruoli che cerco in più. Tocca ✕ per toglierne uno."),
      h("div", {class:"wrap"}, lr.titles.map(t => offChip(t, "Tolto: non lo cerco più")))] : null,
    lr.companies.length ? [h("p", {class:"hint", style:"margin-top:10px"}, "Aziende che seguo per te: nelle tue città leggo tutti i loro annunci dell'ultimo mese, anche con titoli diversi dai tuoi ruoli."),
      h("div", {class:"wrap"}, lr.companies.map(t => offChip(t, "Tolta: non la seguo più")))] : null);
  const nt = (d.profile && d.profile.notify) || {};
  const ntBox = h("div", {class:"sec"}, h("h4", null, "Avvisi sul telefono"),
    nt.topic ? [
      h("p", {class:"hint"}, `Quando trovo annunci nuovi con voto da ${nt.min || 70} in su ti mando una notifica, prima quelli della tua città. Gratis, senza account.`),
      h("ol", {class:"hint", style:"padding-left:18px;margin:6px 0 10px"},
        h("li", null, "Installa l'app gratuita «ntfy» (Play Store o App Store)."),
        h("li", null, "Tocca «Iscriviti» qui sotto: si apre ntfy sul tuo canale personale. Se non si apre, in ntfy premi + e scrivi il nome del canale: ", h("b", null, nt.topic)),
        h("li", null, "Premi «Mandami una prova» per controllare che arrivi.")),
      h("div", {class:"actions", style:"flex-wrap:wrap"},
        h("a", {class:"btn solid", href: "ntfy://ntfy.sh/" + nt.topic, onclick: () => setTimeout(() => { if (!document.hidden) location.href = "https://ntfy.sh/" + nt.topic; }, 1200)}, "Iscriviti"),
        h("button", {class:"btn", type:"button", onclick: async e => { e.target.disabled = true; const r = await api("avvisi", {prova: true}); e.target.disabled = false; toast(r.ok ? "Avviso di prova inviato" : r.error); }}, "Mandami una prova")),
      h("div", {class:"wrap", style:"margin-top:10px"}, [60, 70, 80].map(m => h("button", {class:"chip", type:"button", "aria-pressed": String((nt.min || 70) === m),
        onclick: async () => { const r = await api("avvisi", {min: m}); if (!r.ok) return toast(r.error); d.profile.notify = r.notify; render(); }}, `Voto da ${m}`))),
      h("button", {class:"linkbtn", type:"button", onclick: async () => { const r = await api("avvisi", {on: false}); if (!r.ok) return toast(r.error); d.profile.notify = {}; toast("Avvisi spenti"); render(); }}, "Spegni gli avvisi")
    ] : [
      h("p", {class:"hint"}, "Ricevi una notifica quando escono annunci nuovi adatti a te, prima quelli della tua città. Gratis, con l'app ntfy, senza account."),
      h("button", {class:"btn", type:"button", onclick: async e => { e.target.disabled = true; const r = await api("avvisi", {on: true}); if (!r.ok){ e.target.disabled = false; return toast(r.error); } d.profile.notify = r.notify; render(); }}, "Attiva gli avvisi")
    ]);
  const left = h("section", {class:"panel"},
    h("h2", null, "La mia ricerca"),
    h("p", {class:"hint"}, "La ricerca parte da sola tre volte al giorno (mattina, mezzogiorno e pomeriggio). Puoi cambiare quello che cerchi quando vuoi."),
    h("div", {class:"kv"},
      h("div", null, h("span", null, "Cosa cerchi"), a.desired || ""),
      h("div", null, h("span", null, "Ruoli che sto cercando per te"), on.join(", ")),
      a.prefer ? h("div", null, h("span", null, "Settori che preferisci"), a.prefer) : null,
      a.avoid ? h("div", null, h("span", null, "Settori esclusi"), a.avoid) : null,
      d.run ? h("div", null, h("span", null, "Ultima ricerca"), `${fmtWhen(d.run.at)}: ${d.jobs.length} annunci in ${d.run.minutes} minuti`) : null),
    cities, learned, ntBox,
    h("div", {class:"actions", style:"flex-direction:column"},
      h("button", {class:"btn solid", type:"button", onclick: () => viewInterview(a)}, "Cambia la mia ricerca"),
      h("button", {class:"btn", type:"button", onclick: () => { const t = light ? "dark" : "light"; document.documentElement.dataset.theme = t; store.set("theme", t); render(); }}, light ? "Passa al tema scuro" : "Passa al tema chiaro"),
      h("button", {class:"btn", type:"button", onclick: () => logout(false)}, "Esci")),
    h("p", {class:"hint", style:"margin-top:16px"}, "Per avere Job Radar come app sul telefono: dal menu del browser scegli «Aggiungi a schermata Home»."),
    h("div", {class:"sec"}, h("h4", null, "Su un altro dispositivo"), linkBox()));
  const right = h("section", {class:"panel"},
    h("h2", null, "Per candidarti"),
    h("p", {class:"hint"}, "L'AI li usa per scrivere lettere e risposte, il segnalibro per compilare i moduli. CV e contatti restano solo su questo dispositivo: all'AI arriva il testo del CV, mai email, telefono e link."),
    h("div", {class:"sec"}, h("h4", null, "Come vuoi candidarti"), applyChips(Object.assign({}, APPLY_DEFAULT, a.apply || {}), async (k, v) => {
      const r = await api("preferenze", {[k]: v});
      if (!r.ok) return toast(r.error);
      a.apply = r.apply; toast("Salvato: vale per il materiale che scrive l'AI");
    })),
    h("div", {class:"sec"}, h("h4", null, "Il tuo CV (PDF)"), cvInfo, h("label", {class:"btn", for:"cvfile", style:"max-width:280px"}, cvName ? "Sostituisci il CV" : "Carica il CV"), cvInput),
    h("div", {class:"sec"}, h("h4", null, "Il tuo profilo LinkedIn (PDF)"), liInfo, h("label", {class:"btn", for:"lifile", style:"max-width:280px"}, liName ? "Sostituisci il profilo" : "Carica il profilo LinkedIn"), liInput),
    h("div", {class:"sec"}, h("h4", null, "I tuoi dati"), form, msg),
    h("div", {class:"sec desk"}, h("h4", null, "Compilazione automatica dei moduli"),
      h("p", {class:"hint"}, "Trascina questo pulsante nella barra dei preferiti del browser (se non la vedi: Ctrl+Maiusc+B). Quando sei sul modulo di candidatura di un annuncio, cliccalo: Job Radar riempie i campi con i tuoi dati, il CV e risposte scritte su quell'annuncio. Non invia nulla: controlli tu e premi Invia."),
      h("a", {class:"bmk", href: bookmarklet(), onclick: e => { e.preventDefault(); toast("Trascinalo nella barra dei preferiti: non va cliccato qui"); }}, "⚡ Compila con Job Radar"),
      h("p", {class:"hint"}, "Se il modulo è dentro un riquadro della pagina e non si riempie, apri il modulo in una scheda sua e riprova.")));
  return h("div", {class:"megrid"}, left, right);
}
/* codice del segnalibro: gira sulla pagina del modulo (sito dell'azienda), apre la finestrella di Job Radar e riempie i campi */
function BOOKMARKLET(){
  const O = "__ORIGIN__";
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden"; };
  const clean = t => String(t || "").replace(/\s+/g, " ").replace(/\*/g, "").trim().slice(0, 200);
  const lab = e => {
    let t = "";
    if (e.id){ const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l) t = l.innerText; }
    if (!t){ const l = e.closest("label"); if (l) t = l.innerText; }
    if (!t) t = e.getAttribute("aria-label") || "";
    if (!t && e.getAttribute("aria-labelledby")) t = e.getAttribute("aria-labelledby").split(" ").map(i => (document.getElementById(i) || {}).innerText || "").join(" ");
    let p = e.parentElement;
    for (let i = 0; i < 4 && p && !t; i++){ const c = p.querySelector("label,legend,[class*=label],[class*=Label]"); if (c && c.innerText && c.innerText.length < 300) t = c.innerText; p = p.parentElement; }
    return clean(t || e.placeholder || e.name || "");
  };
  // se è aperta una finestra di candidatura (LinkedIn "Candidatura semplice" e simili) si guardano solo i suoi campi
  // (i nomi possono essere offuscati: si cerca il riquadro "fisso" in primo piano che sta al centro dello schermo)
  const fixedBox = e => { for (let p = e.parentElement; p && p !== document.body; p = p.parentElement){ if (getComputedStyle(p).position === "fixed") return p; } return null; };
  const cx = innerWidth / 2, cy = innerHeight / 2;
  const boxes = new Map();
  document.querySelectorAll("input,textarea,select").forEach(e => { if (!vis(e)) return; const b = fixedBox(e); if (!b) return;
    const r = b.getBoundingClientRect(); if (r.left < cx && r.right > cx && r.top < cy && r.bottom > cy) boxes.set(b, (boxes.get(b) || 0) + 1); });
  const modals = [...document.querySelectorAll('[aria-modal="true"],[role=dialog]')].filter(m => vis(m) && m.querySelector("input,textarea,select"));
  const root = [...boxes.entries()].sort((a, b) => b[1] - a[1]).map(x => x[0])[0] || modals[modals.length - 1] || document;
  // un CV già scelto nel modulo (LinkedIn propone quelli caricati in passato) non si sostituisce
  const cvChosen = [...root.querySelectorAll("input[type=radio]:checked,input[type=checkbox]:checked")].some(e => /\.(pdf|docx?)\b/i.test(lab(e) + " " + ((e.closest("li,div") || {}).innerText || "")));
  document.querySelectorAll("[data-jr]").forEach(e => e.removeAttribute("data-jr"));  // modulo a più pagine: si riparte da capo
  const els = [...root.querySelectorAll("input,textarea,select")].filter(e => !["hidden","submit","button","image","reset","password","search"].includes(e.type) && !e.disabled
    && (e.type === "file" || (vis(e) && e.getAttribute("aria-hidden") !== "true" && e.tabIndex !== -1)));
  const isCombo = e => e.getAttribute("role") === "combobox" || e.getAttribute("aria-autocomplete") === "list";
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const listOf = e => document.getElementById(e.getAttribute("aria-controls") || e.getAttribute("aria-owns") || "") || [...document.querySelectorAll("[role=listbox]")].filter(vis).pop();
  const key = (e, k) => ["keydown", "keyup"].forEach(t => e.dispatchEvent(new KeyboardEvent(t, {key: k, code: k, bubbles: true})));
  const fields = [], groups = {};
  const w = window.open(O + "/compila.html", "jrfill", "width=480,height=680");  // subito, finché vale il clic
  window.__jrOpen = w;
  const scan = (async () => {
    for (const [i, e] of els.entries()){
      e.dataset.jr = i;
      if (e.type === "radio" || e.type === "checkbox"){ const g = e.name || "x" + i; (groups[g] = groups[g] || []).push(e); continue; }
      let options = e.tagName === "SELECT" ? [...e.options].map(o => o.text.trim()).filter(Boolean).slice(0, 40) : null;
      if (isCombo(e) && !e.value){
        e.focus(); key(e, "ArrowDown"); await sleep(250);
        const lb = listOf(e);
        options = lb ? [...lb.querySelectorAll("[role=option]")].map(o => clean(o.innerText)).filter(Boolean).slice(0, 40) : null;
        key(e, "Escape"); e.blur(); await sleep(60);
      }
      fields.push({id: String(i), label: lab(e), type: e.tagName === "SELECT" || isCombo(e) ? "select" : (e.type || "text"), long: e.tagName === "TEXTAREA",
        options, ac: e.autocomplete || "", name: e.name || "", accept: e.accept || ""});
    }
    Object.entries(groups).forEach(([g, list]) => { const fs = list[0].closest("fieldset"); const lg = fs && fs.querySelector("legend");
      fields.push({id: "g:" + g, label: clean(lg ? lg.innerText : (list[0].closest("[role=group],[role=radiogroup]") || {}).innerText || lab(list[0])), type: list[0].type, options: list.map(lab)}); });
  })();
  async function pick(e, v){  // menu "cerca e scegli": si scrive, si aspetta l'elenco e si clicca l'opzione giusta
    e.focus(); setv(e, v); key(e, "ArrowDown"); await sleep(400);
    const lb = listOf(e), low = v.toLowerCase();
    const opts = lb ? [...lb.querySelectorAll("[role=option]")] : [];
    const o = opts.find(x => clean(x.innerText).toLowerCase() === low) || opts.find(x => clean(x.innerText).toLowerCase().startsWith(low)) || (opts.length === 1 ? opts[0] : null);
    if (o){ o.click(); await sleep(120); return true; }
    setv(e, ""); key(e, "Escape"); e.blur(); return false;
  }
  const setv = (e, v) => { const d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e), "value"); if (d && d.set) d.set.call(e, v); else e.value = v;
    ["input","change","blur"].forEach(n => e.dispatchEvent(new Event(n, {bubbles: true}))); };
  const mark = e => { e.style.outline = "2px solid #36F2A0"; e.style.outlineOffset = "2px"; };
  async function fill(m){
    let n = 0;
    for (const [id, raw] of Object.entries(m.values || {})){
      const v = String(raw == null ? "" : raw); if (!v) continue;
      if (id.startsWith("g:")){
        const list = groups[id.slice(2)] || [], low = v.toLowerCase();
        const hit = list.find(e => lab(e).toLowerCase() === low) || list.find(e => lab(e).toLowerCase().includes(low));
        if (hit && !hit.checked){ hit.click(); mark(hit); n++; }
        continue;
      }
      const e = document.querySelector('[data-jr="' + id + '"]'); if (!e) continue;
      if (e.type === "file"){
        if (m.file && !cvChosen){ try { const dt = new DataTransfer(); dt.items.add(m.file); e.files = dt.files; ["input","change"].forEach(x => e.dispatchEvent(new Event(x, {bubbles: true}))); n++; } catch (er) {} }
        continue;
      }
      if (isCombo(e)){ if (!e.value && await pick(e, v)){ mark(e); n++; } continue; }
      if (e.tagName === "SELECT"){
        const low = v.toLowerCase(), o = [...e.options].find(o => o.text.trim().toLowerCase() === low) || [...e.options].find(o => o.text.toLowerCase().includes(low));
        if (o){ e.value = o.value; e.dispatchEvent(new Event("change", {bubbles: true})); mark(e); n++; }
        continue;
      }
      if (e.value && e.value.trim()) continue;  // ciò che è già scritto non si tocca
      setv(e, v); mark(e); n++;
    }
    for (const id of m.letterIds || []){  // campi "allega la lettera di presentazione"
      const e = document.querySelector('[data-jr="' + id + '"]');
      if (e && m.letterFile){ try { const dt = new DataTransfer(); dt.items.add(m.letterFile); e.files = dt.files; ["input","change"].forEach(x => e.dispatchEvent(new Event(x, {bubbles: true}))); n++; } catch (er) {} }
    }
    const b = document.createElement("div");
    b.textContent = "Job Radar ha compilato " + n + " campi (bordo verde). Controlla tutto, completa quello che manca e premi tu Invia.";
    b.style.cssText = "position:fixed;z-index:2147483647;left:50%;top:16px;transform:translateX(-50%);max-width:90vw;background:#0A0F14;color:#E6EDF3;border:2px solid #36F2A0;padding:12px 18px;border-radius:12px;font:600 15px system-ui;box-shadow:0 10px 30px rgba(0,0,0,.45)";
    document.body.appendChild(b); setTimeout(() => b.remove(), 12000);
  }
  if (window.__jrH) window.removeEventListener("message", window.__jrH);
  window.__jrH = ev => {
    if (ev.origin !== O) return;
    const m = ev.data || {};
    if (m.t === "ready") scan.then(() => w.postMessage({t: "req", url: location.href, title: document.title, page: document.body.innerText.slice(0, 9000), fields}, O));
    if (m.t === "fill") fill(m);
    if (m.t === "closed") window.__jrOpen = null;
  };
  window.addEventListener("message", window.__jrH);
}

/* ---------- intervista ---------- */
const WZ_LANGS = [["it","Italiano"],["en","Inglese"],["es","Spagnolo"],["fr","Francese"],["de","Tedesco"],["pt","Portoghese"],["nl","Olandese"]];
const WZ_YEARS = [[0,"Meno di 1 anno"],[2,"1-3 anni"],[5,"4-6 anni"],[8,"7-10 anni"],[12,"Più di 10"]];
const WZ_LEVEL = [["","Coerente con la mia esperienza"],["stage","Stage o primo impiego"],["junior","Junior"],["mid","Mid"],["senior","Senior"]];
const APPLY_Q = [
  ["ral", "Che stipendio chiedi?", "Lordo annuo. Se non lo sai, lo propone l'AI per ogni annuncio, in base a ruolo, paese ed esperienza.",
    [["auto","Decidi tu per ogni annuncio"],["25-30","25-30k"],["30-35","30-35k"],["35-45","35-45k"],["45-60","45-60k"],["60+","Oltre 60k"]]],
  ["modalita", "Come preferisci lavorare?", null, [["any","Indifferente"],["remote","Da remoto"],["hybrid","Ibrido"],["onsite","In sede"]]],
  ["trasferimento", "Ti trasferiresti per un lavoro?", null, [["si","Sì, anche all'estero"],["paese","Solo nel mio paese"],["no","No"]]],
  ["preavviso", "Quando potresti iniziare?", null, [["subito","Subito"],["2w","Tra 2 settimane"],["1m","Tra 1 mese"],["2-3m","Tra 2-3 mesi"]]],
  ["permesso", "Permesso di lavoro", "Lo chiedono quasi tutti i moduli.", [["ue","Cittadinanza UE"],["permesso","Ho un permesso di lavoro"],["sponsor","Mi serve lo sponsor per il visto"]]],
];
const APPLY_DEFAULT = {ral:"auto", modalita:"any", trasferimento:"paese", preavviso:"1m", permesso:"ue"};
function applyChips(ap, onPick){
  return APPLY_Q.map(([k, label, hint, opts]) => {
    const box = h("div", {class:"wrap"});
    const draw = () => box.replaceChildren(...opts.map(([v, t]) => h("button", {class:"chip", type:"button", "aria-pressed": String(ap[k] === v),
      onclick: () => { ap[k] = v; draw(); if (onPick) onPick(k, v); }}, t)));
    draw();
    return h("div", {class:"field"}, h("div", {class:"ql"}, label), hint ? h("p", {class:"hint"}, hint) : null, box);
  });
}
const WZ_COUNTRIES = ["Italia","Spagna","Francia","Germania","Regno Unito","Irlanda","Paesi Bassi","Belgio","Svizzera","Portogallo","Austria","Lussemburgo","Svezia","Danimarca","Norvegia","Finlandia","Polonia","Repubblica Ceca","Ungheria","Romania","Grecia","Estonia","Lettonia","Lituania","Croazia","Slovenia","Slovacchia","Bulgaria","Malta","Cipro"];
function plain(content, back){
  stopPoll(); closeSheet();
  $app.replaceChildren(h("header", {class:"top"}, h("div", {class:"brand", html: ICON.logo + "<span>Job Radar</span>"}),
    back ? h("button", {class:"pill", type:"button", onclick: back}, "Indietro") : h("button", {class:"iconbtn", type:"button", "aria-label":"Esci", html: ICON.out, onclick: () => logout(false)})),
    h("main", null, h("div", {class:"center", style:"padding-top:8px"}, content)));
  window.scrollTo(0, 0);
}
function viewInterview(prev){
  const first = !(S.data && S.data.profile);
  const a = Object.assign({desired:"", years:2, level:"", languages:["it","en"], countries:[], cities:[], education:"", strengths:"", avoid:"", current:"", prefer:""}, prev || {});
  a.apply = Object.assign({}, APPLY_DEFAULT, a.apply || {});
  const field = (label, hint, node) => h("div", {class:"field"}, h("div", {class:"ql"}, label), hint ? h("p", {class:"hint"}, hint) : null, node);
  const chips = (opts, key, multi) => { const box = h("div", {class:"wrap"}); const draw = () => box.replaceChildren(...opts.map(([v, t]) => {
      const on = multi ? a[key].includes(v) : a[key] === v;
      return h("button", {class:"chip", type:"button", "aria-pressed": String(on), onclick: () => { if (multi) a[key] = on ? a[key].filter(x => x !== v) : a[key].concat(v); else a[key] = v; draw(); }}, t); })); draw(); return box; };
  const text = (key, ph) => h("input", {type:"text", value: a[key], placeholder: ph, oninput: e => { a[key] = e.target.value; }});
  const ta = h("textarea", {placeholder:"Esempio: vorrei lavorare come business developer in un'azienda di software. Mi piace parlare con i clienti, capire cosa serve e costruire nuove collaborazioni...", "aria-label":"Che lavoro vorresti fare"}, a.desired);
  const msg = h("p", {class:"msg", role:"alert"}), go = h("button", {class:"btn solid", type:"button"}, "Proponimi i ruoli da cercare");
  go.addEventListener("click", async () => {
    a.desired = ta.value.trim();
    if (a.desired.length < 8){ msg.textContent = "Scrivi almeno una frase sul lavoro che cerchi."; ta.focus(); return; }
    if (!a.languages.length){ msg.textContent = "Scegli almeno una lingua."; return; }
    go.disabled = true; go.textContent = "Vale sta ragionando sul tuo profilo..."; msg.textContent = "";
    const r = await api("intervista", {answers: a});
    go.disabled = false; go.textContent = "Proponimi i ruoli da cercare";
    if (!r.ok){ msg.textContent = r.error; return; }
    viewReview(r.profile);
  });
  plain([
    h("h1", null, first ? "Benvenuta, benvenuto" : "La mia ricerca"),
    h("p", {class:"lead"}, ""),
    says("ada", "Vale", "Ciao, sono Vale. Ti faccio poche domande per capire che lavoro cerchi e cosa sai fare. Poi ti propongo i ruoli da cercare, anche quelli a cui non avevi pensato, e tu scegli quali tenere."),
    h("div", {class:"field"}, h("div", {class:"ql"}, "1. Che lavoro vorresti fare?"), h("p", {class:"hint"}, "Scrivilo con parole tue: ruolo, cosa vorresti fare ogni giorno, tipo di azienda. Anche se è diverso da quello che fai ora."), ta),
    field("2. Quanta esperienza di lavoro hai?", null, chips(WZ_YEARS, "years")),
    field("3. Che livello cerchi?", null, chips(WZ_LEVEL, "level")),
    field("4. In che lingue puoi lavorare?", "Gli annunci che richiedono una lingua che non parli vengono scartati.", chips(WZ_LANGS, "languages", true)),
    field("5. In che città vuoi lavorare?", "Lì cerco tutti gli annunci dell'ultima settimana, entro circa 40 km. Fino a tre città, separate da una virgola. Lascia vuoto se non ti interessa una città in particolare.",
      h("input", {type:"text", value: (a.cities || []).join(", "), placeholder:"Esempio: Torino", oninput: e => { a.cities = e.target.value.split(",").map(x => x.trim()).filter(Boolean).slice(0, 3); }})),
    field("6. In quali paesi vuoi cercare anche fuori città?", "Annunci delle ultime 24 ore. Nessun paese selezionato = tutta Europa.", chips(WZ_COUNTRIES.map(c => [c, c]), "countries", true)),
    field("7. Che lavoro fai adesso, o qual è stato l'ultimo?", "Serve a capire quali tue competenze si trasferiscono al lavoro che desideri.", text("current", "Esempio: technical sales di software, da due anni")),
    field("8. Che cosa hai studiato?", null, text("education", "Esempio: laurea magistrale in Ingegneria Gestionale")),
    field("9. In che cosa sei più forte?", "Competenze, strumenti, cose che ti riescono bene.", text("strengths", "Esempio: analisi di mercato, Excel, parlare con i clienti")),
    field("10. Quali settori preferisci?", "Gli annunci di questi settori salgono in classifica.", text("prefer", "Esempio: telefonia, software, energia")),
    field("11. Quali settori o lavori vuoi escludere?", "Vengono tolti sempre, anche se per il resto sarebbero adatti.", text("avoid", "Esempio: bancario, call center, vendita porta a porta")),
    h("h2", {style:"margin-top:28px;font-size:22px"}, "Per candidarti al posto tuo"),
    h("p", {class:"hint"}, "Con queste risposte l'AI compila i moduli e scrive le lettere: tu rivedi e invii."),
    applyChips(a.apply),
    msg, h("div", {class:"actions"}, go)], first ? null : () => render());
}
const TIER = {1:"Quello che hai chiesto", 2:"Ruoli vicini", 3:"Ruoli ponte"};
function viewReview(p){
  const msg = h("p", {class:"msg", role:"alert"}), go = h("button", {class:"btn solid", type:"button"}, "Conferma e avvia la ricerca");
  const editable = (label, hint, key) => { const inp = h("input", {type:"text", value: (p[key] || []).join(", "), oninput: e => { p[key] = e.target.value.split(",").map(s => s.trim()).filter(Boolean); }}); return h("div", {class:"field"}, h("div", {class:"ql"}, label), h("p", {class:"hint"}, hint), inp); };
  go.addEventListener("click", async () => {
    if (!p.clusters.some(c => c.on !== false)){ msg.textContent = "Lascia attivo almeno un gruppo di ruoli."; return; }
    go.disabled = true; go.textContent = "Salvo e avvio la ricerca..."; msg.textContent = "";
    const r = await api("profilo", {profile: p});
    go.disabled = false; go.textContent = "Conferma e avvia la ricerca";
    if (!r.ok){ msg.textContent = r.error; return; }
    S.tab = "jobs"; await boot();
  });
  plain([
    h("h1", null, "Ecco cosa cercherei"),
    h("p", {class:"lead"}, ""),
    says("ada", "Vale", "Ho diviso i ruoli in gruppi. Togli la spunta a quelli che non ti interessano: cercherò solo gli altri."),
    p.clusters.map(c => { const cb = h("input", {type:"checkbox", checked: c.on !== false, onchange: e => { c.on = e.target.checked; }}); return h("label", {class:"cluster"}, cb, h("div", null, h("span", {class:"tier"}, TIER[c.tier] || ""), h("b", null, c.name), h("span", null, (c.titles_en || []).slice(0, 5).join(", ")))); }),
    editable("Competenze", "Gli annunci che le citano salgono di voto. Separa con una virgola.", "skills"),
    editable("Parole dei settori che preferisci", "Separa con una virgola.", "prefer_words"),
    editable("Parole dei settori da escludere", "Separa con una virgola.", "avoid_words"),
    msg, h("div", {class:"actions"}, go)], () => viewInterview(p.answers));
}

/* ---------- colloqui: una pagina di preparazione per ogni colloquio ---------- */
const ROUND = {hr:"Primo colloquio (HR)", manager:"Con il responsabile", tecnico:"Tecnico o caso pratico", assessment:"Assessment o di gruppo", finale:"Colloquio finale"};
const CMODE = {video:"Video", presenza:"Di persona", telefono:"Telefono"};
const CLANG = {"":"Come l'annuncio", it:"Italiano", en:"English", es:"Español", fr:"Français", de:"Deutsch"};
const QTYPE = {presentazione:"Presentazione", motivazione:"Motivazione", azienda:"Sull'azienda", ruolo:"Sul ruolo", competenze:"Competenze",
  comportamentale:"Esperienze passate", situazionale:"Cosa faresti se", pratica:"Prova pratica", curiosita:"Curiosità", scomoda:"Domanda scomoda", rilancio:"Approfondimento"};
const SPEECH = {it:"it-IT", en:"en-GB", es:"es-ES", fr:"fr-FR", de:"de-DE", nl:"nl-NL", pt:"pt-PT"};
const colloqui = () => (S.data && S.data.colloqui) || {};
const cWhen = c => { if (!c || !c.when) return null; const d = new Date(c.when.length === 10 ? c.when + "T09:00" : c.when); return isNaN(d) ? null : d; };
function whenLabel(c){
  const d = cWhen(c); if (!d) return "Data da decidere";
  const day = new Date(d); day.setHours(0, 0, 0, 0); const today = new Date(); today.setHours(0, 0, 0, 0);
  const n = Math.round((day - today) / 864e5), hour = c.when.length > 10 ? " alle " + d.toLocaleTimeString("it-IT", {hour:"2-digit", minute:"2-digit"}) : "";
  if (n === 0) return "Oggi" + hour; if (n === 1) return "Domani" + hour; if (n === -1) return "Ieri" + hour;
  if (n > 1 && n < 7) return d.toLocaleDateString("it-IT", {weekday:"long"}).replace(/^./, x => x.toUpperCase()) + hour;
  return d.toLocaleDateString("it-IT", {weekday:"short", day:"numeric", month:"long"}) + hour;
}
const isPast = c => { const d = cWhen(c); return d ? d.getTime() + 3 * 3600e3 < Date.now() : false; };
const cJob = c => { const f = favs()[c.key]; return (f && f.job) || c.job || {}; };
const cLang = c => (c.plan && c.plan.lingua) || c.qlang || c.lang || "en";
function cStats(c){
  const qs = c.qs || [], done = qs.filter(q => (q.prove || []).length);
  const avg = done.length ? done.reduce((s, q) => s + q.prove[q.prove.length - 1].voto, 0) / done.length : null;
  return {n: qs.length, done: done.length, avg};
}
function sortedColloqui(){
  return Object.entries(colloqui()).sort((a, b) => (cWhen(a[1]) || 0) - (cWhen(b[1]) || 0));
}
function cCard(id, c){
  const j = cJob(c), st = cStats(c), past = isPast(c);
  return h("button", {class:"ccard" + (past ? " past" : ""), type:"button", onclick: () => openColloquio(id)},
    h("div", {class:"cwhen"}, whenLabel(c)),
    h("b", null, j.title_it || j.title || "Colloquio"),
    h("div", {class:"co"}, [j.company, ROUND[c.round] || "", CMODE[c.mode] || ""].filter(Boolean).join(" · ")),
    h("div", {class:"ameta"}, c.plan ? h("span", {class:"tag new"}, "Preparazione pronta") : h("span", {class:"tag"}, "Da preparare"),
      st.n ? h("span", null, `Simulazione ${st.done}/${st.n}` + (st.avg != null ? ` · voto medio ${st.avg.toFixed(1).replace(".", ",")}` : "")) : null,
      c.esito ? h("span", {class:"tag"}, ESITO[c.esito] || c.esito) : null));
}
const ESITO = {attesa:"In attesa di risposta", avanti:"Passata al giro dopo", no:"Non è andata"};
function viewColloqui(){
  const all = sortedColloqui(), next = all.filter(([, c]) => !isPast(c)), past = all.filter(([, c]) => isPast(c)).reverse();
  const add = h("button", {class:"btn solid", type:"button", style:"flex:none", onclick: () => openSchedule()}, "+ Programma un colloquio");
  // candidature già spostate su «Colloquio» ma senza data: si programmano con un tocco
  const keys = new Set(all.map(([, c]) => c.key));
  const todo = Object.entries(favs()).filter(([k, f]) => f.state === "interview" && !keys.has(k));
  const todoBox = todo.length ? h("div", {class:"sec"}, h("h4", null, "Da programmare"),
    h("p", {class:"hint"}, "Queste candidature sono in «Colloquio» ma non hanno ancora una data. Toccane una e dimmi quando: preparo la pagina."),
    h("div", {class:"clist"}, todo.map(([k, f]) => h("button", {class:"ccard", type:"button", onclick: () => openSchedule(null, k)},
      h("div", {class:"cwhen"}, "Quando è il colloquio?"), h("b", null, f.job.title_it || f.job.title), h("div", {class:"co"}, [f.job.company, place(f.job)].filter(Boolean).join(" · ")))))) : null;
  if (!all.length) return h("div", {class:"center"},
    h("h1", null, "I tuoi ", h("em", null, "colloqui")),
    says("vaglio", "Tina", "Quando ti chiamano per un colloquio, segnalo qui. Per ogni colloquio ti preparo una pagina: cosa sapere dell'azienda, come presentarti, perché sceglierla. Poi facciamo le prove: io ti faccio le domande come una selezionatrice, tu rispondi a voce o per scritto, e Vale ti dice come migliorare."),
    todoBox, h("div", {class:"actions"}, add));
  return h("div", {class:"cwrap"},
    h("section", {class:"hero"}, h("div", {class:"eyebrow"}, "Preparazione ai colloqui"),
      h("h1", null, next.length ? [h("em", null, String(next.length)), next.length === 1 ? " colloquio in arrivo" : " colloqui in arrivo"] : "Nessun colloquio in arrivo"),
      h("div", {style:"margin-top:14px;display:flex"}, add)),
    todoBox,
    next.length ? h("div", {class:"clist"}, next.map(([id, c]) => cCard(id, c))) : null,
    past.length ? h("div", {class:"sec"}, h("h4", null, "Già fatti"), h("div", {class:"clist"}, past.map(([id, c]) => cCard(id, c)))) : null);
}
function openSchedule(id, presetKey, presetRound){
  const old = id ? colloqui()[id] : null;
  const v = Object.assign({key: presetKey || "", date:"", time:"", round: presetRound || "hr", mode:"video", lang:"", with:"", notes:""}, old ? {
    key: old.key, date: (old.when || "").slice(0, 10), time: (old.when || "").slice(11, 16), round: old.round || "hr", mode: old.mode || "video",
    lang: old.lang || "", with: old.with || "", notes: old.notes || ""} : {});
  const order = ["interview", "cv_requested", "replied", "applied", "offer", "interested"];
  const apps = Object.entries(favs()).filter(([, f]) => f.state !== "discarded" && f.state !== "closed")
    .sort((a, b) => order.indexOf(a[1].state) - order.indexOf(b[1].state));
  const chipsOf = (opts, k) => { const box = h("div", {class:"wrap"}); const draw = () => box.replaceChildren(...Object.entries(opts).map(([val, t]) =>
    h("button", {class:"chip", type:"button", "aria-pressed": String(v[k] === val), onclick: () => { v[k] = val; draw(); }}, t))); draw(); return box; };
  const sel = h("select", {class:"csel", "aria-label":"Candidatura", onchange: e => { v.key = e.target.value; }},
    h("option", {value:""}, "Scegli la candidatura..."),
    apps.map(([k, f]) => h("option", {value: k, selected: k === v.key ? true : null}, [f.job.title_it || f.job.title, f.job.company].filter(Boolean).join(" · "))));
  const date = h("input", {type:"date", value: v.date, "aria-label":"Giorno", oninput: e => { v.date = e.target.value; }});
  const time = h("input", {type:"time", value: v.time, "aria-label":"Ora", oninput: e => { v.time = e.target.value; }});
  const who = h("input", {type:"text", maxlength:"120", value: v.with, placeholder:"Es. recruiter HR, Head of Sales", oninput: e => { v.with = e.target.value; }});
  const notes = h("textarea", {maxlength:"1500", placeholder:"Es. «Colloquio conoscitivo di 30 minuti su Google Meet, parleremo della tua esperienza e del ruolo»", oninput: e => { v.notes = e.target.value; }}, v.notes);
  const msg = h("p", {class:"msg", role:"alert"});
  const go = h("button", {class:"btn solid", type:"button", onclick: async () => {
    if (!v.key){ msg.textContent = "Scegli la candidatura del colloquio."; return; }
    if (!v.date){ msg.textContent = "Indica il giorno del colloquio."; return; }
    go.disabled = true; go.textContent = "Salvo...";
    const r = await api("colloquio", {id: id || undefined, key: v.key, when: v.date + (v.time ? "T" + v.time : ""), round: v.round, mode: v.mode, lang: v.lang, with: v.with, notes: v.notes});
    go.disabled = false; go.textContent = "Salva";
    if (!r.ok){ msg.textContent = r.error; return; }
    S.data.colloqui = r.colloqui; if (r.tracker) S.data.tracker = r.tracker;
    closeSheet(); toast(id ? "Colloquio aggiornato" : "Colloquio salvato: preparo la tua pagina");
    openColloquio(r.id);
  }}, "Salva");
  const field = (label, node, hint) => h("div", {class:"field"}, h("div", {class:"ql"}, label), hint ? h("p", {class:"hint"}, hint) : null, node);
  openSheet(h("h2", null, id ? "Modifica il colloquio" : "Programma un colloquio"),
    h("div", null,
      id ? null : field("Per quale candidatura?", apps.length ? sel : h("p", {class:"hint"}, "Non hai ancora candidature."),
        h("button", {class:"linkbtn", type:"button", style:"padding:0;min-height:0", onclick: openImport}, "Non è in elenco? Aggiungi l'annuncio con il link")),
      field("Quando", h("div", {class:"duo"}, date, time)),
      field("Che colloquio è", chipsOf(ROUND, "round")),
      field("Come", chipsOf(CMODE, "mode")),
      field("In che lingua", chipsOf(CLANG, "lang"), "Le domande della simulazione saranno in questa lingua."),
      field("Chi ti intervista (facoltativo)", who, "Basta il ruolo: niente nomi."),
      field("Cosa sai del colloquio (facoltativo)", notes, "Incolla qui le informazioni della mail di invito: durata, argomenti, prove."), msg),
    h("div", {class:"actions"}, go));
}

/* preparazione automatica: ricerca sul web, ricerca in ordine, strategia, domande. Ogni passo è una chiamata breve. */
S.prep = S.prep || {};
const PREP_STEPS = [["web", "Cerco l'azienda sul web: sito, notizie, video, come fa i colloqui", c => c.web || c.research],
  ["ricerca", "Metto in ordine quello che ho trovato", c => c.research], ["piano", "Preparo la tua strategia per il colloquio", c => c.plan],
  ["domande", "Preparo le domande della simulazione", c => (c.qs || []).length]];
async function prepare(id, only){
  const p = S.prep[id] = {running: true, step: "", error: ""};
  for (const [step, , done] of PREP_STEPS){
    const c = colloqui()[id]; if (!c) return;
    if (only ? only !== step && !(only === "ricerca" && step === "web") : done(c)) continue;
    p.step = step; redrawColloquio(id);
    const r = await api("colloquio_" + step, {id, cv: cvForAi()});
    if (!r.ok){ p.error = r.error; p.running = false; redrawColloquio(id); return; }
    if (r.colloquio) S.data.colloqui[id] = r.colloquio;
    else if (step === "web") S.data.colloqui[id].web = r.trovati;
    if (only === step) break;
  }
  p.running = false; p.step = ""; redrawColloquio(id);
}
function openColloquio(id){ S.tab = "int"; S.cid = id; S.csec = S.csec || "strategia"; S.qi = 0; render(); window.scrollTo(0, 0);
  const c = colloqui()[id]; if (c && !(S.prep[id] || {}).running && PREP_STEPS.some(([, , done]) => !done(c))) prepare(id); }
function redrawColloquio(id){ if (S.tab === "int" && S.cid === id && !sheetEl) render(); }
function prepBox(id, c){
  const p = S.prep[id] || {};
  const missing = PREP_STEPS.filter(([, , done]) => !done(c));
  if (!missing.length && !p.running) return null;
  return h("div", {class:"prep"},
    says("ada", "Vale", p.error ? p.error : "Sto preparando la tua pagina per questo colloquio. Ci vuole un paio di minuti: puoi restare qui o tornare dopo."),
    h("ul", {class:"steps"}, PREP_STEPS.map(([step, label, done]) => h("li", {class: done(c) ? "done" : p.step === step ? "on" : ""}, (done(c) ? "✓ " : p.step === step ? "… " : "") + label))),
    !p.running ? h("div", {class:"actions"}, h("button", {class:"btn solid", type:"button", onclick: () => prepare(id)}, p.error ? "Riprova" : "Prepara")) : null,
    !store.get("cvtext", "") ? h("p", {class:"hint", style:"margin-top:10px"}, "Consiglio: carica il CV in «Profilo». Senza CV non conosco le tue esperienze e le storie da raccontare restano tracce da completare.") : null);
}
function speak(text, lang){
  if (!window.speechSynthesis) return toast("Il tuo browser non sa leggere ad alta voce");
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text); u.lang = SPEECH[lang] || "en-GB"; u.rate = 0.98;
  const v = speechSynthesis.getVoices().find(x => x.lang && x.lang.toLowerCase().startsWith(u.lang.slice(0, 2).toLowerCase())); if (v) u.voice = v;
  speechSynthesis.speak(u);
}
const listenBtn = (text, lang, label) => h("button", {class:"copy", type:"button", onclick: () => speak(text, lang)}, label || "🔊 Ascolta");
const ul = (items, cls) => items && items.length ? h("ul", {class:"reasons" + (cls ? " " + cls : "")}, items.map(t => h("li", null, t))) : null;
const csec = (title, ...kids) => h("div", {class:"kitb"}, h("div", {class:"kith"}, h("b", null, title)), ...kids);
function secStrategia(id, c){
  const p = c.plan; if (!p) return h("p", {class:"hint"}, "La strategia arriva tra poco.");
  const lang = cLang(c), checks = store.get("cchk." + id, {});
  return h("div", null,
    p.in_breve ? says("ada", "Vale", p.in_breve) : null,
    p.pitch ? h("div", {class:"kitb"}, h("div", {class:"kith"}, h("b", null, "«Parlami di te»: la tua presentazione"), h("span", {class:"btnrow"}, listenBtn(p.pitch, lang), copyBtn(p.pitch))),
      h("p", {class:"kitt"}, p.pitch), h("p", {class:"hint", style:"margin-top:8px"}, "Ripetila ad alta voce finché ti viene naturale, con parole tue: 60-90 secondi.")) : null,
    (p.perche_azienda || []).length ? csec("Perché proprio questa azienda", ul(p.perche_azienda)) : null,
    p.percorso ? csec("Come si inserisce nel tuo percorso", h("p", {class:"kitt"}, p.percorso)) : null,
    (p.punti_forti || []).length ? csec("I tuoi punti forti per questo ruolo", h("div", null, p.punti_forti.map(x => h("div", {class:"qa2"}, h("b", null, x.punto), h("p", {class:"kitt"}, x.prova))))) : null,
    (p.punti_deboli || []).length ? csec("Cosa può preoccuparli, e come rispondere", h("div", null, p.punti_deboli.map(x => h("div", {class:"qa2"}, h("b", null, x.rischio), h("p", {class:"kitt"}, x.risposta))))) : null,
    (p.storie || []).length ? csec("Storie da raccontare (metodo STAR)", h("p", {class:"hint", style:"margin:6px 0 0"}, "Situazione, Compito, Azione, Risultato. Sostituisci le parti tra [ ] con i fatti veri e controlla che ogni frase sia vera."),
      h("div", null, p.storie.map(x => h("div", {class:"qa2"}, h("div", {class:"kith"}, h("b", null, x.titolo), listenBtn(x.star, lang)), h("p", {class:"kitt"}, x.star), x.per ? h("p", {class:"hint", style:"margin-top:6px"}, "Usala per: " + x.per) : null)))) : null,
    (p.domande_da_fare || []).length ? csec("Domande da fare tu, alla fine", ul(p.domande_da_fare)) : null,
    p.stipendio ? csec("Se ti chiedono la retribuzione", h("p", {class:"kitt"}, p.stipendio)) : null,
    (p.parole_chiave || []).length ? csec("Parole da usare", h("div", {class:"tags", style:"margin-top:8px"}, p.parole_chiave.map(w => h("span", {class:"tag"}, w)))) : null,
    (p.promemoria || []).length ? csec("Il giorno del colloquio", h("div", null, p.promemoria.map((t, i) => h("label", {class:"check"},
      h("input", {type:"checkbox", checked: checks[i] ? true : null, onchange: e => { checks[i] = e.target.checked; store.set("cchk." + id, checks); }}), h("span", null, t))))) : null,
    h("p", {class:"hint"}, `Preparato il ${p.creato || ""}${p.modello ? " con " + String(p.modello).replace(/^models\//, "") : ""}. Basato sul tuo profilo${store.get("cvtext", "") ? ", sul CV" : ""} e sulla ricerca sull'azienda.`),
    h("button", {class:"linkbtn", type:"button", onclick: () => prepare(id, "piano")}, "Rifai la strategia"));
}
function secAzienda(id, c){
  const r = c.research; if (!r) return h("p", {class:"hint"}, "La ricerca sull'azienda arriva tra poco.");
  const a = r.azienda || {}, s = r.selezione || {}, j = cJob(c);
  const link = (u, t) => /^https?:\/\//.test(u || "") ? h("a", {href: u, target:"_blank", rel:"noopener noreferrer"}, t || u.replace(/^https?:\/\/(www\.)?/, "").slice(0, 60)) : null;
  return h("div", null,
    a.chi_sono ? csec(j.company || "L'azienda", h("p", {class:"kitt"}, a.chi_sono), r.sito ? h("p", {class:"hint", style:"margin-top:8px"}, "Sito: ", link(r.sito)) : null) : null,
    (a.prodotti || []).length ? csec("Cosa vende", h("div", {class:"tags", style:"margin-top:8px"}, a.prodotti.map(w => h("span", {class:"tag"}, w)))) : null,
    a.mercato ? csec("Clienti e mercato", h("p", {class:"kitt"}, a.mercato), (a.concorrenti || []).length ? h("p", {class:"hint", style:"margin-top:8px"}, "Concorrenti: " + a.concorrenti.join(", ")) : null) : null,
    (a.numeri || []).length ? csec("I numeri", ul(a.numeri)) : null,
    (a.notizie || []).length ? csec("Notizie recenti", h("ul", {class:"reasons"}, a.notizie.map(n => h("li", null, h("span", null, n.t, n.u ? [" ", link(n.u, "(fonte)")] : null))))) : null,
    (a.cultura || []).length ? csec("Cultura e valori", ul(a.cultura), h("p", {class:"hint", style:"margin-top:8px"}, "Citali nelle risposte con esempi tuoi: è quello che chi seleziona vuole sentire.")) : null,
    (s.fasi || []).length || (s.cosa_cercano || []).length ? csec("Come selezionano",
      (s.fasi || []).length ? h("ol", {class:"timeline"}, s.fasi.map(t => h("li", null, t))) : null,
      (s.cosa_cercano || []).length ? [h("p", {class:"hint", style:"margin:10px 0 4px"}, "Cosa cercano"), ul(s.cosa_cercano)] : null) : null,
    (s.domande_riportate || []).length ? csec("Domande che hanno fatto ad altri candidati", ul(s.domande_riportate), h("p", {class:"hint", style:"margin-top:8px"}, "Le trovi anche nella simulazione.")) : null,
    (s.consigli || []).length ? csec("Consigli per questo colloquio", ul(s.consigli)) : null,
    (r.video || []).length ? csec("Video da guardare prima", h("div", {class:"vids"}, r.video.map(v => h("a", {class:"vid", href: "https://www.youtube.com/watch?v=" + encodeURIComponent(v.id), target:"_blank", rel:"noopener noreferrer"},
      h("img", {src: "https://i.ytimg.com/vi/" + encodeURIComponent(v.id) + "/mqdefault.jpg", alt:"", loading:"lazy"}), h("b", null, v.t), h("span", null, [v.ch, v.len].filter(Boolean).join(" · ")), v.perche ? h("small", null, v.perche) : null)))) : null,
    (r.non_trovato || []).length ? h("div", {class:"note"}, h("b", null, "Non trovato: "), r.non_trovato.join(" · ")) : null,
    (r.fonti || []).length ? h("details", {class:"fonti"}, h("summary", null, `Fonti (${r.fonti.length})`), h("ul", null, r.fonti.map(u => h("li", null, link(u))))) : null,
    h("p", {class:"hint"}, `Ricerca del ${r.creato || ""}: ${(r.trovati || {}).risultati || 0} risultati, ${(r.trovati || {}).pagine || 0} pagine lette, ${(r.trovati || {}).video || 0} video. Solo fatti trovati nelle fonti.`),
    h("button", {class:"linkbtn", type:"button", onclick: () => { const x = colloqui()[id]; delete x.research; delete x.web; prepare(id, "ricerca"); }}, "Rifai la ricerca"));
}
let recog = null;
function stopRecog(){ if (recog){ try { recog.stop(); } catch (e) {} recog = null; } }
function secSimula(id, c){
  const qs = c.qs || []; if (!qs.length) return h("p", {class:"hint"}, "Le domande arrivano tra poco.");
  S.qi = Math.max(0, Math.min(S.qi || 0, qs.length - 1));
  const q = qs[S.qi], lang = cLang(c), st = cStats(c), last = (q.prove || []).slice(-1)[0];
  const color = x => !(x.prove || []).length ? "" : x.prove[x.prove.length - 1].voto >= 8 ? " ok" : x.prove[x.prove.length - 1].voto >= 6 ? " mid" : " low";
  const nav = h("div", {class:"qnav", role:"tablist", "aria-label":"Domande"}, qs.map((x, i) => h("button", {type:"button", class:"qn" + color(x), "aria-current": i === S.qi ? "true" : null,
    title: x.d, onclick: () => { stopRecog(); S.qi = i; render(); }}, String(i + 1))));
  const draftKey = "cdraft." + id + "." + q.id;
  const ta = h("textarea", {class:"answer", placeholder: lang === "it" ? "Rispondi come faresti al colloquio..." : "Rispondi come faresti al colloquio, in " + (CLANG[lang] || lang) + "...", "aria-label":"La tua risposta",
    oninput: e => store.set(draftKey, e.target.value)}, store.get(draftKey, ""));
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const mic = SR ? h("button", {class:"btn mic", type:"button", onclick: () => {
    if (recog){ stopRecog(); mic.classList.remove("rec"); mic.textContent = "🎤 A voce"; return; }
    recog = new SR(); recog.lang = SPEECH[lang] || "en-GB"; recog.continuous = true; recog.interimResults = true;
    const base = ta.value ? ta.value.trim() + " " : "";
    recog.onresult = e => { let t = ""; for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript; ta.value = base + t; store.set(draftKey, ta.value); };
    recog.onend = () => { recog = null; mic.classList.remove("rec"); mic.textContent = "🎤 A voce"; };
    recog.onerror = e => { if (e.error === "not-allowed") toast("Permetti l'uso del microfono per rispondere a voce"); };
    try { recog.start(); mic.classList.add("rec"); mic.textContent = "⏹ Fine"; } catch (e) { toast("Microfono non disponibile"); recog = null; }
  }}, "🎤 A voce") : null;
  const send = h("button", {class:"btn solid", type:"button", onclick: async () => {
    stopRecog(); const answer = ta.value.trim();
    if (answer.length < 3){ toast("Scrivi o detta la tua risposta"); return; }
    send.disabled = true; send.textContent = "Vale sta valutando...";
    const r = await api("colloquio_risposta", {id, qid: q.id, answer, cv: cvForAi()});
    send.disabled = false; send.textContent = "Valuta la risposta";
    if (!r.ok){ toast(r.error); return; }
    S.data.colloqui[id] = r.colloquio; store.del(draftKey); render();
    requestAnimationFrame(() => { const fb = document.querySelector(".feedback"); if (fb) fb.scrollIntoView({behavior:"smooth", block:"start"}); });
  }}, "Valuta la risposta");
  const fb = last ? h("div", {class:"feedback"},
    h("div", {class:"score"}, h("b", {class: last.voto >= 8 ? "ok" : last.voto >= 6 ? "mid" : "low"}, String(last.voto)), h("span", null, "su 10"), h("p", null, last.giudizio)),
    masc ? h("div", {class:"says", style:"margin:12px 0 0"}, masc("ada"), h("div", {class:"bubble"}, h("b", null, "Vale"),
      (last.bene || []).length ? [h("div", {class:"fbh"}, "Cosa funziona"), ul(last.bene)] : null,
      (last.migliora || []).length ? [h("div", {class:"fbh"}, "Cosa migliorare"), ul(last.migliora, "warnl")] : null)) : null,
    last.risposta_migliore ? h("div", {class:"kitb"}, h("div", {class:"kith"}, h("b", null, "Come potresti rispondere"), h("span", {class:"btnrow"}, listenBtn(last.risposta_migliore, lang), copyBtn(last.risposta_migliore))),
      h("p", {class:"kitt"}, last.risposta_migliore), h("p", {class:"hint", style:"margin-top:8px"}, "Non va imparata a memoria: prendi la struttura e dilla con parole tue. Le parti tra [ ] sono da completare con fatti veri.")) : null,
    last.rilancio ? h("div", {class:"kitb"}, h("div", {class:"kith"}, h("b", null, "Tina potrebbe insistere così")), h("p", {class:"kitt"}, last.rilancio),
      h("button", {class:"btn", type:"button", style:"margin-top:8px;width:100%", onclick: async e => {
        e.target.disabled = true; const r = await api("colloquio_risposta", {id, qid: q.id, nuova: last.rilancio});
        if (!r.ok){ e.target.disabled = false; return toast(r.error); }
        S.data.colloqui[id] = r.colloquio; S.qi = r.colloquio.qs.findIndex(x => x.id === r.qid); render(); window.scrollTo(0, 0); }}, "Rispondi a questa domanda")) : null,
    (q.prove || []).length > 1 ? h("details", {class:"fonti"}, h("summary", null, `Le tue risposte precedenti (${q.prove.length - 1})`),
      q.prove.slice(0, -1).reverse().map(x => h("div", {class:"qa2"}, h("b", null, `Voto ${x.voto} · ${x.t || ""}`), h("p", {class:"kitt"}, x.risposta))))
      : null) : null;
  return h("div", null,
    h("div", {class:"simtop"}, h("span", null, `Domanda ${S.qi + 1} di ${qs.length}`), st.done ? h("span", null, `Risposte: ${st.done} · voto medio ${st.avg.toFixed(1).replace(".", ",")}`) : null),
    nav,
    h("div", {class:"qcard"},
      h("div", {class:"says", style:"margin:0"}, masc("vaglio"), h("div", {class:"bubble"}, h("b", null, "Tina, selezionatrice"), h("p", {class:"qtext"}, q.d))),
      h("div", {class:"tags", style:"margin-top:10px"}, h("span", {class:"tag"}, QTYPE[q.tipo] || q.tipo), q.online ? h("span", {class:"tag pref"}, "Fatta davvero ad altri candidati") : null),
      h("div", {class:"btnrow", style:"margin-top:10px"}, listenBtn(q.d, lang, "🔊 Ascolta la domanda")),
      q.it ? h("details", {class:"hintd"}, h("summary", null, "Traduzione"), h("p", null, q.it)) : null,
      q.perche ? h("details", {class:"hintd"}, h("summary", null, "Perché te la fanno"), h("p", null, q.perche)) : null,
      q.traccia ? h("details", {class:"hintd"}, h("summary", null, "Un aiutino"), h("p", null, q.traccia)) : null),
    h("div", {class:"field"}, ta),
    h("div", {class:"duo", style:"margin-top:10px"}, mic, send),
    !SR ? h("p", {class:"hint", style:"margin-top:8px"}, "Per rispondere a voce usa il microfono della tastiera del telefono (dettatura).") : null,
    fb,
    h("div", {class:"duo", style:"margin-top:16px"},
      h("button", {class:"btn", type:"button", disabled: S.qi === 0 ? true : null, onclick: () => { stopRecog(); S.qi--; render(); window.scrollTo(0, 0); }}, "← Precedente"),
      S.qi < qs.length - 1 ? h("button", {class:"btn", type:"button", onclick: () => { stopRecog(); S.qi++; render(); window.scrollTo(0, 0); }}, "Prossima →")
        : h("button", {class:"btn", type:"button", onclick: async e => { e.target.disabled = true; e.target.textContent = "Tina prepara altre domande...";
            const r = await api("colloquio_domande", {id, more: true, cv: cvForAi()}); if (!r.ok){ e.target.disabled = false; e.target.textContent = "Altre domande, più difficili"; return toast(r.error); }
            S.data.colloqui[id] = r.colloquio; S.qi++; render(); window.scrollTo(0, 0); }}, "Altre domande, più difficili")),
    h("button", {class:"linkbtn", type:"button", onclick: () => { if (confirm("Rifare tutte le domande da capo? Le tue risposte a queste domande si perdono.")) { const x = colloqui()[id]; x.qs = []; S.qi = 0; prepare(id, "domande"); } }}, "Rifai le domande da capo"));
}
function secDopo(id, c){
  const v = {after: c.after || "", esito: c.esito || ""};
  const ta = h("textarea", {class:"answer", placeholder:"Che domande ti hanno fatto? Cosa è andato bene, cosa no? Cosa ti hanno detto dei prossimi passi?", oninput: e => { v.after = e.target.value; }}, v.after);
  const box = h("div", {class:"wrap"}); const draw = () => box.replaceChildren(...Object.entries(ESITO).map(([k, t]) => h("button", {class:"chip", type:"button", "aria-pressed": String(v.esito === k), onclick: () => { v.esito = k; draw(); }}, t))); draw();
  const save = h("button", {class:"btn solid", type:"button", onclick: async () => {
    save.disabled = true; const r = await api("colloquio", {id, after: v.after, esito: v.esito}); save.disabled = false;
    if (!r.ok) return toast(r.error);
    S.data.colloqui = r.colloqui; if (r.tracker) S.data.tracker = r.tracker; toast("Salvato: ne terrò conto per il prossimo colloquio"); render();
  }}, "Salva");
  return h("div", null,
    says("ada", "Vale", "Subito dopo il colloquio, finché te lo ricordi bene, scrivi qui com'è andata. Se ti chiamano per il giro successivo, preparo il prossimo colloquio partendo da qui."),
    h("div", {class:"field"}, ta), h("div", {class:"field"}, h("div", {class:"ql"}, "Com'è finita"), box),
    h("div", {class:"actions"}, save),
    c.esito === "avanti" ? h("div", {class:"actions"}, h("button", {class:"btn", type:"button", onclick: () => openSchedule(null, c.key, c.round === "hr" ? "manager" : "finale")}, "Programma il prossimo colloquio")) : null);
}
function viewColloquio(id){
  const c = colloqui()[id];
  if (!c){ S.cid = null; return viewColloqui(); }
  const j = cJob(c), sec = S.csec || "strategia";
  const tabs = [["strategia", "Strategia"], ["azienda", "Azienda"], ["simula", "Simulazione"], ["dopo", "Dopo"]];
  const body = {strategia: secStrategia, azienda: secAzienda, simula: secSimula, dopo: secDopo}[sec](id, c);
  return h("div", {class:"cwrap"},
    h("button", {class:"linkbtn", type:"button", style:"padding:0", onclick: () => { stopRecog(); S.cid = null; render(); }}, "← Tutti i colloqui"),
    h("section", {class:"chead"},
      h("div", {class:"eyebrow"}, [whenLabel(c), ROUND[c.round], CMODE[c.mode]].filter(Boolean).join(" · ")),
      h("h1", null, j.title_it || j.title || "Colloquio"),
      h("div", {class:"co"}, [j.company, place(j)].filter(Boolean).join(" · ")),
      h("div", {class:"wrap", style:"margin-top:12px"},
        h("button", {class:"chip", type:"button", onclick: () => openSchedule(id)}, "Modifica"),
        favs()[c.key] ? h("button", {class:"chip", type:"button", onclick: () => openApp(c.key)}, "L'annuncio e la candidatura") : null,
        h("button", {class:"chip", type:"button", onclick: async () => { if (!confirm("Cancellare questo colloquio e la sua preparazione?")) return;
          const r = await api("colloquio", {id, delete: true}); if (!r.ok) return toast(r.error); S.data.colloqui = r.colloqui; S.cid = null; render(); }}, "Cancella"))),
    prepBox(id, c),
    h("div", {class:"chips ctabs", role:"tablist"}, tabs.map(([k, t]) => h("button", {class:"chip", type:"button", role:"tab", "aria-pressed": String(sec === k),
      onclick: () => { stopRecog(); S.csec = k; render(); window.scrollTo(0, 0); }}, t))),
    body);
}

/* ---------- mercato nascosto: aziende che probabilmente assumono nei suoi ruoli senza averlo pubblicato ---------- */
S.mprep = {running: false, step: "", error: ""};
const MSTEPS = [["cerca", "Leggo le notizie delle tue città: finanziamenti, nuove sedi, espansioni"], ["analisi", "Scelgo le aziende adatte a te"],
  ["verifica", "Cerco i loro siti carriere e le posizioni aperte"]];
async function runMercato(){
  const p = S.mprep = {running: true, step: "cerca", error: ""}; render();
  for (const [step] of MSTEPS){
    p.step = step; if (S.merc) render();
    let r = await api("mercato_" + step, step === "verifica" ? {n: 4} : {});
    if (r.ok && r.mercato) S.data.mercato = r.mercato;
    while (r.ok && step === "verifica" && r.rimaste > 0){ r = await api("mercato_verifica", {n: 4}); if (r.ok && r.mercato){ S.data.mercato = r.mercato; if (S.merc && !sheetEl) render(); } }
    if (!r.ok){ p.error = r.error; break; }
  }
  p.running = false; p.step = ""; if (S.merc && !sheetEl) render();
}
function mercatoCard(){
  const m = S.data.mercato || {}, n = (m.aziende || []).length;
  return h("button", {class:"mcard", type:"button", onclick: () => { S.merc = true; render(); window.scrollTo(0, 0); }},
    h("b", null, "Mercato nascosto"),
    h("span", null, n ? `${n} aziende che probabilmente assumono nel tuo ruolo senza averlo pubblicato` : "Scopri le aziende che probabilmente assumono nel tuo ruolo senza averlo pubblicato sui portali"));
}
function openMsg(i){
  const a = (S.data.mercato.aziende || [])[i], k = a.msg;
  if (!k) return;
  openSheet(h("div", null, h("h2", null, "Candidatura spontanea"), h("div", {class:"co"}, a.nome + (a.contatto ? " · da mandare a: " + a.contatto : ""))),
    h("div", null,
      block("Email", (k.oggetto ? "Oggetto: " + k.oggetto + "\n\n" : "") + k.email,
        h("a", {class:"btn", style:"margin-top:8px;width:100%", href: "mailto:?subject=" + encodeURIComponent(k.oggetto || "") + "&body=" + encodeURIComponent(sign(k.email))}, "Apri nella posta")),
      k.linkedin ? block("Messaggio su LinkedIn", k.linkedin) : null,
      h("p", {class:"hint"}, "Rileggi e aggiusta prima di inviare: le parti tra [ ] sono da completare. Allega il CV.")),
    h("div", {class:"actions"}, h("button", {class:"btn", type:"button", onclick: e => writeMsg(i, e.currentTarget)}, "Riscrivi")));
}
async function writeMsg(i, btn){
  if (btn){ btn.disabled = true; btn.textContent = "Vale sta scrivendo..."; }
  const r = await api("mercato_messaggio", {i, cv: cvForAi()});
  if (btn){ btn.disabled = false; btn.textContent = "Scrivi la candidatura spontanea"; }
  if (!r.ok) return toast(r.error);
  S.data.mercato = r.mercato; render(); openMsg(i);
}
function viewMercato(){
  const m = S.data.mercato || {}, az = m.aziende || [], p = S.mprep;
  const link = (u, t) => /^https?:\/\//.test(u || "") ? h("a", {href: u, target:"_blank", rel:"noopener noreferrer"}, t) : null;
  const li = a => "https://www.linkedin.com/search/results/people/?keywords=" + encodeURIComponent((a.contatto || "") + " " + a.nome);
  const prog = p.running || p.error ? h("div", {class:"prep"},
    says("ada", "Vale", p.error || "Sto cercando: ci vuole un minuto o due. Puoi restare qui."),
    h("ul", {class:"steps"}, MSTEPS.map(([s, label]) => { const i = MSTEPS.findIndex(x => x[0] === p.step), j = MSTEPS.findIndex(x => x[0] === s);
      return h("li", {class: p.running && j < i ? "done" : p.step === s ? "on" : ""}, (p.running && j < i ? "✓ " : p.step === s ? "… " : "") + label); })),
    !p.running ? h("div", {class:"actions"}, h("button", {class:"btn solid", type:"button", onclick: runMercato}, "Riprova")) : null) : null;
  const cards = az.map((a, i) => h("div", {class:"kitb mz"},
    h("div", {class:"kith"}, h("b", {style:"font-size:17px"}, a.nome), h("span", {class:"tag" + (a.priorita === "alta" ? " new" : "")}, a.priorita === "alta" ? "Priorità alta" : "Priorità media")),
    h("div", {class:"co", style:"margin-top:2px;font-size:14px;color:var(--text2)"}, ["📍 " + a.citta, a.settore].filter(Boolean).join(" · ")),
    h("p", {class:"kitt"}, h("b", null, "Segnale: "), a.segnale, a.notizia ? [" ", link(a.notizia.u, "(notizia)")] : null),
    a.perche ? h("p", {class:"kitt"}, a.perche) : null,
    h("div", {class:"facts", style:"margin-top:10px"},
      h("div", {class:"fact"}, h("span", null, "Ruolo da proporre"), h("b", null, a.ruolo || "-")),
      h("div", {class:"fact"}, h("span", null, "A chi scrivere"), h("b", null, a.contatto || "-"))),
    a.come ? h("p", {class:"hint", style:"margin-top:8px"}, "Come: " + a.come) : null,
    a.annunci && (a.annunci.tuoi || []).length ? h("div", {class:"note", style:"border-color:var(--radar)"}, h("b", null, "Sul loro sito carriere c'è già qualcosa per te:"),
      h("ul", {class:"reasons", style:"margin-top:6px"}, a.annunci.tuoi.map(x => h("li", null, link(x.u, x.t) || x.t, x.luogo ? " · " + x.luogo : "")))) :
      a.annunci ? h("p", {class:"hint", style:"margin-top:8px"}, `Sul loro sito carriere ci sono ${a.annunci.n} posizioni aperte, nessuna nel tuo ruolo: proponiti tu.`) : null,
    h("div", {class:"wrap", style:"margin-top:10px"},
      h("button", {class:"chip", type:"button", onclick: e => a.msg ? openMsg(i) : writeMsg(i, e.currentTarget)}, a.msg ? "La tua candidatura spontanea" : "Scrivi la candidatura spontanea"),
      h("a", {class:"chip", href: li(a), target:"_blank", rel:"noopener noreferrer", style:"display:inline-flex;align-items:center;text-decoration:none"}, "Trova la persona su LinkedIn"),
      a.carriere ? h("a", {class:"chip", href: a.carriere, target:"_blank", rel:"noopener noreferrer", style:"display:inline-flex;align-items:center;text-decoration:none"}, "Sito carriere") :
        a.sito ? h("a", {class:"chip", href: a.sito, target:"_blank", rel:"noopener noreferrer", style:"display:inline-flex;align-items:center;text-decoration:none"}, "Sito (da verificare)") : null)));
  return h("div", {class:"cwrap"},
    h("button", {class:"linkbtn", type:"button", style:"padding:0", onclick: () => { S.merc = false; render(); }}, "← Candidature"),
    h("section", {class:"chead"}, h("div", {class:"eyebrow"}, "Mercato nascosto"), h("h1", null, "Aziende da contattare")),
    says("ada", "Vale", "Molte aziende assumono senza pubblicare annunci: hanno appena ricevuto un finanziamento, aprono una sede, crescono in fretta, oppure pubblicano solo sul loro sito. Qui trovi quelle delle tue città che fanno per te, con il motivo e a chi scrivere. I loro siti carriere li leggo a ogni ricerca: se esce un annuncio nel tuo ruolo lo trovi tra gli annunci."),
    prog,
    !az.length && !p.running ? h("div", {class:"actions"}, h("button", {class:"btn solid", type:"button", onclick: runMercato}, "Cerca le aziende")) : null,
    az.length ? h("div", null, cards) : null,
    az.length ? h("p", {class:"hint", style:"margin-top:14px"}, `Aggiornato il ${m.at || ""}. Solo aziende trovate nelle notizie e negli annunci delle tue città: niente nomi inventati. I siti sono trovati in automatico, controllali.`) : null,
    az.length && !p.running ? h("button", {class:"linkbtn", type:"button", onclick: runMercato}, "Cerca di nuovo (nuove notizie)") : null);
}

/* ---------- attesa e aggiornamento ---------- */
function radarSvg(){ return '<svg viewBox="0 0 200 200" aria-hidden="true"><circle class="ring" cx="100" cy="100" r="96"/><circle class="ring" cx="100" cy="100" r="64"/><circle class="ring" cx="100" cy="100" r="32"/><g class="sweep"><path d="M100 100L100 4A96 96 0 0 1 183 52z" fill="#36F2A0" opacity=".22"/></g><circle class="blip" cx="140" cy="70" r="4"/><circle class="blip" cx="62" cy="128" r="3.200" style="animation-delay:.7s"/><circle class="blip" cx="118" cy="150" r="3" style="animation-delay:1.3s"/><circle cx="100" cy="100" r="4" fill="#36F2A0"/></svg>'; }
const EXPECT_MIN = 15;
function viewWaiting(){
  const st = S.data.state || {};
  if (!st.running) return h("div", {class:"center"}, says("ada", "Vale", st.error || "Non ci sono ancora annunci. Avvia la ricerca: ci vuole circa un quarto d'ora."), h("div", {class:"actions"}, h("button", {class:"btn solid", type:"button", onclick: refreshNow}, "Avvia la ricerca")));
  const mins = Math.max(0, (Date.now() - new Date(st.started_at || Date.now())) / 60000), pct = Math.min(96, mins / EXPECT_MIN * 100);
  const left = Math.max(1, Math.round(EXPECT_MIN - mins));
  const step = (from, label) => h("li", {class: mins >= from + 4 ? "done" : mins >= from ? "on" : ""}, (mins >= from + 4 ? "✓ " : "") + label);
  return h("div", {class:"center", style:"padding-top:8px"},
    h("div", {class:"radarbox", html: radarSvg()}),
    h("h1", {style:"font-size:clamp(24px,6.500vw,34px);text-align:center"}, "Sto cercando i tuoi annunci"),
    h("p", {class:"lead", style:"text-align:center"}, mins > EXPECT_MIN ? "Ci siamo quasi, ancora un momento." : `Ancora circa ${left} ${left === 1 ? "minuto" : "minuti"}. Puoi chiudere l'app: li trovi qui quando torni.`),
    h("div", {class:"bar"}, h("i", {style:`width:${pct}%`})),
    h("ul", {class:"steps"}, step(0, myPlaces().length ? "Sfoglio LinkedIn e i portali vicino a " + myPlaces().map(p => p.typed || p.name).join(", ") + " e in Europa" : "Sfoglio LinkedIn e gli altri portali in 30 paesi"), step(4, "Leggo gli annunci, partendo dai più adatti"), step(8, "Tina dà un voto a ogni annuncio"), step(13, "Preparo l'elenco")),
    S.data.jobs.length ? null : says("vaglio", "Tina", "Leggo ogni annuncio e tengo solo quelli che c'entrano con quello che cerchi. Niente numeri gonfiati."));
}
function stopPoll(){ clearInterval(S.poll); S.poll = null; }
function startPoll(){
  stopPoll();
  S.poll = setInterval(async () => {
    if (document.hidden) return;
    const r = await api("stato"); if (!r.ok) return;
    if (r.state.running){ S.data.state = r.state; if (S.tab === "jobs" && !S.data.jobs.length && !sheetEl) render(); return; }
    stopPoll(); const d = await api("dati"); if (d.ok){ S.data = d; idb.set("cache", {uid: String(S.token).split(".")[0], data: d}).catch(() => {}); if (!sheetEl) render(); toast(d.state.ok === false ? "La ricerca non è riuscita" : "Annunci aggiornati"); }
  }, 20000);
}
async function refreshNow(){
  if (S.data.state && S.data.state.running){ toast("La ricerca è già in corso"); return; }
  const r = await api("aggiorna", {});
  if (!r.ok){ toast(r.error); return; }
  S.data.state = r.state || {running: true, started_at: new Date().toISOString()};
  toast("Ricerca avviata: circa un quarto d'ora"); render(); startPoll();
}

/* ---------- partenza ---------- */
const theme = store.get("theme", null); if (theme) document.documentElement.dataset.theme = theme;
document.addEventListener("visibilitychange", async () => { if (!document.hidden && S.token && S.data && S.data.profile && !sheetEl && !S.poll){ const r = await api("stato"); if (r.ok && r.state.running){ S.data.state = r.state; render(); startPoll(); } else if (r.ok && S.data.run && r.state.at && r.state.at !== S.data.run.at){ boot(); } } });
window.addEventListener("hashchange", () => { if (/^#t=/.test(location.hash)) boot(); });  // link personale aperto con l'app già aperta
if ("serviceWorker" in navigator) window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
boot();
})();
