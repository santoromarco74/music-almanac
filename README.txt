Ripristino migrazione mancante v1.6.0

Contenuto:
backend/migrations/versions/0003_musicbrainz_review_workflow.py

La migrazione è stata recuperata dal branch main del repository GitHub:
https://github.com/santoromarco74/music-almanac/blob/main/backend/migrations/versions/0003_musicbrainz_review_workflow.py

Installazione:
1. Estrarre il contenuto dello ZIP nella root del repository locale, mantenendo i percorsi.
2. Verificare che il file sia presente in backend/migrations/versions/.
3. Eseguire:
   docker compose exec api alembic history --verbose
   docker compose exec api alembic current --verbose
4. Se la revisione corrente è 0002_artist_aliases e la cronologia mostra la catena 0002 -> 0003 -> 0004, applicare:
   docker compose exec api alembic upgrade head
5. Verificare:
   docker compose exec api alembic current --verbose

Non usare docker compose down -v.
Non modificare manualmente alembic_version.
