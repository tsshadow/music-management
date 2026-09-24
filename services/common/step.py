import inspect
import logging


class Step:
    """Represents an executable step in the importer workflow."""

    def __init__(self, name, action, condition_keys=None):
        self.name = name
        self.condition_keys: set | None = set(condition_keys) if condition_keys is not None else None
        self.action = action

    def should_run(self, steps):
        """Whether this step is selected by `steps` ('all' selects every step)."""
        return self.condition_keys is None or bool(self.condition_keys.intersection(steps)) or 'all' in steps

    def run(self, steps, **kwargs):
        """Run the action if `steps` selects it.

        Returns None when the step was not selected, True when the action completed and
        False when it raised; a failure is logged, never propagated, so one broken step
        cannot stop the rest of the pipeline.
        """
        if not self.should_run(steps):
            return None
        try:
            params = inspect.signature(self.action).parameters
            if 'steps' in params:
                self.action(steps, **kwargs)
            elif params:
                self.action(**kwargs)
            else:
                self.action()
        except Exception as e:
            logging.error(f'{self.name} failed: {e}')
            return False
        logging.info(f'{self.name} completed.')
        return True
