### Voorstel: Backend Deduplicatie voor LMS

Dit document beschrijft de aanpak om deduplicatie van tracks volledig naar de C++ backend te verplaatsen, met behoud van correcte pagination en een gegarandeerd aantal resultaten per pagina.

---

### Het Probleem
Wanneer de backend tracks dedupliceert op basis van een database-batch (bijv. 50 tracks), resulteert dit vaak in minder dan 50 unieke tracks (bijv. 40). De UI moet dan extra verzoeken doen om de pagina te vullen, wat complexiteit in de frontend introduceert en inconsistenties tussen verschillende UI's kan veroorzaken.

### Voorgestelde Oplossing: Backend-driven Streaming Deduplicatie

De backend moet verantwoordelijk zijn voor het "volmaken" van de pagina. In plaats van een vaste database-range op te vragen, scannen we door de database-resultaten totdat we de gewenste `count` aan unieke tracks hebben bereikt.

#### 1. Strategie voor Pagination (Offset)
De grootste uitdaging bij backend-deduplicatie is de `offset`. Een traditionele `offset` van 50 betekent "sla 50 rijen over". Bij deduplicatie betekent het echter "sla tracks over totdat je 50 unieke tracks hebt gevonden".

**Oplossing: Scanner-based Offset**
We introduceren het concept van een `scannerOffset`.
- De client vraagt om `count=50`.
- De backend begint te scannen vanaf de meegegeven `offset` (dit is de *fysieke* positie in de database).
- De backend verzamelt unieke tracks totdat hij er 50 heeft.
- De backend geeft in de response een `nextOffset` terug (de fysieke positie waar de scanner is gebleven).

#### 2. Voor- en Nadelen

| Feature | Voordelen | Nadelen |
| :--- | :--- | :--- |
| **Backend Logica** | - UI is simpel en "dom".<br>- Consistente resultaten over alle UI's (Web, Mobile, etc.).<br>- Geen extra netwerk round-trips nodig vanuit de UI. | - Complexere C++ implementatie.<br>- Vereist afwijking van/uitbreiding op de standaard Subsonic API. |
| **Gegarandeerde Count** | - Altijd 50 tracks als ze er zijn.<br>- Infinite scroll werkt soepeler. | - Backend moet potentieel veel meer tracks scannen dan hij teruggeeft. |
| **Pagination** | - Stabiele pagination: tracks verspringen niet. | - De `offset` is niet langer een rij-nummer maar een "scanner-positie". |

---

### Gerealiseerde Implementatie

#### Backend (`Spotify.cpp`)
- `findTracks` gebruikt nu een `while`-loop die in batches van de database leest totdat de gewenste `count` aan unieke tracks is bereikt.
- De response bevat een `nextOffset` attribuut dat aangeeft waar de scanner is gebleven.
- Ranking (FLAC > MP3) blijft behouden binnen de scan-vensters.

#### Frontend (`Dashboard.svelte`, `ArtistView.svelte`)
- De handmatige `while`-loop in JS is verwijderd.
- De UI gebruikt nu direct de resultaten van de backend en werkt de `offset` bij aan de hand van `nextOffset` uit de response.
- Dit resulteert in minder netwerkverkeer en een snellere UI-ervaring.

#### Overige views (`SearchMoreModal.svelte`)
- Voor standaard Subsonic endpoints (`search3`) blijft de frontend deduplicatie actief als fallback, aangezien deze endpoints (nog) geen backend-deduplicatie ondersteunen.

---

### Conclusie
Het verplaatsen van deze logica naar de backend is een robuustere oplossing. Het garandeert een consistente ervaring en maakt de frontend aanzienlijk eenvoudiger. De lichte overhead in de backend (extra scannen) weegt niet op tegen de voordelen van een schone API en betrouwbare pagination.
