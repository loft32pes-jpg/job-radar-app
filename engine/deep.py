"""Analisi approfondita di un abbinamento CV / annuncio con Claude (a richiesta, un annuncio alla volta).

Serve una chiave API Anthropic in config.json ("anthropic": {"api_key": "..."}). Invia a Claude il testo del CV
e il testo dell'annuncio: nient'altro. Senza chiave la funzione resta spenta e il resto di Job Radar non cambia.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

MODEL = "claude-opus-5-5"

SYSTEM = """Sei un selezionatore esperto di ruoli commerciali e tecnico-commerciali nel software B2B in Europa.
Valuti quanto un CV è adatto a un annuncio specifico, come farebbe chi fa la prima scrematura in azienda.

Scrivi in italiano, in modo diretto e concreto, per la candidata (dalle del tu). Basati solo su ciò che è scritto
nel CV e nell'annuncio: non inventare esperienze, numeri o requisiti. Se un'informazione manca, dillo.

Struttura la risposta così, con questi titoli:
Valutazione: un numero da 0 a 100 e una frase che lo motiva.
Punti forti: da 2 a 4 punti, ciascuno legato a una frase precisa dell'annuncio.
Punti deboli: da 2 a 4 punti, con il requisito dell'annuncio che non risulta coperto.
Cosa cambiare nel CV per questo annuncio: da 3 a 5 modifiche puntuali (quale frase riscrivere e come), solo se veritiere.
Conviene candidarsi?: sì, no o sì con riserva, in una frase.

