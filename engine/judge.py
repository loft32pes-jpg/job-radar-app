"""Giudice AI: legge ogni annuncio candidato e dice quanto è adatto alla persona (0-100) e perché.

Serve a due cose: togliere gli annunci che hanno il titolo giusto ma sono un altro mestiere, e far salire quelli davvero
alla portata dell'utente anche se il titolo non era tra quelli previsti. Senza AI disponibile non fa nulla: restano le regole.
"""
import json
import os
import itertools
import queue
import re
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(__file__))
from common import ROOT, read_json  # noqa: E402

SYSTEM = """Valuti annunci di lavoro per una persona precisa. Sei un giudice MEDIO: né generoso né severo.

PRIMA VENGONO LE SCELTE DELLA PERSONA, poi il tuo giudizio:
1. Il riferimento è il lavoro che DESIDERA, non quello che ha fatto finora. Se vuole cambiare mestiere, chiediti se le competenze
   che ha si trasferiscono al lavoro desiderato: se sì il voto è alto, anche se non ha mai avuto quel titolo. Non abbassare il
   voto perché "finora ha fatto altro" e non premiare gli annunci del mestiere da cui vuole uscire.
2. Settori ESCLUSI: se l'azienda o il ruolo appartengono a un settore che ha escluso, metti "x": true. L'annuncio verrà tolto
   anche se per il resto sarebbe perfetto. Vale per tutto il settore (es. escluso il bancario: banche, servizi per le banche).
3. Settori PREFERITI: se l'azienda o il ruolo sono in un suo settore preferito, metti "p": true (avrà punti in più).

Poi dai "fit" da 0 a 100, usando tutta la scala:
- 80-100: è il lavoro che desidera, o un suo equivalente, ed è alla sua portata;
- 60-79: c'entra bene: ruolo vicino a quello desiderato, che può svolgere con le competenze che ha;
- 40-59: c'entra mediamente: stesso tipo di lavoro in un ambito diverso, oppure un requisito in dubbio (un po' più di
  esperienza, una competenza da completare). Questi annunci RESTANO in elenco: sono opportunità;
- 20-39: c'entra poco: il legame con ciò che desidera e sa fare è debole;
- 0-19: non c'entra niente: è un altro mestiere con un titolo simile, oppure chiede competenze tecniche o anni che non ha.
Non alzare il voto solo perché il titolo è uguale: conta cosa si fa davvero nel ruolo.
Se ricevi gli annunci che la persona ha SALVATO e quelli che ha SCARTATO, sono le sue scelte reali e valgono più delle tue
ipotesi: un annuncio dello stesso tipo di quelli salvati vale almeno 60, uno dello stesso tipo di quelli scartati al massimo 39.
Quando uno scarto ha un motivo ("perché: ..."), applicalo a tutti gli annunci simili per quel motivo (stesso settore, stesso
livello, agenzia per il lavoro, stessa zona...), non solo a quell'annuncio.
Conta anche il LIVELLO del lavoro che DESIDERA: un annuncio di un livello molto diverso (molto più semplice o molto più
alto di quello che cerca) è un altro lavoro e vale al massimo 35, anche se contiene le stesse parole ("vendita", "clienti").
Di ogni annuncio ricevi l'inizio, le mansioni e i requisiti ("[…]" segna un taglio). Leggi i requisiti: anni richiesti, lingue,
titoli di studio e competenze obbligatorie che la persona non ha abbassano il voto; se c'è solo il titolo giudica con prudenza.
"why": una frase in italiano di al massimo 14 parole, rivolta alla persona (tu), che spiega il voto in modo concreto.
Rispondi SOLO con JSON: {"r": [{"i": <numero annuncio>, "fit": <0-100>, "x": <true|false>, "p": <true|false>, "why": "<frase>"}, ...]}
con una voce per ogni annuncio."""
BATCH, SNIPPET, HEAD = 10, 900, 220  # 900 caratteri per annuncio: inizio + mansioni + requisiti


def _models():
    """Tutti i modelli utilizzabili, di tutti i fornitori in config.json (sezione "ai" e la sua lista "extra"):
    [((indirizzo, chiave), modello)]. Ogni modello ha la sua quota gratuita: più ce ne sono, più annunci al minuto."""
    ai = read_json(ROOT / "config.json", {}).get("ai", {})
    out = []
    for p in [ai] + list(ai.get("extra") or []):
        if not (p.get("base_url") and p.get("api_key")):
            continue
        url = p["base_url"].rstrip("/")
        url += "" if url.endswith("/chat/completions") else "/chat/completions"
        import ai as ai_mod
        for m in p.get("judge_models") or p.get("models") or ai_mod.models_of(p):
            out.append(((url, p["api_key"]), m))
    return bool(out), out


