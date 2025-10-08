# ListenBrainz genre metadata endpoints

To confirm that ListenBrainz is sending genre information for a listen you can hit their metadata endpoints directly. Replace the MusicBrainz IDs (MBIDs) with the ones from the listens you are inspecting.

## Recording metadata endpoint

```
GET https://api.listenbrainz.org/1/metadata/recording/{recording_mbid}
```

This returns the metadata ListenBrainz has cached for the specific recording. When genres are available you will find them inside `track_metadata.additional_info.tags`, for example:

```json
{
  "track_metadata": {
    "artist_name": "Massive Attack",
    "track_name": "Teardrop",
    "additional_info": {
      "tags": ["trip hop", "downtempo"]
    }
  }
}
```

## User listens endpoint with includes

```
GET https://api.listenbrainz.org/1/user/{user_name}/listens?count=1&time_range=all_time&include_metadata=true
```

When `include_metadata=true` is present each listen in the response includes a `track_metadata` block with `additional_info.tags`, matching the structure above. If this field is empty in the ListenBrainz response it means the listen has no genre data available upstream and a re-import will not populate it.

> **Tip:** You can use the MBIDs from this payload to query the MusicBrainz API (`https://musicbrainz.org/ws/2/recording/{recording_mbid}?inc=tags&fmt=json`) if you want to verify whether the source MusicBrainz entry exposes tags for the track.
