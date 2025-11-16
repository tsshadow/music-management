from pathlib import Path
import ast
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]  # repo root, pas aan als nodig

OLD_PREFIXES = ("processing", "postprocessing", " data","analyzer")

def main():
    counter = Counter()
    modules_by_file = {}

    for path in ROOT.rglob("*.py"):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue

        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(OLD_PREFIXES):
                    counter[node.module] += 1
                    modules_by_file.setdefault(node.module, []).append(
                        f"{path}:{node.lineno}"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name.startswith(OLD_PREFIXES):
                        counter[name] += 1
                        modules_by_file.setdefault(name, []).append(
                            f"{path}:{node.lineno}"
                        )

    print("== Unieke oude modules met aantallen ==")
    for mod, count in counter.most_common():
        print(f"{mod}: {count}")

if __name__ == "__main__":
    main()
