from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import markdown
import os

app = FastAPI(title="Music Management Control Center")

def get_file_content(filename):
    # Try multiple possible paths depending on environment
    paths = [
        os.path.join(os.getcwd(), filename),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), filename),
        os.path.join("/app", filename)
    ]
    for path in paths:
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
    return f"File {filename} not found."

@app.get("/", response_class=HTMLResponse)
def index():
    release_notes_md = get_file_content("RELEASE_NOTES.md")
    changelog_md = get_file_content("CHANGELOG.md")
    version = get_file_content("VERSION").strip()
    
    release_notes_html = markdown.markdown(release_notes_md, extensions=['extra', 'toc'])
    changelog_html = markdown.markdown(changelog_md, extensions=['extra', 'toc'])
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Music Management Control Center</title>
        <style>
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
                line-height: 1.6; 
                color: #333; 
                max-width: 900px; 
                margin: 0 auto; 
                padding: 20px; 
                background-color: #f4f4f9; 
            }}
            header {{ 
                border-bottom: 2px solid #3498db; 
                margin-bottom: 20px; 
                padding-bottom: 10px; 
                display: flex; 
                justify-content: space-between; 
                align-items: baseline; 
            }}
            h1 {{ margin: 0; color: #2c3e50; }}
            .version {{ font-size: 1.1em; color: #7f8c8d; font-weight: bold; }}
            nav {{ 
                margin-bottom: 30px; 
                position: sticky;
                top: 0;
                background: rgba(244, 244, 249, 0.9);
                padding: 10px 0;
                z-index: 100;
            }}
            nav a {{ 
                margin-right: 20px; 
                text-decoration: none; 
                color: #3498db; 
                font-weight: bold; 
                font-size: 1.1em;
            }}
            nav a:hover {{ color: #2980b9; }}
            .card {{ 
                background: white; 
                padding: 30px; 
                border-radius: 12px; 
                box-shadow: 0 4px 6px rgba(0,0,0,0.05); 
                margin-bottom: 40px; 
            }}
            h2 {{ color: #2980b9; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-top: 0; }}
            h3 {{ color: #16a085; margin-top: 25px; }}
            ul {{ padding-left: 20px; }}
            li {{ margin-bottom: 8px; }}
            code {{ background: #f0f0f0; padding: 2px 5px; border-radius: 4px; font-family: 'Monaco', 'Menlo', monospace; font-size: 0.9em; }}
            pre {{ 
                background: #2d3436; 
                color: #dfe6e9; 
                padding: 20px; 
                border-radius: 8px; 
                overflow-x: auto; 
                font-size: 0.9em;
            }}
            hr {{ border: 0; border-top: 1px solid #eee; margin: 30px 0; }}
        </style>
    </head>
    <body>
        <header>
            <h1>Music Management Control Center</h1>
            <span class="version">Version {version}</span>
        </header>
        
        <nav>
            <a href="#release-notes">🚀 Release Notes</a>
            <a href="#changelog">📜 Changelog</a>
            <a href="#modules">📦 Modules</a>
        </nav>
        
        <div id="release-notes" class="card">
            <h2>Release Notes</h2>
            {release_notes_html}
        </div>
        
        <div id="changelog" class="card">
            <h2>Technical Changelog</h2>
            {changelog_html}
        </div>

        <div id="modules" class="card">
            <h2>Module Status</h2>
            <ul>
                <li><strong>Main Application</strong>: API, Importer, Tagger, Downloader</li>
                <li><strong>ML Analyzer</strong>: Deep audio feature extraction</li>
                <li><strong>Tools</strong>: SoundCloud/YouTube fetchers and maintenance scripts</li>
            </ul>
        </div>
    </body>
    </html>
    """
    return html

@app.get("/health")
def health():
    return {{"status": "healthy"}}
