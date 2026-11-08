/* Finestrella aperta dal segnalibro "Compila con Job Radar" sulla pagina di un modulo di candidatura.
   Riceve l'elenco dei campi, riempie da sola quelli con i dati della persona (salvati solo su questo dispositivo),
   chiede all'AI le risposte alle altre domande e rimanda tutto alla pagina, che compila senza inviare. */
(() => {
"use strict";
const $msg = document.getElementById("msg"), $out = document.getElementById("out");
const get = (k, d) => { try { const v = localStorage.getItem("jr." + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } };
const token = get("token", null), me = get("me", {});
const say = (html, cls) => { $msg.className = cls || ""; $msg.innerHTML = html; };
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"})[c]);

// dati personali riconosciuti dall'etichetta del campo, in più lingue
const RULES = [
  ["email", /e-?mail|courriel|correo/i, f => f.type === "email" || f.ac === "email"],
  ["telefono", /phone|telefon|téléphone|teléfono|cellulare|mobile|cell\b|handy/i, f => f.type === "tel" || /tel/.test(f.ac)],
  ["linkedin", /linkedin/i],
  ["sito", /website|web site|portfolio|sito|github|homepage|personal site/i],
  ["cognome", /last.?name|surname|family.?name|cognome|nom de famille|nachname|apellido|achternaam/i, f => f.ac === "family-name"],
  ["nome", /first.?name|given.?name|^nome$|^nome\b(?!.*cognome)|prénom|vorname|^nombre$|voornaam/i, f => f.ac === "given-name"],
  ["completo", /full.?name|^name$|^your name|nome e cognome|nome completo|nom complet|vollständiger name|nombre completo|^naam$/i, f => f.ac === "name"],
  ["citta", /^city|città|location|località|^ort$|ville|ciudad|current location|where are you based/i],
];
function personal(f){
  const short = String(f.label || "").length <= 45;  // le domande lunghe vanno all'AI anche se citano "email" o "location"
  for (const [k, rx, test] of RULES){ if ((test && test(f)) || (short && rx.test(f.label)) || rx.test(f.name)) return k; }
  return null;
}
const isCv = f => f.type === "file" && (/resume|cv\b|curriculum|lebenslauf|currículum/i.test(f.label + " " + f.name) || !/cover|lettera|motivation/i.test(f.label + " " + f.name));
const isLetter = f => /cover.?letter|lettera|motivation|motivazione|anschreiben|lettre/i.test(f.label + " " + f.name);
const value = k => k === "completo" ? [me.nome, me.cognome].filter(Boolean).join(" ") : (me[k] || "");

function idb(){ return new Promise((ok, ko) => { const r = indexedDB.open("jobradar", 1); r.onupgradeneeded = () => r.result.createObjectStore("f"); r.onsuccess = () => ok(r.result); r.onerror = () => ko(r.error); }); }
async function cvFile(){ try { const db = await idb(); return await new Promise(ok => { const q = db.transaction("f").objectStore("f").get("cvfile"); q.onsuccess = () => ok(q.result || null); q.onerror = () => ok(null); }); } catch (e) { return null; } }
function cvForAi(){
  const extra = [["Città in cui vive", me.citta]].filter(x => x[1]);
  return get("cvtext", "") + (extra.length ? "\n\nINFORMAZIONI PER I MODULI\n" + extra.map(([k, v]) => k + ": " + v).join("\n") : "");
}

async function handle(req, origin){
  const values = {}, rows = [], ask = [];
  for (const f of req.fields){
    if (f.type === "file"){
      if (isLetter(f)){ values[f.id] = "LETTERA"; continue; }
      if (isCv(f)){ values[f.id] = "CV"; rows.push([f.label || "Allegato", "il tuo CV", "ok"]); }
      continue;
    }
    const k = personal(f);
    if (k){ const v = value(k); if (v){ values[f.id] = v; rows.push([f.label, v, "ok"]); } else rows.push([f.label, "manca nei tuoi dati", "warn"]); continue; }
    ask.push(f);
  }
  let letter = "";
  const wantsLetterFile = Object.values(values).includes("LETTERA");
  if (wantsLetterFile && !ask.some(isLetter)) ask.push({id: "_lettera", label: "Cover letter", long: true});
  if (ask.length || req.fields.some(isLetter)){
    say('<span class="spin"></span>L\'AI sta scrivendo le risposte su questo annuncio (20-40 secondi)...');
    let r;
    try {
      r = await (await fetch("/api/index?a=compila", {method: "POST", headers: {"Content-Type": "application/json", Authorization: "Bearer " + token},
        body: JSON.stringify({url: req.url, title: req.title, page: req.page, fields: ask, cv: cvForAi()})})).json();
    } catch (e) { r = {ok: false, error: "Non riesco a collegarmi a Job Radar."}; }
    if (!r.ok){ say(esc(r.error || "L'AI non ha risposto.") + " Compilo intanto i tuoi dati.", "warn"); r = {answers: {}}; }
    const sign = t => String(t || "").replace(/\[NOME\]/g, value("completo") || "");
    letter = sign(r.letter);
    for (const f of ask){
      const v = isLetter(f) ? letter : sign((r.answers || {})[f.id]);
      if (v){ values[f.id] = v; rows.push([f.label || "Domanda", v, "ok"]); } else rows.push([f.label || "Domanda", "da completare a mano", "warn"]);
    }
  }
  const file = Object.values(values).includes("CV") ? await cvFile() : null;
  let letterFile = null;
  if (wantsLetterFile && letter){
    try { letterFile = await letterPdf(letter); rows.push(["Lettera di presentazione", "allegata in PDF", "ok"]); } catch (e) { rows.push(["Lettera di presentazione", "PDF non riuscito: allegala a mano", "warn"]); }
  }
  for (const [id, v] of Object.entries(values)) if (v === "LETTERA") delete values[id];
  if (Object.values(values).includes("CV") && !file) rows.push(["CV", "non caricato in Job Radar: allegalo a mano", "warn"]);
  window.opener.postMessage({t: "fill", values, file, letterFile, letterIds: req.fields.filter(f => f.type === "file" && isLetter(f)).map(f => f.id)}, origin);
  const done = rows.filter(r => r[2] === "ok").length;
  say(`<b class="ok">${done} campi compilati.</b> Torna alla pagina del modulo: controlla tutto, completa i campi in giallo e premi tu Invia.`);
  $out.innerHTML = '<div class="box">' + rows.map(([a, b, c]) => `<div class="row"><span title="${esc(a)}">${esc(a)}</span><span class="${c}" title="${esc(b)}">${esc(b)}</span></div>`).join("") + "</div>";
  const close = document.createElement("button"); close.textContent = "Chiudi questa finestra"; close.className = "ghost"; close.onclick = () => window.close(); $out.appendChild(close);
}

async function letterPdf(text){
  if (!window.jspdf) await new Promise((ok, ko) => { const s = document.createElement("script"); s.src = "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"; s.onload = ok; s.onerror = ko; document.head.appendChild(s); });
  const plain = t => String(t || "").replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/[–—]/g, "-").replace(/…/g, "...").replace(/[‑ ]/g, " ");
  const doc = new window.jspdf.jsPDF({unit: "mm", format: "a4"});
  const head = [value("completo"), [me.citta, me.email, me.telefono].filter(Boolean).join("  |  "), me.linkedin || ""].filter(Boolean);
  doc.setFont("helvetica", "bold"); doc.setFontSize(15); doc.text(plain(head[0] || ""), 22, 26);
  doc.setFont("helvetica", "normal"); doc.setFontSize(9.5); doc.setTextColor(90); head.slice(1).forEach((l, i) => doc.text(plain(l), 22, 32 + i * 5));
  doc.setTextColor(20); doc.setFontSize(11);
  let y = 32 + head.length * 5 + 12;
  for (const par of plain(text).split(/\n+/)){
    for (const line of doc.splitTextToSize(par, 166)){ if (y > 280){ doc.addPage(); y = 22; } doc.text(line, 22, y); y += 5.6; }
    y += 3;
  }
  return new File([doc.output("blob")], ("Cover_letter_" + (me.cognome || "")).replace(/_+$/, "") + ".pdf", {type: "application/pdf"});
}

if (!window.opener){ say("Questa finestra si apre dal segnalibro «Compila con Job Radar», sulla pagina di un modulo di candidatura.", "warn"); return; }
if (!token){ say('Prima entra in Job Radar con il tuo codice, su <a href="/" target="_blank" style="color:#36F2A0">questa pagina</a>, poi riprova.', "warn"); return; }
if (!me.email && !me.nome) say("I tuoi dati per candidarti non sono ancora inseriti (Job Radar, «Profilo»): compilo solo le risposte.", "warn");
let busy = false;
window.addEventListener("message", ev => {
  const m = ev.data || {};
  if (m.t !== "req" || busy || ev.source !== window.opener) return;
  busy = true;
  handle(m, ev.origin).catch(() => say("Qualcosa non ha funzionato. Chiudi e riprova.", "bad"));
});
window.addEventListener("beforeunload", () => { try { window.opener.postMessage({t: "closed"}, "*"); } catch (e) {} });
window.opener.postMessage({t: "ready"}, "*");
})();
