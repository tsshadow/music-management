"""No tracked Python file hands a string literal to a database connect call (GitLab #188).

`scripts/cleanup_redundant_indices.py` and `tools/quick_inspect.py` once carried the production
database password in a `pymysql.connect(...)` call, and the secret scanner did not stop it. The
guard reads every tracked `*.py` file as a syntax tree and fails on a `connect(` call whose
`password=` or `passwd=` is a non-empty string literal. A value from the environment, a variable
or a call is fine; so is an empty string.

Also covers the env reading of the two scripts that used to hard-code it.
"""

import ast
import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PASSWORD_KEYWORDS = {"password", "passwd"}


def literal_password_lines(source: str) -> list[int]:
    """Return the line numbers of `connect(...)` calls in `source` with a literal password."""
    hits = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name != "connect":
            continue
        for kw in node.keywords:
            if (
                kw.arg in PASSWORD_KEYWORDS
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
                and kw.value.value != ""
            ):
                hits.append(kw.value.lineno)
    return hits


def tracked_python_files() -> list[str]:
    """Return the tracked `*.py` paths, relative to the repository root."""
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def test_no_tracked_file_connects_with_a_literal_password():
    """Fail on any tracked Python file that passes a string literal as a connect password."""
    offenders = []
    for rel in tracked_python_files():
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
            lines = literal_password_lines(source)
        except (SyntaxError, UnicodeDecodeError):
            continue
        offenders.extend(f"{rel}:{n}" for n in lines)
    assert not offenders, "literal database password in connect(): " + ", ".join(offenders)


def test_detector_flags_a_literal_and_accepts_the_rest():
    """The detector catches literals and ignores variables, environment lookups and empty strings."""
    assert literal_password_lines("pymysql.connect(host=h, password='x')") == [1]
    assert literal_password_lines("conn = connect(host=h, passwd='x')") == [1]
    assert literal_password_lines("pymysql.connect(host=h, password=pw)") == []
    assert literal_password_lines("pymysql.connect(host=h, password=os.environ['P'])") == []
    assert literal_password_lines("pymysql.connect(host=h, password='')") == []


def load_script(rel: str):
    """Import the script at `rel` by path and return the module."""
    spec = importlib.util.spec_from_file_location("script_under_test", REPO_ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPTS = ["scripts/cleanup_redundant_indices.py", "tools/quick_inspect.py"]


@pytest.mark.parametrize("rel", SCRIPTS)
def test_script_names_every_missing_variable(rel):
    """With nothing set, the script exits and the message names DB_HOST, DB_USER and DB_PASS."""
    module = load_script(rel)
    with pytest.raises(SystemExit) as exc:
        module.connection_settings_from_env({})
    message = str(exc.value.code)
    for name in ("DB_HOST", "DB_USER", "DB_PASS"):
        assert name in message


@pytest.mark.parametrize("rel", SCRIPTS)
def test_script_names_only_the_missing_variable(rel):
    """A single missing variable is the only one named."""
    module = load_script(rel)
    with pytest.raises(SystemExit) as exc:
        module.connection_settings_from_env({"DB_HOST": "h", "DB_USER": "u"})
    message = str(exc.value.code)
    assert "DB_PASS" in message
    assert "DB_HOST" not in message and "DB_USER" not in message


@pytest.mark.parametrize("rel", SCRIPTS)
def test_script_reads_settings_and_applies_defaults(rel):
    """Required values are read as given; port and database fall back to 3306 and music-management."""
    module = load_script(rel)
    base = {"DB_HOST": "db.example", "DB_USER": "u", "DB_PASS": "p"}
    settings = module.connection_settings_from_env(base)
    assert settings["host"] == "db.example"
    assert settings["user"] == "u"
    assert settings["password"] == "p"
    assert settings["port"] == 3306
    assert settings["database"] == "music-management"
    custom = module.connection_settings_from_env({**base, "DB_PORT": "3307", "DB_NAME": "other"})
    assert custom["port"] == 3307
    assert custom["database"] == "other"
