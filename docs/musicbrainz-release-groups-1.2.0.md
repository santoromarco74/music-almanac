# Music Almanac v1.2.0 — MusicBrainz Release Groups

## Obiettivo

Aggiunge l'acquisizione controllata dei release group MusicBrainz. La funzionalità riusa `sources`, `ingestion_runs`, `raw_records`, `release_groups` ed `external_identifiers`: non introduce tabelle né migrazioni.

## Endpoint

Tutti gli endpoint sono sotto `/api/v1/ingestion/musicbrainz/release-groups`.

| Metodo | Endpoint | Funzione |
|---|---|---|
| POST | `/search?q={query}&limit=10` | Cerca release group e conserva ogni risultato in `raw_records` |
| POST | `/lookup/{mbid}` | Acquisisce il dettaglio, inclusi artist-credit e release |
| GET | `/preview/{mbid}` | Mostra candidato, omonimie, crediti e stato del collegamento |
| POST | `/normalize/{mbid}` | Crea il release group canonico o collega un record esistente |

### Flusso consigliato

1. Eseguire `POST /search?q=The%20Dark%20Side%20of%20the%20Moon`.
2. Selezionare un MBID dai risultati.
3. Eseguire `POST /lookup/{mbid}` per ottenere il dettaglio completo.
4. Eseguire `GET /preview/{mbid}` e verificare titolo, tipo, anno e corrispondenze locali.
5. Eseguire `POST /normalize/{mbid}` con `{}` per creare un nuovo record, oppure con `{"existing_release_group_id":"UUID"}` per collegare un record esistente.

## Regole di integrità

- Il payload originale viene conservato in `raw_records` con hash SHA-256.
- La ricerca non crea record canonici.
- La normalizzazione usa namespace `MUSICBRAINZ_RELEASE_GROUP` in `external_identifiers`.
- Un titolo già presente produce HTTP 409; è necessaria una scelta esplicita del record locale.
- Un MBID già collegato restituisce `ALREADY_LINKED` senza creare duplicati.
- Le edizioni MusicBrainz (`releases`) non vengono create automaticamente.
- I crediti artista sono esposti in preview. Non vengono inseriti in `release_artists` perché tale tabella richiede un `release_id`, non un `release_group_id`.
- Gli artisti locali sono riconosciuti solo se il loro MBID è già presente in `external_identifiers` con namespace `MUSICBRAINZ_ARTIST`.
- La precisione temporale del release group è limitata all'anno, coerentemente con `first_release_year`.
- Le richieste sono serializzate nel processo API con intervallo minimo di 1,05 secondi. In deployment multi-worker il limite va coordinato a livello condiviso.

## Configurazione

Impostare `MUSICBRAINZ_USER_AGENT` nel file `.env` con nome applicazione, versione e contatto verificabile. Esempio:

`MUSICBRAINZ_USER_AGENT=MusicAlmanac/1.2.0 ( mailto:contatto@example.org )`

Sostituire l'indirizzo di esempio con un contatto effettivo.

## Applicazione

Copiare i file della patch nelle rispettive directory della root del repository, sovrascrivendo `backend/app/main.py`, quindi eseguire:

```powershell
docker compose up -d --build api
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/v1
```

Verificare la presenza dei quattro endpoint in `http://localhost:8000/docs`.

Non eseguire `docker compose down -v`: il comando eliminerebbe il volume persistente PostgreSQL.

## Rollback applicativo

Per disattivare il modulo, ripristinare `backend/app/main.py` dalla versione precedente e rimuovere `backend/app/api/routes/musicbrainz_release_groups.py`, quindi ricostruire il servizio API. Nessuna modifica allo schema DB è prevista.
