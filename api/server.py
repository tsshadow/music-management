import logging
import uuid
from typing import Dict

from fastapi import FastAPI, BackgroundTasks, HTTPException

from main import Step
from data.settings import Settings
from postprocessing.repair import FileRepair
from postprocessing.sanitizer import Sanitizer
from postprocessing.tagger import Tagger
from postprocessing.analyze import Analyze
from postprocessing.artistfixer import ArtistFixer
from processing.converter import Converter
from processing.epsflattener import EpsFlattener
from processing.extractor import Extractor
from processing.mover import Mover
from processing.renamer import Renamer
from downloader.youtube import YoutubeDownloader
from downloader.soundcloud import SoundcloudDownloader
from downloader.telegram import TelegramDownloader

app = FastAPI()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    force=True,
)

jobs: Dict[str, Dict] = {}

settings = Settings()
youtube_downloader = YoutubeDownloader()
soundcloud_downloader = SoundcloudDownloader()
telegram_downloader = TelegramDownloader()
extractor = Extractor()
renamer = Renamer()
mover = Mover()
converter = Converter()
sanitizer = Sanitizer()
flattener = EpsFlattener()
repair = FileRepair()
analyze_step = Analyze()
artist_fixer = ArtistFixer()

def run_tagger(steps):
    parse_all = "tag" in steps
    tagger = Tagger()
    tagger.run(
        parse_labels=parse_all or "tag-labels" in steps,
        parse_soundcloud=parse_all or "tag-soundcloud" in steps,
        parse_youtube=parse_all or "tag-youtube" in steps,
        parse_generic=parse_all or "tag-generic" in steps,
        parse_telegram=parse_all or "tag-telegram" in steps,
    )

steps_to_run = [
    Step("Extractor", ["import", "extract"], extractor.run),
    Step("Renamer", ["import", "rename"], renamer.run),
    Step("Mover", ["import", "move"], mover.run),
    Step("Converter", ["convert"], converter.run),
    Step("Sanitizer", ["sanitize"], sanitizer.run),
    Step("Flattener", ["flatten"], flattener.run),
    Step("YouTube Downloader", ["download", "download-youtube"], youtube_downloader.run),
    Step(
        "SoundCloud Downloader",
        ["download", "download-soundcloud"],
        lambda: soundcloud_downloader.run(account=""),
    ),
    Step(
        "Telegram Downloader",
        ["download-telegram"],
        lambda: telegram_downloader.run(""),
    ),
    Step("Analyze", ["analyze"], analyze_step.run),
    Step("ArtistFixer", ["artistfixer"], artist_fixer.run),
    Step(
        "Tagger",
        [
            "tag",
            "tag-labels",
            "tag-soundcloud",
            "tag-youtube",
            "tag-generic",
            "tag-telegram",
        ],
        lambda steps=None: run_tagger(steps or []),
    ),
]

step_map = {key: step for step in steps_to_run for key in step.condition_keys}


@app.get("/api/steps")
def list_steps():
    """Return available step keys for dropdowns."""
    return {"steps": sorted(step_map.keys())}


@app.get("/api/jobs")
def list_jobs():
    """Return currently active jobs for selection."""
    return {
        "jobs": [
            job
            for job in jobs.values()
            if job["status"] in {"queued", "running"}
        ]
    }


class JobLogHandler(logging.Handler):
    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = job_id

    def emit(self, record: logging.LogRecord) -> None:
        jobs[self.job_id]["log"].append(self.format(record))


def execute_step(step_name: str, job_id: str):
    job = jobs[job_id]
    step = step_map.get(step_name)
    if not step:
        job["status"] = "error"
        job["log"].append(f"Unknown step: {step_name}")
        return

    handler = JobLogHandler(job_id)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logging.getLogger().addHandler(handler)

    try:
        job["status"] = "running"
        step.run({step_name})
        job["status"] = "done"
    except Exception as e:  # pragma: no cover - for robustness
        job["status"] = "error"
        job["log"].append(str(e))
    finally:
        logging.getLogger().removeHandler(handler)


@app.post("/api/run/{step_name}")
def run_step_endpoint(step_name: str, background_tasks: BackgroundTasks):
    if step_name not in step_map:
        raise HTTPException(status_code=404, detail="Unknown step")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"id": job_id, "step": step_name, "status": "queued", "log": []}
    background_tasks.add_task(execute_step, step_name, job_id)
    return jobs[job_id]


@app.get("/api/job/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
