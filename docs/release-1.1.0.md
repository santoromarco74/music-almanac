# Release notes — Music Almanac 1.1.0

## Funzionalità aggiunte
1. Workflow editoriale con schede, relazioni, tag, scoring e transizioni di stato protette.
2. Ricerca unificata su artisti, release ed eventi.
3. Calendario filtrabile per anno, mese, giorno e tipologia evento.
4. Export JSON/CSV per artisti, generi, release, eventi, premi e schede editoriali.
5. Smoke test PowerShell e documentazione operativa.

## Componenti preesistenti preservati
Le API Artists, Genres, Memberships, MusicBrainz, Catalog, Events, Provenance e Awards restano registrate. La pipeline MusicBrainz continua a conservare il payload grezzo e a richiedere normalizzazione/approvazione prima della scrittura canonica; questa release non modifica il comportamento di ingestione già collaudato. Lo schema SQL e i volumi PostgreSQL non vengono modificati.

## Limiti espliciti
- Non sono implementati vincitori/candidature dei premi: il modello corrente non contiene tabelle nomination/recipient.
- Export sincrono con limite massimo di 20.000 record.
- La dashboard esistente non viene riscritta né alterata: le nuove API sono disponibili per l'integrazione del client.
- La patch è stata verificata sintatticamente e l'archivio è stato controllato; il runtime va verificato nel Docker locale, non accessibile in questa sessione.
