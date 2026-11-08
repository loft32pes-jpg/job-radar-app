"""Copia il codice (ramo main) nel repo pubblico della ricerca, come un nuovo commit senza la storia del repo privato.

  py strumenti/pubblica.py "messaggio"

Nel repo pubblico arriva solo l'albero dei file di main (già pulito: niente chiavi né dati personali, vedi .gitignore),
firmato con l'indirizzo anonimo di GitHub. La storia del repo privato non viene mai spinta lì.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PUBLIC = "https://github.com/loft32pes-jpg/job-radar-app.git"
WHO = {"GIT_AUTHOR_NAME": "Job Radar", "GIT_AUTHOR_EMAIL": "loft32pes-jpg@users.noreply.github.com",
       "GIT_COMMITTER_NAME": "Job Radar", "GIT_COMMITTER_EMAIL": "loft32pes-jpg@users.noreply.github.com"}


def git(*args, env=None):
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, env={**os.environ, **(env or {})})
    if r.returncode:
        raise SystemExit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def main():
    msg = sys.argv[1] if len(sys.argv) > 1 else "Aggiornamento"
    if git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("Ci sono modifiche non salvate: prima fai commit su main.")
    tree = git("rev-parse", "main^{tree}")
    remote = subprocess.run(["git", "ls-remote", PUBLIC, "refs/heads/main"], cwd=REPO, capture_output=True, text=True).stdout.split()
    parent = []
    if remote:
        git("fetch", "-q", PUBLIC, "main")
        if git("rev-parse", "FETCH_HEAD^{tree}") == tree:
            print("Il repo pubblico è già aggiornato")
            return
        parent = ["-p", "FETCH_HEAD"]
    commit = git("commit-tree", tree, *parent, "-m", msg, env=WHO)
    git("push", "-q", PUBLIC, f"{commit}:refs/heads/main")
    print(f"Pubblicato: {commit[:7]} su {PUBLIC}")


if __name__ == "__main__":
    main()
