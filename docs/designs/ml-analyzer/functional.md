# ML Analyzer — Functional Design

See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This is the
functional (user-observable) half of the audio analysis and genre prediction feature; the implementation 
contract is in [technical.md](technical.md).

## Overview

The `ml-analyzer` service provides automated audio analysis and genre classification for the music library.
It extracts technical audio features (BPM, spectral characteristics, energy) and uses machine learning 
to suggest genres for newly added tracks. This helps maintain a well-organized library even when 
incoming files have incomplete or inconsistent tags. Administrators can review AI predictions and 
manually approve them to improve the system's accuracy over time.

## User Stories

- As a library manager, I want the system to automatically detect the BPM of my tracks, so that I can filter my library by tempo without manual entry.
- As a library manager, I want the system to suggest genres for new tracks, so that I can quickly categorize large batches of music.
- As a library manager, I want to see the confidence level of AI predictions, so that I know which ones I should double-check.
- As an administrator, I want to manually verify and correct AI-suggested genres, so that the training data for the machine learning model remains high-quality.
- As a user, I want to filter my library by tempo and genre in the "Advanced" view, so that I can find exactly the music I'm looking for.

## Functional Flows

### Automated Analysis

| Situation | Observable outcome |
|---|---|
| A new track is added to a monitored folder | The system eventually extracts audio features (BPM, etc.) and stores them in the background. |
| The analyzer runs on a track with a tempo of 175 BPM | The BPM is correctly identified (the analyzer is optimized for fast electronic music >150 BPM). |
| The analyzer runs on a track with no existing tags | It extracts audio features and prepares for a genre prediction based on sound only. |

### Genre Prediction and Review

| Situation | Observable outcome |
|---|---|
| A prediction is made for a track | The predicted genre and a confidence percentage (e.g., "Hardstyle (92%)") are recorded in the database. |
| An administrator reviews predictions via the CLI tool | They are shown the track details and the AI guess, and can choose to approve, correct, or skip the track. |
| A prediction is corrected by an administrator | The correct genre is saved and the track is marked as "human_verified", making it available for future model training. |

## Acceptance Criteria

1. Every track in the supported music folders is eventually analyzed for basic features (BPM, duration, RMS).
2. BPM detection is reliable for high-tempo electronic music, avoiding "half-BPM" detection errors.
3. Genre predictions are accompanied by a confidence score to aid manual review.
4. Only "human_verified" labels are used for production model training to prevent feedback loops of errors.
5. Analysis results (BPM, Predicted Genre) are visible and searchable in the frontend's "Advanced" library tab.

## Open Questions / Not Yet Decided

- **Musical Key and Mood Detection**: While these fields exist in the database and UI, they are currently placeholders. Which specific algorithms (e.g., Essentia, MuQ) will be used for these features?
- **Real-time API**: Currently, analysis is batch-processed or triggered via CLI. Should there be a REST endpoint in `music-manager` to trigger analysis for a specific track on demand?
- **Web UI for Review**: The current approval process is CLI-based (`approve.py`). Is a dedicated web interface for genre approval required for non-technical administrators?
- **Auto-tagging**: Should the system automatically write high-confidence predictions back to the file tags, or keep them strictly in the database?
