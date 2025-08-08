import inspect
import logging
import inspect

from job_manager import job_manager


class Step:
    """Represents an executable step in the importer workflow."""

    def __init__(self, name, condition_keys, action):
        self.name = name
        self.condition_keys = set(condition_keys)
        self.action = action

    def should_run(self, steps):
        return bool(self.condition_keys.intersection(steps)) or "all" in steps

    def run(self, steps, **kwargs):
        if self.should_run(steps):
            job_id = job_manager.register(self.name)
            try:
                params = inspect.signature(self.action).parameters
                if "steps" in params:
                    self.action(steps, **kwargs)
                elif params:
                    self.action(**kwargs)
                else:
                    self.action()
                logging.info(f"{self.name} completed.")
                job_manager.update(job_id, "completed")
            except Exception as e:
                logging.error(f"{self.name} failed: {e}")
                job_manager.update(job_id, "failed", str(e))
            return job_id