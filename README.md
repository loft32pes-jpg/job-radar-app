# Job Radar

App web che ogni giorno cerca gli annunci di lavoro usciti in Europa nelle ultime 24 ore e tiene quelli adatti a ogni persona.

- `public/` e `api/`: l'app (Vercel). Ogni modifica caricata sul ramo `main` viene pubblicata da sola.
- `engine/`: il motore di ricerca, gira su GitHub Actions (`.github/workflows/ricerca.yml`) ogni mattina e su richiesta,
  nel repo pubblico del codice.
- I dati di ogni persona (profili, risultati, candidature) stanno in un repo privato separato e non entrano mai qui.
- `strumenti/`: comandi per chi amministra (utenti, segreti, prova in locale).

Regole: mai chiavi, CV o dati personali nel ramo `main`. I commit vanno firmati con l'email dell'account che possiede il progetto Vercel, altrimenti Vercel blocca la pubblicazione.
