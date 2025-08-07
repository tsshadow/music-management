from pathlib import Path

try:
    from fastapi import FastAPI
    from pydantic import BaseModel
except ModuleNotFoundError:  # fallback stubs for environments without FastAPI
    class BaseModel:
        def __init__(self, **data):
            for k, v in data.items():
                setattr(self, k, v)

    class FastAPI:  # simple registry for handlers
        def __init__(self):
            self.routes = {}

        def get(self, path):
            def decorator(func):
                self.routes[("GET", path)] = func
                return func

            return decorator

        def post(self, path):
            def decorator(func):
                self.routes[("POST", path)] = func
                return func

            return decorator

from postprocessing.tagger import Tagger
from postprocessing.constants import SongTypeEnum

app = FastAPI()


class TagPayload(BaseModel):
    file: str
    tag: str
    value: str
    song_type: str | None = None


@app.get("/tags")
def get_tags():
    """Return available tag keys for dropdowns."""
    return {"tags": Tagger.available_tags()}


@app.post("/tags")
def add_tag(payload: TagPayload):
    """Apply a manual tag to a song, overriding automatic parsing."""
    song_type = SongTypeEnum[payload.song_type.upper()] if payload.song_type else SongTypeEnum.GENERIC
    Tagger.parse_song(Path(payload.file), song_type, {payload.tag: payload.value})
    return {"status": "ok"}
