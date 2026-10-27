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
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PASSWORD_KEYWORDS = {"password", "passwd"}
DB_MODULES = {"pymysql", "MySQLdb", "mysql", "mariadb"}


def is_literal(node) -> bool:
    """Return True when `node` is a non-empty str or bytes constant."""
    return isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)) and node.value != ""


def literal_assignments(tree: ast.AST) -> set[str]:
    """Return names that are only ever assigned a non-empty literal in this module."""
    literal, other = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                (literal if is_literal(value) else other).add(target.id)
    return literal - other


def db_bindings(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Return (names bound to DB driver modules, names bound to a DB driver's connect)."""
    modules, connects = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in DB_MODULES:
                    modules.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in DB_MODULES:
            for alias in node.names:
                if alias.name == "connect":
                    connects.add(alias.asname or "connect")
                else:
                    modules.add(alias.asname or alias.name)
    return modules, connects


def is_db_connect(func: ast.AST, modules: set[str], connects: set[str]) -> bool:
    """Return True when `func` is a DB driver's `connect`, such as pymysql.connect."""
    if isinstance(func, ast.Name):
        return func.id in connects
    if isinstance(func, ast.Attribute) and func.attr == "connect":
        root = func.value
        while isinstance(root, ast.Attribute):
            root = root.value
        return isinstance(root, ast.Name) and root.id in modules
    return False


def literal_password_lines(source: str) -> list[int]:
    """Return the line numbers of DB `connect(...)` calls in `source` with a literal password.

    Catches a literal or a module-level name holding one, as `password=`/`passwd=`, inside a
    `**{...}` dict, and as the third positional argument.
    """
    tree = ast.parse(source)
    modules, connects = db_bindings(tree)
    names = literal_assignments(tree)

    def literal_value(node) -> bool:
        return is_literal(node) or (isinstance(node, ast.Name) and node.id in names)

    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not is_db_connect(node.func, modules, connects):
            continue
        if len(node.args) >= 3 and literal_value(node.args[2]):
            hits.append(node.lineno)
        for kw in node.keywords:
            if kw.arg in PASSWORD_KEYWORDS and literal_value(kw.value):
                hits.append(kw.value.lineno)
            elif kw.arg is None and isinstance(kw.value, ast.Dict):
                for key, value in zip(kw.value.keys, kw.value.values, strict=True):
                    if isinstance(key, ast.Constant) and key.value in PASSWORD_KEYWORDS and literal_value(value):
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


def test_detector_flags_literals_in_every_shape():
    """The detector catches each way a literal password reaches a DB connect call."""
    imp = "import pymysql\n"
    assert literal_password_lines(imp + "pymysql.connect(host=h, password='x')") == [2]
    assert literal_password_lines("import MySQLdb\nMySQLdb.connect(host=h, passwd='x')") == [2]
    assert literal_password_lines(imp + "pymysql.connect(host=h, password=b'x')") == [2]
    assert literal_password_lines(imp + "pymysql.connect(**{'password': 'x'})") == [2]
    assert literal_password_lines(imp + "pymysql.connect(**{'passwd': 'x'})") == [2]
    assert literal_password_lines(imp + "pymysql.connect('h', 'u', 'x')") == [2]
    assert literal_password_lines("import mysql.connector\nmysql.connector.connect(host=h, password='x')") == [2]
    assert literal_password_lines("from pymysql import connect\nconnect(host=h, password='x')") == [2]
    assert literal_password_lines("import pymysql as pm\npm.connect(password='x')") == [2]


def test_detector_resolves_a_name_assigned_a_literal():
    """The shape that leaked: password = "..." in a function, then connect(password=password)."""
    leaked = (
        "import pymysql\ndef inspect():\n    password = 'x'\n    conn = pymysql.connect(host='h', password=password)\n"
    )
    assert literal_password_lines(leaked) == [4]
    module_level = "import pymysql\nPW = 'x'\npymysql.connect(password=PW)\n"
    assert literal_password_lines(module_level) == [3]


def test_detector_accepts_safe_calls():
    """Variables, environment lookups, empty strings and non-DB connect calls pass."""
    imp = "import pymysql\n"
    assert literal_password_lines(imp + "pymysql.connect(host=h, password=pw)") == []
    assert literal_password_lines(imp + "pymysql.connect(host=h, password=os.environ['P'])") == []
    assert literal_password_lines(imp + "pymysql.connect(host=h, password='')") == []
    assert literal_password_lines(imp + "pw = env['P']\npymysql.connect(password=pw)") == []
    assert literal_password_lines("import sqlite3\nsqlite3.connect('x.db', password='x')") == []
    assert literal_password_lines("import smtplib\ns = smtplib.SMTP()\ns.connect('h', 25, 'x')") == []


def load_script(rel: str):
    """Import the script at `rel` by path and return the module."""
    spec = importlib.util.spec_from_file_location("script_under_test", REPO_ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("script_under_test", None)
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