def _call(conn, model, user):
    url, key = conn
    body = {"model": model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"}, "temperature": 0.1}
    req = Request(url, data=json.dumps(body).encode("utf-8"),
                  headers={"Content-Type": "application/json", "Authorization": "Bearer " + key, "User-Agent": "JobRadar/1.0"})
    with urlopen(req, timeout=60) as r:
        return json.loads(json.load(r)["choices"][0]["message"]["content"])


def _person(profile):
    a = profile.get("answers") or {}
    return (f"LA PERSONA\nLAVORO CHE DESIDERA: {a.get('desired', '')[:900]}\nLavoro attuale o più recente: {a.get('current') or 'non indicato'}\n"
            f"SETTORI PREFERITI: {a.get('prefer') or 'nessuna preferenza'}\nSETTORI O LAVORI ESCLUSI: {a.get('avoid') or 'nessuno'}\nAnni di esperienza: {a.get('years', '?')}\nStudi: {a.get('education') or 'non indicati'}\n"
            f"Punti di forza: {a.get('strengths') or 'non indicati'}\nCompetenze: {', '.join((profile.get('skills') or [])[:20])}\n"
            f"Lingue in cui può lavorare: {', '.join(a.get('languages') or ['it', 'en'])} "
            f"(un annuncio scritto in un'altra lingua, che quindi la richiede, vale al massimo 45)\n"
            f"Ruoli individuati per lei/lui: {', '.join(c['name'] for c in profile['clusters'] if c.get('on', True))}"
            + _choices(profile))


def _choices(profile):
    """Le scelte reali della persona nella bacheca: il giudice le usa come esempi."""
    lr = profile.get("learned") or {}
    out = ""
    if lr.get("pos"):
        out += "\nANNUNCI CHE HA SALVATO O A CUI SI È CANDIDATA (le piacciono): " + "; ".join(f"{x[0]} ({x[1]})" for x in lr["pos"][-15:])
    if lr.get("neg"):
        out += "\nANNUNCI CHE HA SCARTATO: " + "; ".join(
            f"{x[0]} ({x[1]})" + (f" perché: {x[2]}" if len(x) > 2 and x[2] else "") for x in lr["neg"][-20:])
    return out


NEEDS = re.compile(r"requirements?|qualifications?|what you.ll (?:need|bring)|what we.re looking for|who you are|your profile|"
                   r"you have|about you|must have|skills|experience (?:in|with)|years of|requisiti|profilo|competenze|cosa cerchiamo|"
                   r"esperienza|anforderungen|dein profil|ihr profil|profil recherché|compétences|requisitos|perfil|wat wij vragen", re.I)
TASKS = re.compile(r"responsibilit|what you.ll do|your role|the role|you will|your tasks|key duties|day.to.day|attività|"
                   r"responsabilità|cosa farai|il ruolo|aufgaben|missions|responsabilidades|funciones", re.I)


def _snippet(text, SNIPPET=SNIPPET):
    """Le parti dell'annuncio che servono per giudicare: l'inizio, cosa si fa nel ruolo e cosa viene richiesto
    (di solito l'inizio è la presentazione dell'azienda, i requisiti stanno in fondo)."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= SNIPPET:
        return text or "(testo non disponibile)"
    head = text[:HEAD]
    need = NEEDS.search(text, HEAD)
    task = TASKS.search(text, HEAD)
    room = SNIPPET - HEAD
    if need and task and abs(need.start() - task.start()) > room // 2:
        a, b = sorted((task.start(), need.start()))
        half = room // 2
        return f"{head} […] {text[a:a + half]} […] {text[b:b + half]}"
    at = (task or need).start() if (task or need) else HEAD
    return f"{head} […] {text[at:at + room]}" if at > HEAD else text[:SNIPPET]


def _ads(batch, size=SNIPPET):
    return "\n".join(f"[{k}] {j['title']} | {j['company']} | {j.get('country', '')} — {_snippet(text, size)}"
                     for k, (j, text) in enumerate(batch))


def _votes(data, n):
    """Risposte valide dell'AI: [(posizione nel gruppo, {"ai_fit", "ai_why", "ai_x", "ai_p"})]."""
    out = []
    for r in (data or {}).get("r") or []:
        try:
            i = int(r["i"])
            if 0 <= i < n:
                out.append((i, {"ai_fit": max(0, min(100, int(r["fit"]))), "ai_why": str(r.get("why") or "")[:140],
                                "ai_x": bool(r.get("x")), "ai_p": bool(r.get("p"))}))
        except (KeyError, ValueError, TypeError):
            continue
    return out


class Live:
    """Giudice che lavora mentre la ricerca è ancora in corso: riceve gli annunci man mano e li valuta a gruppi.
    Un lavoratore per modello, in parallelo: ogni modello ha il suo tetto di parole al minuto, così si sommano."""

    def __init__(self, profile):
        self.conn, self.models = _models()
        self.on = bool(self.conn and self.models and profile)
        self.results, self.sent, self.tries, self.q = {}, set(), {}, queue.PriorityQueue()
        self.n = itertools.count()
        self.closing, self.deadline, self.busy = False, None, 0
        self.collect, self.tally = threading.Lock(), threading.Lock()
        self.threads, self.out = [], []  # out: modelli che hanno finito la quota gratuita di oggi
        if self.on:
            self.person = _person(profile)
            self.threads = [threading.Thread(target=self._work, args=(m,), daemon=True) for m in self.models]
            for t in self.threads:
                t.start()

    def submit(self, key, job, text, prio=5):
        """job: dizionario con title, company, country. Ogni chiave viene valutata una volta sola.
        prio: più basso = valutato prima (la città principale della persona viene prima di tutto)."""
        if self.on and not self.closing and key not in self.sent:
            self.sent.add(key)
            self.q.put((prio, next(self.n), (key, job, text)))

    def _late(self):
        return bool(self.deadline and time.time() > self.deadline)

    def _work(self, model):
        fails = 0
        while not self._late():
            batch, first = [], 0.0
            # con pochi modelli ancora in quota si risparmia: gruppi più grandi e meno testo per annuncio
            active = len(self.models) - len(self.out)
            limit, size = (BATCH, SNIPPET) if active >= 3 else (12, 600) if active == 2 else (14, 380)
            with self.collect:  # un gruppo alla volta si riempie, così non restano tre gruppi a metà
                while len(batch) < limit:
                    try:
                        batch.append(self.q.get(timeout=1)[2])
                        first = first or time.time()
                    except queue.Empty:
                        if self.closing or (batch and time.time() - first > 10):
                            break  # gruppo incompleto: non si aspetta oltre
                with self.tally:
                    self.busy += bool(batch)
            if not batch:
                if self.closing and not self.busy:
                    return  # coda vuota e nessun collega che potrebbe rimettere in coda qualcosa
                continue
            data = None
            for _try in range(3):
                if self._late():
                    break
                try:
                    data = _call(model[0], model[1], self.person + "\n\nANNUNCI\n" + _ads([(j, t) for _k, j, t in batch], size))
                    break
                except HTTPError as e:  # tetto al minuto raggiunto: questo modello aspetta, gli altri continuano
                    wait = float(e.headers.get("retry-after") or 8) if e.code == 429 else 4
                    if wait > 90:  # tetto GIORNALIERO del modello esaurito: per oggi esce, il gruppo passa agli altri
                        self.out.append(model)
                        if len(self.out) < len(self.models):
                            for item in batch:
                                self.q.put((0, next(self.n), item))
                        with self.tally:
                            self.busy -= 1
                        return
                    time.sleep(min(30, wait + 0.5))
                except Exception:
                    time.sleep(3)
            fails = 0 if data else fails + 1
            if fails >= 2:  # modello che non risponde (sovraccarico): esce e lascia il gruppo agli altri
                self.out.append(model)
                if len(self.out) < len(self.models):
                    for item in batch:
                        self.q.put((0, next(self.n), item))
                with self.tally:
                    self.busy -= 1
                return
            voted = set()
            for i, vote in _votes(data, len(batch)):
                self.results[batch[i][0]] = vote
                voted.add(i)
            for i, item in enumerate(batch):  # chi è rimasto senza risposta torna in coda una volta
                if i not in voted and not self.tries.get(item[0]):
                    self.tries[item[0]] = 1
                    self.q.put((0, next(self.n), item))
            with self.tally:
                self.busy -= 1

    def close(self, budget_s=45):
        """Aspetta che finisca la coda (al massimo budget_s secondi) e ritorna {chiave: voto}."""
        if not self.on:
            return {}
        self.closing, self.deadline = True, time.time() + budget_s
        for t in self.threads:
            t.join(max(1, self.deadline + 62 - time.time()))
        return dict(self.results)


def run(profile, items, log=None, budget_s=200):
    """items: [(job, testo)]. Scrive job["ai_fit"] e job["ai_why"] dove riesce. Ritorna quanti annunci ha valutato."""
    log = log or (lambda m: None)
    live = Live(profile)
    if not live.on or not items:
        return 0
    t0 = time.time()
    for n, (j, text) in enumerate(items):
        live.submit(n, j, text, j.get("_prio", 5))
    votes = live.close(budget_s)
    for n, vote in votes.items():
        items[n][0].update(vote)
    late = "" if len(votes) == len(items) else " (tempo scaduto: gli altri restano con il punteggio a regole)"
    if live.out:
        late += f". Quota gratuita di oggi finita per {len(live.out)} modelli AI su {len(live.models)}: il giudizio è più lento"
    log(f"  Giudizio AI: {len(votes)} annunci valutati su {len(items)} in {round(time.time() - t0)} secondi{late}")
    return len(votes)
