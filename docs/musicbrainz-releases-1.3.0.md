# Music Almanac API v1.3.0 — MusicBrainz Releases ingestion

## Obiettivo

Aggiunge l'acquisizione e la normalizzazione delle singole edizioni discografiche MusicBrainz (`release`). Una `release` è distinta dal `release-group`: il gruppo rappresenta l'opera/aggregato discografico, mentre la release rappresenta una specifica edizione, eventualmente territoriale o temporale.

## Endpoint

Tutti gli endpoint sono sotto `/api/v1/ingestion/musicbrainz/releases`.

- `POST /search?q=...&limit=...`: ricerca release, persiste i risultati in `raw_records`.
- `POST /lookup/{mbid}`: acquisisce il dettaglio release con artisti, etichette, registrazioni e release group.
- `GET /preview/{mbid}`: mostra candidato, data con precisione, paese, barcode, formati, cataloghi, label, release group e artisti locali riconosciuti.
- `POST /normalize/{mbid}`: crea la release canonica o collega un record esistente.

## Normalizzazione

Body di esempio:

```json
{
  "release_group_id": "UUID-DEL-RELEASE-GROUP",
  "label_id": null,
  "status": "TO_VERIFY"
}
```

`release_group_id` è facoltativo se il MBID del release group è già collegato a un record locale tramite `MUSICBRAINZ_RELEASE_GROUP`. Se manca il collegamento, è obbligatorio indicarlo esplicitamente. La normalizzazione non crea automaticamente release group.

Per collegare una release già presente, usare `existing_release_id`; in questo caso non vengono sovrascritti i dati del record canonico.

`label_id` è facoltativo. Le etichette non vengono create automaticamente: viene associata una label locale soltanto quando la corrispondenza per nome e paese è univoca. In caso di omonimia ambigua, la preview espone i candidati e la normalizzazione restituisce HTTP 409.

Gli artisti vengono associati esclusivamente se i rispettivi MBID sono già collegati a record locali tramite `MUSICBRAINZ_ARTIST`. I crediti non risolti restano nel payload grezzo. La chiave primaria di `release_artists` non permette duplicati dello stesso artista/ruolo: viene conservata la prima occorrenza risolta.

## Date e provenienza

- `YYYY` → `YEAR`
- `YYYY-MM` → `MONTH`
- `YYYY-MM-DD` → `DAY`

La data completa è valorizzata in `release_date` soltanto con precisione `DAY`. La normalizzazione crea anche una riga `date_assertions` con stato `PRELIMINARY`, senza sostituire il modello di asserzioni con una dichiarazione di certezza. La fonte viene collegata alla release tramite `entity_sources`, e l'MBID tramite `external_identifiers` con namespace `MUSICBRAINZ_RELEASE`.

Il payload integrale resta in `raw_records`, con hash SHA-256 e stato di elaborazione.

## Vincoli

- Nessuna modifica allo schema SQL e nessuna migrazione.
- Nessuna creazione automatica di label o release group.
- Nessun aggiornamento distruttivo quando si collega un record esistente.
- Le release non vengono pubblicate automaticamente né marcate `VERIFIED`.
- Rate limit applicativo serializzato: almeno 1,05 secondi tra richieste MusicBrainz nello stesso processo.
- Configurare `MUSICBRAINZ_USER_AGENT` con identificazione applicazione, versione e contatto.

## Verifica

Dopo aver installato la patch:

1. `GET /health`
2. `GET /api/v1` → versione `1.3.0`
3. `GET /docs` → gruppo `ingestion` e quattro endpoint release visibili.
4. Eseguire `tests/smoke_releases.ps1`.

Lo smoke test verifica registrazione OpenAPI; non esegue richieste live a MusicBrainz né scrive record nel database.
