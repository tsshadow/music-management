"""Helpers for the tests that assert pipeline policy against .gitlab-ci.yml."""

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_FILE = REPO_ROOT / ".gitlab-ci.yml"

# Top-level keys that configure the pipeline rather than declare a job.
RESERVED_KEYS = {"default", "stages", "workflow", "include", "variables"}


class _GitlabLoader(yaml.SafeLoader):
    """SafeLoader that tolerates GitLab's !reference tag.

    `!reference [.some_template, rules]` is a GitLab extension, not YAML, and
    yaml.safe_load raises ConstructorError on it. Resolving it is not needed to
    assert policy: the tests only need the document to load and to be able to
    see *that* a job's rules refer to a template. It is therefore represented
    as a plain list of the referenced path, e.g. ['.release_rule', 'rules'].
    """


def _reference(loader: yaml.Loader, node: yaml.Node) -> list[str]:
    return list(loader.construct_sequence(node))


_GitlabLoader.add_constructor("!reference", _reference)


def load_ci() -> dict[str, Any]:
    """Parse .gitlab-ci.yml into a plain dict."""
    return yaml.load(CI_FILE.read_text(encoding="utf-8"), Loader=_GitlabLoader)


def job_names(ci: dict[str, Any]) -> list[str]:
    """Every real job in the pipeline: no reserved keys, no .hidden templates."""
    return [
        name
        for name, body in ci.items()
        if isinstance(body, dict) and not name.startswith(".") and name not in RESERVED_KEYS
    ]
