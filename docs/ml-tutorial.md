# Tutorial: Getting Started with Machine Learning for Genre Detection

This tutorial explains how to use the Machine Learning (ML) tools in this project to predict genres based on audio features and metadata.

## The Pipeline in 4 steps

1.  **Analyzing**: Extract characteristics (features) of your music collection.
2.  **Labeling**: Provide example answers to the system (training data).
3.  **Training**: Let the ML model learn from your examples.
4.  **Predicting**: Use the model on new, unknown tracks.

---

### Step 1: Analyzing

Before the system can learn, it needs to know how your tracks "sound" and what the metadata is.

Run the analyzer on your music folder:

```bash
cd services/ml-analyzer
python analyzer.py /path/to/your/music --save --parallel
```

*   `--save`: Saves the results in the database (`library_track_audio_features`). Including metadata and the file path.
*   `--parallel`: Uses multiple CPU cores for speed.
*   `--tags-only`: (Optional) Skips the heavy audio analysis and only reads the MP3 tags. Useful for a quick first scan!

This fills the table `library_track_audio_features` with technical data and `library_track_ml_labels` with the genres from your tags (ready for approval).

---

### Step 2: Labeling and Approving (Preparing Training Data)

ML needs "labeled data." You now have two ways to approve tracks for training:

#### Option A: Interactive approval (Recommended)
Use the approval script to go through your scanned tracks and officially approve them:

```bash
python approve.py
```
You will see the artist and genre for each track and can indicate with 'y' (yes) or 'n' (no) whether this is correct. Approved tracks are immediately marked with `approved_for_training = 1`.

#### Option B: Manually via SQL
You can also approve tracks in batches in the database:
```sql
UPDATE library_track_ml_labels 
SET approved_for_training = 1, ml_review_status = 'human_verified'
WHERE ml_genre = 'Hardcore' AND ml_review_status = 'unreviewed';
```

---

### Step 3: Training

Once you have enough labeled tracks (at least 10-20 per genre, preferably more), you can train the model.

```bash
python trainer.py
```

This script:
1.  Fetches the labeled data from the database.
2.  Combines audio features with metadata (artist, label, platform).
3.  Trains a **Random Forest Classifier**.
4.  Saves the model in the `models/` folder.

Afterwards, you will see a report on how accurate the model is.

---

### Step 4: Predicting

Now you can use the model on new tracks that don't have a genre yet.

```bash
python predict.py /path/to/new/track.mp3
```

The script will:
1.  Analyze the track.
2.  Make the prediction via the trained model.
3.  Show the result and save it in the table `library_track_ml_predictions`.

---

## Frequently Asked Questions

### Does the original tagger still work?
Yes. The original tagger (with the regex rules and database lookups) has not changed. The ML components run alongside it and use their own tables (`track_ml_...`). You can use the ML predictions later to supplement or replace the tagger rules.

### How do I improve accuracy?
1.  **More data**: The more labeled tracks, the better.
2.  **Metadata leakage**: Be careful that the model doesn't gamble *only* on label name. The `trainer.py` shows which features are most important.
3.  **Quality**: Ensure your labels in Step 2 are 100% correct.

### Where are the results?
*   Features: `library_track_audio_features`
*   Your labels: `library_track_ml_labels`
*   Predictions: `library_track_ml_predictions`
