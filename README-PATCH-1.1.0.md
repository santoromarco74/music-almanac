# Music Almanac v1.1.0 — patch cumulativa

Questa patch aggiunge workflow editoriale, ricerca trasversale, calendario ed export. Riutilizza le tabelle editoriali già presenti nello schema SQL e non esegue migrazioni né reset del database.

## Contenuto
- `backend/app/api/routes/editorial.py`: schede, associazioni ad artisti/release/eventi, tag, scoring e transizioni di stato.
- `backend/app/api/routes/discovery.py`: ricerca, calendario, export JSON/CSV.
- `backend/app/main.py`: registrazione dei nuovi router e versione API 1.1.0.
- `docs/`: specifica API, regole editoriali, installazione e collaudo.
- `tests/`: smoke test di integrazione eseguibili contro API già avviata.

## Applicazione su Windows / PowerShell
1. Arrestare solo il container API, senza eliminare volumi: `docker compose stop api` (se il servizio si chiama diversamente, verificare `docker compose ps`).
2. Estrarre lo ZIP nella root del repository, mantenendo la struttura delle cartelle e sovrascrivendo `backend/app/main.py`.
3. Ricostruire e avviare solo l'API: `docker compose up -d --build api`.
4. Verificare `Invoke-RestMethod http://localhost:8000/health` e `http://localhost:8000/api/v1`.

Non eseguire `docker compose down -v`. Non è necessario modificare `database/init/001_schema.sql` né applicare migrazioni.

## Test
Eseguire i comandi in `docs/patch-1.1.0-validation.md`. La patch è stata sottoposta a controllo sintattico Python e controllo ZIP; il test runtime richiede l'ambiente Docker dell'utente e deve essere eseguito localmente.
