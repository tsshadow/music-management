import os
from typing import Optional
import markdown

def get_version() -> str:
    """Read the VERSION file from the project root or service directory."""
    paths = [
        "VERSION",
        "../VERSION",
        "../../VERSION",
        "/app/VERSION"
    ]
    for path in paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
    return "unknown"

def get_release_notes(service_name: Optional[str] = None) -> str:
    """Read and parse the RELEASE_NOTES.md file."""
    # Try service-specific release notes first if service_name is provided
    paths = []
    if service_name:
        paths.append(f"services/{service_name}/RELEASE_NOTES.md")
        paths.append(f"/app/services/{service_name}/RELEASE_NOTES.md")
        paths.append("RELEASE_NOTES.md") # If running inside the service container where it might be copied to root

    paths.extend([
        "RELEASE_NOTES.md",
        "../RELEASE_NOTES.md",
        "../../RELEASE_NOTES.md",
        "/app/RELEASE_NOTES.md"
    ])

    for path in paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                return markdown.markdown(content, extensions=['extra', 'toc'])

    return "<p>No release notes found.</p>"

def get_changelog() -> str:
    """Read and parse the CHANGELOG.md file."""
    paths = [
        "CHANGELOG.md",
        "../CHANGELOG.md",
        "../../CHANGELOG.md",
        "/app/CHANGELOG.md"
    ]
    for path in paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                return markdown.markdown(content, extensions=['extra', 'toc'])
    return "<p>No changelog found.</p>"
