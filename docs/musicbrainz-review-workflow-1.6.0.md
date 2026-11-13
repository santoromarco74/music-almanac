# MusicBrainz Review Workflow — v1.6.0

## Obiettivo

Estendere la review queue v1.5.0 con decisioni editoriali esplicite, collegamento manuale alle entità canoniche e storico append-only. I payload originali in `raw_records` non vengono modificati o cancellati.

## Migrazione

La revisione Alembic `0003_musicbrainz_review_workflow` dipende da `0002_artist_aliases` e crea `musicbrainz_review_decisions`.

Prima di eseguire la migrazione, verificare lo stato:

```powershell
docker compose exec api alembic current
```

Se il database è già stato marcato con la baseline e la migrazione `0002_artist_aliases` è applicata, eseguire:

```powershell
docker compose exec api alembic upgrade head
```

Non eseguire `docker compose down -v`. La migrazione non modifica o elimina i dati preesistenti.

## API

Tutti gli endpoint sono sotto `/api/v1/ingestion/musicbrainz/review`.

- `GET /decisions`: storico globale, filtrabile per `action` e `raw_record_id`.
- `GET /records/{raw_record_id}`: payload raw, collegamento esterno corrente, ultima decisione e storico.
- `GET /records/{raw_record_id}/decisions`: storico di un singolo record.
- `POST /records/{raw_record_id}/decision`: registra una decisione.

### Decisione APPROVED

```json
{
  "action": "APPROVED",
  "reason": "Payload coerente con la fonte primaria.",
  "reviewer": "editor-1"
}
```

L'approvazione registra l'esito della revisione; non esegue la normalizzazione e non cambia `raw_records.processing_status`.

### Decisione REJECTED

```json
{
  "action": "REJECTED",
  "reason": "Record non pertinente al catalogo editoriale.",
  "reviewer": "editor-1"
}
```

La motivazione è obbligatoria. Il payload rimane conservato.

### Collegamento LINKED

```json
{
  "action": "LINKED",
  "target_entity_id": "UUID_ENTITA_CANONICA",
  "reason": "Identità verificata tramite confronto dei metadati.",
  "reviewer": "editor-1"
}
```

Il tipo di entità viene dedotto dal payload raw. L'API verifica che la destinazione esista e che il MBID non sia già associato a un'altra entità. In caso di collegamento valido crea l'identificatore esterno nel namespace MusicBrainz corrispondente. Non crea, fonde o modifica entità canoniche.

## Audit e sicurezza

- Le decisioni sono append-only: ogni revisione genera una nuova riga.
- Non sono esposti endpoint di modifica o cancellazione delle decisioni.
- `reviewer` è un'etichetta dichiarata dal chiamante, non un'identità autenticata: il progetto non dispone ancora di un sistema di autenticazione/autorizzazione.
- Le decisioni APPROVED/REJECTED non cambiano lo stato di elaborazione del raw record.
- LINKED modifica esclusivamente `external_identifiers` e registra la decisione nella stessa transazione.
- Nessuna deduplicazione automatica, normalizzazione automatica o modifica del payload raw.

## Smoke test

Dopo aver applicato la patch e la migrazione:

```powershell
docker compose up -d --build api
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\smoke_review_1_6.ps1
```

Lo smoke test verifica la registrazione delle route, la consultazione read-only e la gestione dei record inesistenti. Il test end-to-end di APPROVED/REJECTED/LINKED richiede un raw record MusicBrainz reale e una corrispondente entità canonica di destinazione.
