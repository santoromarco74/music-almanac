# Architettura

## Principi
1. PostgreSQL è la fonte di verità applicativa.
2. Il frontend non accede direttamente al database.
3. Ogni dato importato conserva provenienza e tracciabilità.
4. Le date incomplete o discordanti non vengono forzate a una data artificiale.
5. La rilevanza editoriale è distinta dall'affidabilità documentale.
6. Le edizioni discografiche sono distinte dall'opera discografica concettuale.

## Flusso dati
Fonti -> Raw records -> normalizzazione -> deduplicazione -> verifica -> entità PostgreSQL -> ricerca ricorrenze -> scoring -> dashboard -> selezione editoriale -> export Astro.

## Precisione temporale
Le colonne `*_year`, `*_month`, `*_day` e `date_precision` descrivono la precisione disponibile. `date_assertions` conserva le affermazioni delle singole fonti. I campi `event_date` e `release_date` sono date canoniche utilizzabili solo quando il giorno è noto.

## Verifica
- VERIFIED: fonte primaria/istituzionale adeguata.
- CONFIRMED: almeno due fonti indipendenti concordanti.
- PRELIMINARY / TO_VERIFY: riscontro incompleto.
- UNCERTAIN: fonti discordanti o evidenza insufficiente.

## Nota di progettazione
La prima versione usa tabelle di collegamento esplicite per le relazioni editoriali e documentali. In questo modo si evita un riferimento polimorfico generico `entity_type/entity_id` che indebolirebbe l'integrità referenziale.