Tieni conto che la candidata parla solo italiano e inglese e vuole uscire dal settore mobility."""


def analyze(api_key: str, cv_text: str, job: dict, job_text: str, rule_result: dict) -> dict:
    """Ritorna {"ok": True, "text": ...} oppure {"ok": False, "error": ...}. Non solleva eccezioni."""
    try:
        import anthropic
    except ImportError:
        return {"ok": False, "error": "Componente Claude non installato in questo pacchetto."}
    if not api_key:
        return {"ok": False, "error": "Chiave API Anthropic non inserita in config.json."}

    user = (
        f"ANNUNCIO\nRuolo: {job.get('title', '')}\nAzienda: {job.get('company', '')}\n"
        f"Luogo: {job.get('city', '')}, {job.get('country', '')}\nFonte: {job.get('source', '')}\n\n"
        f"Testo dell'annuncio:\n{job_text or '(testo non disponibile: valuta solo sul titolo e segnalalo)'}\n\n"
        f"CV DELLA CANDIDATA\n{cv_text}\n\n"
        f"Per riferimento, un confronto automatico per parole chiave ha dato {rule_result.get('score', '?')}/100 "
        f"(parole chiave mancanti: {', '.join(rule_result.get('missing', [])) or 'nessuna'}). "
        "Usalo come punto di partenza, non come verità: se il tuo giudizio è diverso, spiega perché."
    )
    client = anthropic.Anthropic(api_key=api_key)
    try:
        # streaming: l'analisi può richiedere un po' e così non si rischia il timeout della richiesta
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # se il modello declina la richiesta, l'API la rilancia sul modello di riserva consigliato
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            msg = stream.get_final_message()
    except anthropic.AuthenticationError:
        return {"ok": False, "error": "Chiave API Anthropic non valida."}
    except anthropic.PermissionDeniedError:
        return {"ok": False, "error": "La chiave API non ha i permessi per questo modello."}
    except anthropic.RateLimitError:
        return {"ok": False, "error": "Troppe richieste a Claude in questo momento: riprova tra un minuto."}
    except anthropic.BadRequestError as e:
        return {"ok": False, "error": f"Richiesta non accettata da Claude: {e.message}"}
    except anthropic.APIStatusError as e:
        return {"ok": False, "error": f"Errore del servizio Claude ({e.status_code}): riprova più tardi."}
    except anthropic.APIConnectionError:
        return {"ok": False, "error": "Connessione a Claude non riuscita: controlla Internet."}

    if msg.stop_reason == "refusal":
        return {"ok": False, "error": "Claude non ha potuto completare questa analisi."}
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    if not text:
        return {"ok": False, "error": "Risposta vuota da Claude: riprova."}
    return {"ok": True, "text": text, "model": msg.model,
            "truncated": msg.stop_reason == "max_tokens"}


REWRITE_SYSTEM = """Sei un consulente di carriera che sistema CV per ruoli commerciali e tecnico-commerciali nel software B2B.
Ricevi il CV diviso in blocchi numerati (ogni blocco è un pezzo di testo dentro un'impaginazione fissa) e, se c'è, un annuncio.

Regole, tutte obbligatorie:
- Non inventare nulla: niente esperienze, numeri, strumenti, certificazioni o lingue che il CV non contiene già. Puoi solo
  riformulare, riordinare le parole, rendere esplicito ciò che è già scritto e usare i termini dell'annuncio quando descrivono
  la stessa cosa che il CV dice con altre parole.
- Nomi, date, contatti, titoli di sezione e nomi di aziende restano identici: non includere quei blocchi nella risposta.
- Ogni blocco riscritto deve avere all'incirca la stessa lunghezza dell'originale (al massimo il 15% in più): lo spazio è fisso.
- Scrivi nella stessa lingua del CV. Frasi concrete, verbo d'azione all'inizio dei punti elenco, niente aggettivi vuoti.
- Cambia solo i blocchi dove la modifica migliora davvero il CV: di solito tra 3 e 10.

Rispondi SOLO con un oggetto JSON, senza testo prima o dopo, in questa forma:
{"segments": {"<numero blocco>": "<testo nuovo>", ...}, "notes": ["<cosa hai cambiato e perché, una frase per punto, massimo 5>"]}"""


def rewrite(api_key: str, segments: list, job: dict, job_text: str, missing: list, lang: str) -> dict:
    """Propone i blocchi del CV riscritti (per un annuncio, o in generale se job è None). Non solleva eccezioni."""
    import json
    import re
    try:
        import anthropic
    except ImportError:
        return {"ok": False, "error": "Componente Claude non installato in questo pacchetto."}
    if not api_key:
        return {"ok": False, "error": "Chiave API Anthropic non inserita in config.json."}
    blocks = "\n".join(f"[{s['id']}] {s['text']}" for s in segments)
    if job:
        goal = (f"OBIETTIVO: adattare il CV a questo annuncio.\nRuolo: {job.get('title', '')}\nAzienda: {job.get('company', '')}\n"
                f"Testo dell'annuncio:\n{job_text or '(testo non disponibile: basati sul titolo)'}\n\n"
                f"Parole chiave dell'annuncio che un confronto automatico non trova nel CV: {', '.join(missing) or 'nessuna'}. "
                "Inseriscile solo dove il CV descrive già quella cosa con altre parole.")
    else:
        goal = ("OBIETTIVO: migliorare il CV in generale per ruoli di technical sales, business development e vendita B2B di software: "
                "punti elenco più concreti, verbi d'azione, risultati in evidenza, termini standard del settore.")
    user = f"{goal}\n\nLingua del CV: {'italiano' if lang == 'it' else 'inglese'}\n\nBLOCCHI DEL CV\n{blocks}"
    client = anthropic.Anthropic(api_key=api_key)
    try:
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=REWRITE_SYSTEM,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            msg = stream.get_final_message()
    except anthropic.AuthenticationError:
        return {"ok": False, "error": "Chiave API Anthropic non valida."}
    except anthropic.RateLimitError:
        return {"ok": False, "error": "Troppe richieste a Claude in questo momento: riprova tra un minuto."}
    except anthropic.APIStatusError as e:
        return {"ok": False, "error": f"Errore del servizio Claude ({e.status_code}): riprova più tardi."}
    except anthropic.APIConnectionError:
        return {"ok": False, "error": "Connessione a Claude non riuscita: controlla Internet."}
    if msg.stop_reason == "refusal":
        return {"ok": False, "error": "Claude non ha potuto completare questa richiesta."}
    text = "".join(b.text for b in msg.content if b.type == "text")
    m = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(m.group(0)) if m else None
    except ValueError:
        data = None
    if not data or not isinstance(data.get("segments"), dict):
        return {"ok": False, "error": "Risposta di Claude non leggibile: riprova."}
    valid = {str(s["id"]) for s in segments}
    return {"ok": True, "segments": {k: str(v) for k, v in data["segments"].items() if k in valid and str(v).strip()},
            "notes": [str(n) for n in (data.get("notes") or [])][:5], "model": msg.model}

