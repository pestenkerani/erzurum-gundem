"""RSS -> public JSON -> static GitHub Pages. No personal data is exported."""
import argparse
import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import collector as app

ROOT = Path(__file__).resolve().parent
PUBLIC_FIELDS = ('id', 'title', 'source', 'url', 'published', 'districts', 'category')

def build(refresh=True):
    app.init()
    history = ROOT / 'archive.json'
    previous = json.loads(history.read_text(encoding='utf-8')) if history.exists() else {}
    # Only public article fields are imported, never notes or saved flags.
    with app.connect() as c:
        for row in previous.get('articles', []):
            c.execute('INSERT OR IGNORE INTO articles (id,title,source,url,published,first_seen,districts,category) VALUES (?,?,?,?,?,?,?,?)',
                (row['id'], row['title'], row['source'], row['url'], row['published'], app.now().isoformat(), json.dumps(row['districts'], ensure_ascii=False), row['category']))
    if refresh:
        run = app.collect()
    else:
        run = previous.get('last_run')
    if not run:
        with app.connect() as c:
            run = app.getmeta(c, 'last_run')
    rows = [{key: row[key] for key in PUBLIC_FIELDS} for row in app.articles(24 * 365)]
    if not rows and not (run and run.get('success')):
        raise RuntimeError('No usable archive and no successful feed. Existing deployment remains untouched.')
    success_at = run['at'] if run and run.get('success') else previous.get('last_success')
    public = {'articles': rows, 'last_run': run, 'last_success': success_at, 'districts': app.DISTRICTS, 'categories': list(app.CATEGORIES) + ['Genel']}
    encoded = json.dumps(public, ensure_ascii=False, separators=(',', ':'))
    history.write_text(encoded, encoding='utf-8')
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    for name in ('index.html', 'app.js', 'style.css'):
        shutil.copyfile(ROOT / name, dist / name)
    (dist / 'news.json').write_text(encoded, encoding='utf-8')
    (dist / '.nojekyll').write_text('', encoding='utf-8')
    print(f'{len(rows)} public articles exported; {run.get("success", 0) if run else 0}/6 feeds available')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-refresh', action='store_true')
    build(not parser.parse_args().no_refresh)
