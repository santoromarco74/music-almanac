# Integrazione dashboard esistente

La dashboard attuale resta invariata. Il backend espone i seguenti endpoint aggiuntivi, utilizzabili dal client già presente:

- `/api/v1/editorial-items` e relativi endpoint figlio per workflow, relazioni, scoring e tag.
- `/api/v1/search` per la ricerca trasversale.
- `/api/v1/calendar` per il calendario degli eventi.
- `/api/v1/export/{entity}?format=json|csv` per download.

Il client dovrebbe leggere la base URL da configurazione (es. `VITE_API_BASE_URL` o variabile equivalente già adottata dal progetto), gestire risposte 4xx mostrando `detail`, e non considerare pubblicabile una scheda prima che l'API abbia accettato la transizione a `PUBLISHED`. Non introdurre chiamate dirette al database dal frontend.
