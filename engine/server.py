"""Server locale di Job Radar: mostra la pagina e permette di aggiornarla con il pulsante "Aggiorna ora".

Uso: python scripts/server.py [--no-open] [--no-auto]
Ascolta solo su 127.0.0.1 (visibile solo da questo computer). Chiudere la finestra nera lo ferma.
"""
import argparse
import json
import os
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(__file__))
import base64  # noqa: E402
import hashlib  # noqa: E402

import re  # noqa: E402
from urllib.parse import quote  # noqa: E402

import build_page  # noqa: E402
import cvhub  # noqa: E402
import cvstore  # noqa: E402
import cvai  # noqa: E402
import cvmatch  # noqa: E402
import deep  # noqa: E402
import facts  # noqa: E402
import llm  # noqa: E402
import run_local  # noqa: E402
import searchprofile  # noqa: E402
import tracker  # noqa: E402
from common import ARCHIVE, DATA, ROOT, read_json, write_json  # noqa: E402

STATE = {"running": False, "log": [], "done_at": None, "error": None, "summary": None, "started_at": None, "expect_min": 13.5, "facts": []}
LOCK = threading.Lock()
PORT = 8765
DIRTY = threading.Event()  # preferiti, note o scartati cambiati dopo che la pagina è stata generata


def _log(msg):
    with LOCK:
        STATE["log"].append(msg)
        STATE["log"] = STATE["log"][-80:]
    print(msg, flush=True)


