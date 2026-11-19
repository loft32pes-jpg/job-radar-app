"""Aggiunge un fornitore di AI gratuito a Job Radar: chiede la chiave senza mostrarla, la prova, la salva nel config.json
locale e carica la configurazione cifrata su GitHub (ricerche) e su Vercel (app). La chiave non viene mai stampata.

  py strumenti/aggiungi_ai.py            mostra l'elenco e chiede quale aggiungere
  py strumenti/aggiungi_ai.py cerebras   aggiunge direttamente quel fornitore

Dopo, ogni mattina modelli.py prova tutti i modelli del fornitore e tiene quelli che rispondono con il piano gratuito.
"""
import getpass
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

CATALOGO = {
    "cerebras": ("Cerebras", "https://api.cerebras.ai/v1", "https://cloud.cerebras.ai  (API Keys)"),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1", "https://openrouter.ai/settings/keys  (si usano solo i modelli :free)"),
    "mistral": ("Mistral", "https://api.mistral.ai/v1", "https://console.mistral.ai/api-keys  (piano Experiment, gratuito)"),
    "nvidia": ("NVIDIA", "https://integrate.api.nvidia.com/v1", "https://build.nvidia.com  (Get API Key)"),
    "sambanova": ("SambaNova", "https://api.sambanova.ai/v1", "https://cloud.sambanova.ai/apis"),
    "groq2": ("Groq", "https://api.groq.com/openai/v1", "https://console.groq.com/keys  (sostituisce la chiave Groq attuale)"),
}


def load_env():
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip())


def vercel_token():
    """Accesso a Vercel dal file locale; se è scaduto lo chiede (senza mostrarlo) e lo salva al posto del vecchio."""
    f = REPO / (".vercel" + "-token")
    for attempt in range(2):
        tok = f.read_text(encoding="utf-8").strip() if f.exists() else ""
        try:
            with urlopen(Request("https://api.vercel.com/v2/user", headers={"Authorization": "Bearer " + tok, "User-Agent": "job-radar-admin"}), timeout=20):
                return tok
        except Exception:
            if attempt:
                return ""
            print("\nL'accesso a Vercel è scaduto. Crea un token nuovo su https://vercel.com/account/tokens")
            print("(nome: job-radar, ambito: il tuo team, scadenza: la più lunga possibile).")
            new = getpass.getpass("Incolla il token Vercel (non si vede) e premi Invio, oppure solo Invio per saltare: ").strip()
            if not new:
                return ""
            f.write_text(new, encoding="utf-8")
    return ""


def vercel_env(name, value):
    """Aggiorna una variabile segreta del progetto Vercel e ripubblica l'app."""
    tok = vercel_token()
    if not tok:
        return False
    proj = json.loads((REPO / ".vercel" / "project.json").read_text(encoding="utf-8"))
    team = f"teamId={proj['orgId']}" if str(proj.get("orgId", "")).startswith("team_") else ""
    h = {"Authorization": "Bearer " + tok, "Content-Type": "application/json", "User-Agent": "job-radar-admin"}
    body = {"key": name, "value": value, "type": "encrypted", "target": ["production"]}
    try:
        with urlopen(Request(f"https://api.vercel.com/v10/projects/{proj['projectId']}/env?upsert=true&{team}", data=json.dumps(body).encode(),
                             headers=h, method="POST"), timeout=30) as r:
            if r.status not in (200, 201):
                return False
    except Exception:
        return False
    return redeploy(tok)


def redeploy(token):
    """Ripubblica l'ultima versione di produzione (stesso codice di main) perché legga la configurazione nuova.
    Niente caricamenti dal computer: nella cartella ci sono file che non devono uscire."""
    proj = json.loads((REPO / ".vercel" / "project.json").read_text(encoding="utf-8"))
    team = f"teamId={proj['orgId']}" if str(proj.get("orgId", "")).startswith("team_") else ""
    h = {"Authorization": "Bearer " + token, "Content-Type": "application/json", "User-Agent": "job-radar-admin"}
    try:
        with urlopen(Request(f"https://api.vercel.com/v6/deployments?projectId={proj['projectId']}&target=production&state=READY&limit=1&{team}",
                             headers=h), timeout=30) as r:
            last = json.load(r)["deployments"][0]
        body = {"name": proj.get("projectName") or "job-radar", "deploymentId": last["uid"], "target": "production"}
        with urlopen(Request(f"https://api.vercel.com/v13/deployments?forceNew=1&{team}", data=json.dumps(body).encode(), headers=h,
                             method="POST"), timeout=60) as r:
            return r.status in (200, 201)
    except Exception:
        return False


def main():
    load_env()
    cfg_path = Path(os.environ.get("JR_LOCAL_CONFIG") or REPO.parent / "JobRadar" / "config.json")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    ai = cfg.setdefault("ai", {})
    have = {p.get("name") for p in [ai] + list(ai.get("extra") or []) if p.get("api_key")}
    pick = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if pick not in CATALOGO:
        print("Fornitori gratuiti che Job Radar sa usare:\n")
        for k, (name, _url, where) in CATALOGO.items():
            print(f"  {k:<11} {name:<11} {'(già attivo)' if name in have else ''}\n              chiave da: {where}")
        pick = input("\nQuale aggiungi? Scrivi il nome a sinistra: ").strip().lower()
        if pick not in CATALOGO:
            print("Nome non riconosciuto.")
            return 1
    name, url, where = CATALOGO[pick]
    print(f"\n{name}: crea la chiave su {where}")
    key = getpass.getpass(f"Incolla la chiave {name} (non si vede mentre la incolli) e premi Invio: ").strip()
    if len(key) < 10:
        print("Chiave vuota o troppo corta: niente da fare.")
        return 1
    try:
        req = Request(url + "/models", headers={"Authorization": "Bearer " + key, "User-Agent": "JobRadar/1.0"})
        with urlopen(req, timeout=30) as r:
            n = len(json.load(r).get("data", []))
        print(f"Chiave valida: {name} offre {n} modelli.")
    except Exception as e:
        print(f"La chiave non funziona ({getattr(e, 'code', type(e).__name__)}). Controlla di averla copiata tutta.")
        return 1
    if pick == "groq2":
        ai["api_key"] = key
    else:
        extra = [p for p in ai.get("extra") or [] if p.get("name") != name]
        extra.append({"name": name, "base_url": url, "api_key": key})
        ai["extra"] = extra
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Salvata nel config.json locale.")
    one_line = json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))  # su una riga: GitHub maschera i segreti riga per riga
    # GitHub (le ricerche)
    import github
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(one_line)
        tmp = f.name
    try:
        sys.argv = ["github.py", "segreto", "JR_CONFIG", tmp]
        github.main()
    finally:
        os.unlink(tmp)
    # Vercel (l'app: candidature e colloqui)
    ok = vercel_env("JR_CONFIG", one_line)
    print("Vercel: configurazione caricata e app ripubblicata" if ok else "Vercel: NON aggiornata (la ricerca usa comunque la chiave nuova)")
    print(f"\nFatto. Da domattina la scelta automatica prova tutti i modelli gratuiti di {name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
