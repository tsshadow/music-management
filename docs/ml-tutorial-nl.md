# Tutorial: Starten met Machine Learning voor Genre-detectie

Deze tutorial legt uit hoe je de Machine Learning (ML) tools in dit project gebruikt om rules_genres te voorspellen op basis van audio-kenmerken en metadata.

## De Pipeline in 4 stappen

1.  **Analyseren**: Kenmerken (features) van je muziekcollectie extraheren.
2.  **Labelen**: Voorbeeld-antwoorden geven aan het systeem (training data).
3.  **Trainen**: Het ML-model laten leren van jouw voorbeelden.
4.  **Voorspellen**: Het model gebruiken op nieuwe, onbekende library_tracks.

---

### Stap 1: Analyseren

Voordat het systeem kan leren, moet het weten hoe je library_tracks "klinken" en wat de metadata is.

Draai de analyzer op je muziekmap:

```bash
cd services/ml-analyzer
python analyzer.py /pad/naar/je/muziek --save --parallel
```

*   `--save`: Slaat de resultaten op in de database (`library_track_audio_features`). Inclusief metadata en het bestandspad.
*   `--parallel`: Gebruikt meerdere CPU cores voor snelheid.
*   `--tags-only`: (Optioneel) Slaat de zware audio-analyse over en leest alleen de MP3-tags. Handig voor een snelle eerste scan!

Dit vult de tabel `library_track_audio_features` met technische data en `library_track_ml_labels` met de genres uit je tags (klaar voor goedkeuring).

---

### Stap 2: Labelen en Goedkeuren (Training Data voorbereiden)

ML heeft "gelabelde data" nodig. Je hebt nu twee manieren om tracks goed te keuren voor training:

#### Optie A: Interactief goedkeuren (Aanbevolen)
Gebruik het approval script om door je gescande nummers te lopen en ze officieel goed te keuren:

```bash
python approve.py
```
Je krijgt per nummer te zien wat de artiest en het genre is, en kunt met 'y' (yes) of 'n' (no) aangeven of dit correct is. Goedgekeurde nummers worden direct gemarkeerd met `approved_for_training = 1`.

#### Optie B: Handmatig via SQL
Je kunt ook batch-gewijs tracks goedkeuren in de database:
```sql
UPDATE library_track_ml_labels 
SET approved_for_training = 1, ml_review_status = 'human_verified'
WHERE ml_genre = 'Hardcore' AND ml_review_status = 'unreviewed';
```

---

### Stap 3: Trainen

Als je genoeg gelabelde library_tracks hebt (minimaal 10-20 per genre, liefst meer), kun je het model trainen.

```bash
python trainer.py
```

Dit script:
1.  Haalt de gelabelde data op uit de database.
2.  Combineert audio-features met metadata (artiest, label, platform).
3.  Traint een **Random Forest Classifier**.
4.  Slaat het model op in de map `models/`.

Je ziet na afloop een rapport met hoe nauwkeurig het model is.

---

### Stap 4: Voorspellen

Nu kun je het model gebruiken op nieuwe library_tracks die nog geen genre hebben.

```bash
python predict.py /pad/naar/nieuwe/track.mp3
```

Het script zal:
1.  De track analyseren.
2.  De voorspelling doen via het getrainde model.
3.  Het resultaat tonen en opslaan in de tabel `library_track_ml_predictions`.

---

## Veelgestelde Vragen

### Werkt de originele tagger nog?
Ja. De originele tagger (met de regex-regels en database lookups) is niet gewijzigd. De ML-onderdelen draaien ernaast en gebruiken hun eigen tabellen (`track_ml_...`). Je kunt de ML-voorspellingen later gebruiken om de tagger-regels aan te vullen of te vervangen.

### Hoe verbeter ik de nauwkeurigheid?
1.  **Meer data**: Hoe meer gelabelde library_tracks, hoe beter.
2.  **Metadata leakage**: Let op dat het model niet *alleen* op labelnaam gokt. De `trainer.py` laat zien welke features het belangrijkst zijn.
3.  **Kwaliteit**: Zorg dat je library_labels in Stap 2 100% correct zijn.

### Waar staan de resultaten?
*   Features: `library_track_audio_features`
*   Jouw library_labels: `library_track_ml_labels`
*   Voorspellingen: `library_track_ml_predictions`
