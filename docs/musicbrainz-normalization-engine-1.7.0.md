# MusicBrainz Normalization Engine — v1.7.0

## Obiettivo

Introdurre una fase esplicita tra revisione editoriale e popolamento del catalogo. Il motore legge i `raw_records` MusicBrainz, richiede una decisione editoriale `APPROVED` come ultima decisione e normalizza in modo controllato artisti, release group e release.

## Endpoint

### GET `/api/v1/ingestion/musicbrainz/normalization/queue`

Restituisce i record `PENDING` con esito di eleggibilità, decisione editoriale e dipendenze. È read-only.

### POST `/api/v1/ingestion/musicbrainz/normalization/execute`

Body:

```json
{
  "raw_record_ids": ["<raw-record-uuid>"],
  "dry_run": true
}
```

`dry_run` è `true` per default. Con `true` il motore restituisce blocchi e dipendenze senza scrivere. Con `false` esegue la normalizzazione per record, in savepoint isolati, e registra l'esito nella tabella audit.

## Regole

- Solo raw record MusicBrainz con ultima decisione editoriale `APPROVED`.
- Solo record in stato `PENDING`.
- Un MBID già collegato non viene duplicato.
- Un artista con corrispondenza nominale locale viene bloccato: occorre usare il workflow `LINKED`.
- Una release richiede il release group già collegato e tutti gli artisti dei crediti già collegati.
- Le label vengono collegate solo in presenza di un match locale univoco; non vengono create automaticamente.
- I tag MusicBrainz vengono associati soltanto a generi locali esistenti.
- I payload raw non vengono modificati; cambia solo lo stato di lavorazione e `processed_at`.
- Ogni entità creata produce una riga in `musicbrainz_normalization_audit`.
- Nessuna deduplicazione, fusione o sovrascrittura automatica.

## Dipendenze

Ordine raccomandato:
1. artisti;
2. release group;
3. release.

Per una release, il release group e gli artisti dei crediti devono essere già collegati tramite `external_identifiers`.

## Migrazione

La revisione Alembic `0004_musicbrainz_normalization_audit` segue `0003_musicbrainz_review_workflow` e crea esclusivamente la tabella di audit e i relativi indici.

Prima dell'upgrade verificare `alembic current`. Non usare `docker compose down -v`.

## Limiti noti

- Il motore crea release group senza una relazione diretta ai crediti artista, perché lo schema corrente non espone una tabella `release_group_artists`.
- Le label non vengono create: il collegamento è effettuato soltanto quando il nome corrisponde a una singola label locale.
- I crediti release vengono importati con ruolo `PRIMARY`; il payload originale conserva la struttura dettagliata MusicBrainz.
- La tabella audit registra gli ID target come UUID senza FK polimorfica, perché il target può appartenere a tre tabelle differenti.