def _worker():
    try:
        s = run_local.run(24, log=_log, do_notify=False)
        with LOCK:
            STATE["summary"] = {"added": s["added"], "total": s["total"], "best": s["best"]}
            STATE["error"] = None
    except Exception as e:  # mostriamo l'errore nella pagina invece di bloccare tutto
        with LOCK:
            STATE["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        print("Errore:", e, flush=True)
    finally:
        with LOCK:
            STATE["running"] = False
            STATE["done_at"] = datetime.now().astimezone().isoformat(timespec="seconds")


def start_refresh() -> bool:
    with LOCK:
        if STATE["running"]:
            return False
        STATE.update(running=True, log=[], error=None, started_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                     expect_min=float(read_json(ROOT / "config.json", {}).get("linkedin", {}).get("max_minutes", 10)) + 1.0)
    threading.Thread(target=_worker, daemon=True).start()
    threading.Thread(target=_load_facts, daemon=True).start()
    return True


class Server(ThreadingHTTPServer):
    allow_reuse_address = False  # su Windows il riuso permetterebbe due Job Radar sulla stessa porta


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # niente rumore in console
        pass

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        origin = self.headers.get("Origin")
        return host in ("127.0.0.1", "localhost") and (not origin or origin.split("://", 1)[-1].split(":")[0] in ("127.0.0.1", "localhost"))

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b"{}")
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            if not build_page.OUTPUT.exists() or DIRTY.is_set():  # preferiti o note cambiati: la pagina va rigenerata
                DIRTY.clear()
                build_page.main()
            return self._send(200, build_page.OUTPUT.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/ai/status":
            return self._send(200, json.dumps(llm.status(), ensure_ascii=False).encode("utf-8"))
        if path == "/api/status":
            with LOCK:
                return self._send(200, json.dumps(STATE, ensure_ascii=False, default=str).encode("utf-8"))
        if path == "/api/hub/file":  # scarica una versione del CV (originale o tradotta)
            cv_id = (re.search(r"[?&]id=([\w-]+)", self.path) or [None, ""])[1]
            fpath, it = cvhub.path_of(cv_id)
            if not it or not fpath.exists():
                return self._send(404, b"{}")
            body = fpath.read_bytes()
            ctype = {".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8",
                     ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}.get(it["ext"], "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(it["name"]))
            self.end_headers()
            return self.wfile.write(body)
        self._send(404, b"{}")

    def _json_body(self, limit=12_000_000):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > limit:
            return None
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _reply(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, b"{}")
        if self.path == "/api/refresh":
            return self._reply({"started": start_refresh()})
        if self.path == "/api/cv":
            return self._reply(*save_cv(self._json_body()))
        if self.path.startswith("/api/hub/"):
            return self._reply(*hub_action(self.path, self._json_body()))
        if self.path.startswith("/api/track/"):
            return self._reply(*track_action(self.path, self._json_body()))
        if self.path.startswith("/api/profile/"):
            return self._reply(*profile_action(self.path, self._json_body()))
        if self.path == "/api/ai/download":
            return self._reply({"ok": True, "started": llm.start_download()})
        if self.path == "/api/deep":
            return self._reply(*deep_analysis(self._json_body()))
        self._send(404, b"{}")


def save_cv(body):
    """Riceve il CV (file in base64 oppure testo incollato), lo salva in profilo/ e ricalcola i punteggi."""
    if not body:
        return {"ok": False, "error": "File mancante o troppo grande (massimo 8 MB)."}, 400
    try:
        cvstore.PROFILE_DIR.mkdir(exist_ok=True)
        if body.get("text"):
            name, tmp = "CV incollato.txt", cvstore.PROFILE_DIR / "cv_caricato.txt"
            tmp.write_text(body["text"], encoding="utf-8")
        else:
            name = os.path.basename(body.get("name") or "cv.pdf")
            ext = os.path.splitext(name)[1].lower()
            if ext not in (".pdf", ".docx", ".txt"):
                return {"ok": False, "error": "Formato non supportato: usa PDF, DOCX o TXT."}, 400
            tmp = cvstore.PROFILE_DIR / ("cv_caricato" + ext)
            tmp.write_bytes(base64.b64decode(body.get("data") or ""))
        entry = cvhub.add_file(str(tmp), name)
        tmp.unlink()
    except Exception as e:
        return {"ok": False, "error": f"Non riesco a leggere il file: {str(e)[:120]}"}, 400
    if entry["words"] < 40:
        cvhub.delete(entry["id"])
        return {"ok": False, "error": "Nel file non c'è testo leggibile: sembra un'immagine. Da Canva scarica il CV come 'PDF standard', oppure incolla il testo."}, 400
    return _recompute({"words": entry["words"]})


def _recompute(extra=None):
    """Ricalcola i punteggi con il CV in uso e rigenera la pagina."""
    n = cvstore.apply_to_archives()
    build_page.main()
    return {"ok": True, "matched": n, **(extra or {})}, 200


def hub_action(path, body):
    """Operazioni sull'hub dei CV: attiva, elimina, traduci, genera il file tradotto."""
    body = body or {}
    cv_id = str(body.get("id") or "")
    try:
        if path == "/api/hub/activate":
            return _recompute() if cvhub.activate(cv_id) else ({"ok": False, "error": "CV non trovato."}, 404)
        if path == "/api/hub/delete":
            cvhub.delete(cv_id)
            return _recompute()
        if path == "/api/hub/translate":
            engine = str(body.get("engine") or "")
            res, err = cvhub.start_translation(cv_id, engine or ("ai" if cvai.available() else "argos"))
            return ({"ok": True, **res}, 200) if res else ({"ok": False, "error": err}, 400)
        if path in ("/api/hub/edit", "/api/hub/rewrite", "/api/hub/apply"):
            return cv_edit(path, cv_id, body)
        if path == "/api/hub/build":
            res, err = cvhub.finish_translation(cv_id, body.get("segments") or {})
            if not res:
                return {"ok": False, "error": err}, 400
            build_page.main()
            return {"ok": True, **res}, 200
    except Exception as e:  # il modello di traduzione o il PDF possono dare errori: li mostriamo nella pagina
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"}, 500
    return {"ok": False, "error": "Operazione sconosciuta."}, 404


def profile_action(path, body):
    """Intervista: costruisce la proposta di profilo con l'AI; alla conferma la salva e azzera gli annunci valutati con il profilo vecchio."""
    body = body or {}
    if path == "/api/profile/build":
        ans = body.get("answers") or {}
        if len(str(ans.get("desired") or "").strip()) < 8:
            return {"ok": False, "error": "Descrivi con qualche parola il lavoro che cerchi."}, 400
        text, cvp = cvstore.load()
        if text:  # dal CV si passa all'AI solo la parte delle esperienze, senza contatti
            sec = cvmatch._sections(text)
            ans["cv_excerpt"] = (sec.get("experience") or text)[:2500]
        prof = searchprofile.build(ans, cvp)
        prof["answers"].pop("cv_excerpt", None)
        return {"ok": True, "profile": prof}, 200
    if path == "/api/profile/save":
        prof = body.get("profile") or {}
        clusters = [c for c in prof.get("clusters") or [] if c.get("titles_en") or c.get("titles_it")]
        if not any(c.get("on", True) for c in clusters):
            return {"ok": False, "error": "Lascia attivo almeno un gruppo di ruoli."}, 400
        with LOCK:
            if STATE["running"]:
                return {"ok": False, "error": "C'è una ricerca in corso: aspetta che finisca."}, 400
        clean = searchprofile._normalize({**prof, "clusters": clusters}, prof.get("answers") or {}, prof.get("provider") or "")
        for c, src in zip(clean["clusters"], sorted(clusters, key=lambda c: c.get("tier", 2))):
            c["on"] = bool(src.get("on", True))
        searchprofile.save(clean)
        # gli annunci in archivio sono stati scelti e valutati con il profilo di prima: si riparte puliti (i preferiti restano)
        for folder in (ARCHIVE, DATA / "texts"):
            for f in folder.glob("????-??-??.json"):
                f.unlink()
        (DATA / "ultima_ricerca.json").unlink(missing_ok=True)
        build_page.main()
        return {"ok": True}, 200
    return {"ok": False, "error": "Operazione sconosciuta."}, 404


def _api_key():
    return read_json(ROOT / "config.json", {}).get("anthropic", {}).get("api_key", "")


def cv_edit(path, cv_id, body):
    """Editor del CV: apre i blocchi con la valutazione, chiede a Claude una proposta, genera il nuovo file."""
    fpath, it = cvhub.path_of(cv_id)
    if not it:
        return {"ok": False, "error": "CV non trovato."}, 404
    url = str(body.get("url") or "")
    job, job_text = tracker.find_job(url) if url else (None, "")
    if url and not job:
        return {"ok": False, "error": "Annuncio non trovato in archivio."}, 404
    text = cvmatch.extract_text(str(fpath))
    profile = cvmatch.analyze_cv(text)

    if path == "/api/hub/edit":
        res, err = cvhub.start_edit(cv_id)
        if not res:
            return {"ok": False, "error": err}, 400
        out = {"ok": True, **res, "claude": cvai.available()}
        if job:
            m = cvmatch.match(profile, text, job, job_text)
            out.update(job={"title": job.get("title_it") or job["title"], "company": job["company"], "local_ad": bool(job.get("local_ad"))},
                       score=m["score"], missing=m["missing"], matched=m["matched"], tips=m["tips"], keyword_rate=m.get("keyword_rate"))
        else:
            rd = cvmatch.ats_readiness(profile)
            out.update(score=rd["score"], checks=rd["checks"])
        return out, 200

    if path == "/api/hub/rewrite":
        saved = read_json(cvhub.HUB / f"{cv_id}_segs.json", None)
        if not saved:
            return {"ok": False, "error": "Riapri l'editor del CV."}, 400
        missing = cvmatch.match(profile, text, job, job_text)["missing"] if job else []
        if body.get("engine") == "local":
            res = llm.rewrite(saved["segs"], job, job_text, missing, it["lang"])
        else:
            res = cvai.rewrite(saved["segs"], job, job_text, missing, it["lang"])
        return res, 200 if res.get("ok") else 400

    label = ("adattato " + job["company"]) if job else "migliorato"
    res, err = cvhub.finish_edit(cv_id, body.get("segments") or {}, label)
    if not res:
        return {"ok": False, "error": err}, 400
    new_text = res.pop("text")
    new_profile = cvmatch.analyze_cv(new_text)
    if job:
        res["before"] = cvmatch.match(profile, text, job, job_text)["score"]
        res["after"] = cvmatch.match(new_profile, new_text, job, job_text)["score"]
    else:
        res["before"] = cvmatch.ats_readiness(profile)["score"]
        res["after"] = cvmatch.ats_readiness(new_profile)["score"]
    build_page.main()
    return {"ok": True, **res}, 200


def _load_facts():
    """Numeri Eurostat per l'attesa: pescati dal vivo, diversi a ogni ricerca."""
    try:
        items = facts.build(16)
    except Exception:
        items = []
    with LOCK:
        STATE["facts"] = items


def _rebuild_if_dirty():
    if DIRTY.is_set():
        DIRTY.clear()
        build_page.main()


def track_action(path, body):
    """Preferiti, stato della candidatura, nota, annunci scartati."""
    body = body or {}
    url = str(body.get("url") or "")
    if not url:
        return {"ok": False, "error": "Annuncio non indicato."}, 400
    if path == "/api/track/fav":
        res = tracker.set_fav(url, bool(body.get("on")))
    elif path == "/api/track/state":
        res = tracker.set_track(url, body.get("status"), body.get("note"))
    elif path == "/api/track/hide":
        res = tracker.set_hidden(url, bool(body.get("on")))
    else:
        return {"ok": False, "error": "Operazione sconosciuta."}, 404
    if res is None:
        return {"ok": False, "error": "Annuncio non trovato in archivio."}, 404
    DIRTY.set()
    threading.Timer(4, _rebuild_if_dirty).start()  # aggiorna anche il file "Job Radar.html" su disco
    return {"ok": True, "fav": res if isinstance(res, dict) else None}, 200


def deep_analysis(body):
    """Analisi approfondita con Claude per un singolo annuncio (richiede la chiave API in config.json)."""
    if not body or not body.get("url"):
        return {"ok": False, "error": "Annuncio non indicato."}, 400
    text, _profile = cvstore.load()
    if not text:
        return {"ok": False, "error": "Carica prima il CV."}, 400
    job, job_text = tracker.find_job(body["url"])
    if not job:
        return {"ok": False, "error": "Annuncio non trovato in archivio."}, 404
    cache = DATA / "deep" / (hashlib.sha1((body["url"] + text).encode("utf-8")).hexdigest() + ".json")
    cached = read_json(cache, None)
    if cached:
        return cached, 200
    key = read_json(ROOT / "config.json", {}).get("anthropic", {}).get("api_key", "")
    res = deep.analyze(key, text, job, job_text, job.get("cv") or {})
    if res.get("ok"):
        write_json(cache, res)
    return res, 200 if res.get("ok") else 400


def main():
    global PORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--no-auto", action="store_true", help="non avviare subito la ricerca")
    args = ap.parse_args()
    srv = None
    for port in range(8765, 8785):
        try:
            srv = Server(("127.0.0.1", port), Handler)
            PORT = port
            break
        except OSError:
            continue
    if not srv:
        print("Nessuna porta libera tra 8765 e 8784.")
        sys.exit(1)
    url = f"http://127.0.0.1:{PORT}/" + ("" if args.no_auto else "?auto=1")
    print(f"Job Radar e' attivo su {url}")
    print("Lascia aperta questa finestra finche' usi la pagina. Chiudila per spegnere Job Radar.\n")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    llm.stop()
    if DIRTY.is_set():  # "Job Radar.html" deve mostrare gli ultimi preferiti anche a server spento
        build_page.main()


if __name__ == "__main__":
    main()
