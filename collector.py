"""Erzurum Gündem. Python 3.10+, yalnızca standart kütüphane."""
import argparse
import concurrent.futures
import csv
import hashlib
import html
import io
import json
import logging
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DB = DATA / 'gundem.sqlite3'
TR = timezone(timedelta(hours=3))
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()
DISTRICTS = ['Aziziye', 'Aşkale', 'Çat', 'Hınıs', 'Horasan', 'İspir', 'Karaçoban', 'Karayazı', 'Köprüköy', 'Narman', 'Oltu', 'Olur', 'Palandöken', 'Pasinler', 'Pazaryolu', 'Şenkaya', 'Tekman', 'Tortum', 'Uzundere', 'Yakutiye']
CATEGORIES = {
    'Hava durumu': ['hava durumu', 'saatlik hava', 'günlük hava'],
    'Afet ve güvenlik': ['deprem', 'sel', 'heyelan', 'yangın', 'kaza', 'çığ', 'fırtına', 'gözaltı'],
    'Altyapı ve ulaşım': ['yol', 'ulaşım', 'otobüs', 'su kesinti', 'elektrik', 'altyapı', 'havalimanı', 'demiryolu', 'asfalt'],
    'Tarım ve hayvancılık': ['tarım', 'çiftçi', 'hayvancılık', 'mera', 'süt', 'besici', 'sulama', 'hasat'],
    'Ekonomi ve yatırım': ['yatırım', 'ihale', 'istihdam', 'işçi', 'fabrika', 'esnaf', 'ekonomi', 'işsizlik', 'ihracat', 'konut'],
    'Eğitim ve sağlık': ['okul', 'eğitim', 'öğrenci', 'üniversite', 'öğretmen', 'hastane', 'sağlık', 'doktor'],
    'Kamu ve siyaset': ['meclis', 'milletvekili', 'bakan', 'vali', 'belediye', 'tbmm', 'kanun', 'komisyon'],
    'Kültür, turizm ve spor': ['turizm', 'kayak', 'spor', 'festival', 'kültür', 'müze', 'tiyatro', 'konser'],
}
QUERIES = [
    ('Erzurum genel gündem', 'Erzurum when:7d'),
    ('Merkez ve çevre ilçeler', 'Erzurum (Aziziye OR Yakutiye OR Palandöken OR Aşkale OR Çat OR Pasinler OR Köprüköy) when:7d'),
    ('Kuzey ilçeleri', 'Erzurum (İspir OR Pazaryolu OR Tortum OR Uzundere OR Oltu OR Olur OR Narman OR Şenkaya) when:7d'),
    ('Güney ve doğu ilçeleri', 'Erzurum (Hınıs OR Tekman OR Karayazı OR Karaçoban OR Horasan) when:7d'),
    ('Kamu kaynakları dizini', 'Erzurum (site:erzurum.gov.tr OR site:erzurum.bel.tr OR site:atauni.edu.tr OR site:erzurum.edu.tr) when:7d'),
    ('Yerel basın dizini', 'Erzurum (site:gazetepusula.net OR site:erzurumgazetesi.com.tr) when:7d'),
]

def now():
    return datetime.now(timezone.utc)

def fold(s):
    return s.replace('İ', 'i').replace('I', 'ı').lower().translate(str.maketrans('çğıöşü', 'cgiosu'))

def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()

def classify(title):
    normalized = fold(title)
    districts = [d for d in DISTRICTS if re.search(r'(?<!\w)' + re.escape(fold(d)) + r'(?!\w)', normalized)]
    # "olur" gündelik bir fiil olduğu için ilçe bağlamı olmadan etiketlenmez.
    if 'Olur' in districts and not re.search(r'\bolur(?:[’\x27](?:da|a|un)| ilce| belediye| kaymakam)', normalized):
        districts.remove('Olur')
    category = next((name for name, words in CATEGORIES.items() if any(re.search(r'(?<!\w)' + re.escape(fold(w)), normalized) for w in words)), 'Genel')
    return districts or ['İl geneli / belirsiz'], category

@contextmanager
def connect():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()

def init():
    DATA.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS articles (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL, url TEXT NOT NULL,
          published TEXT, first_seen TEXT NOT NULL, districts TEXT NOT NULL, category TEXT NOT NULL,
          saved INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')

def setmeta(c, key, value):
    c.execute('INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value, ensure_ascii=False)))

def getmeta(c, key, default=None):
    row = c.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default

def parse_feed(payload):
    root = ET.fromstring(payload)
    if root.tag != 'rss':
        raise ValueError('Beklenen RSS biçimi alınamadı')
    result = []
    for item in root.findall('./channel/item'):
        source = clean(item.findtext('source')) or 'Kaynak belirtilmemiş'
        title = clean(item.findtext('title'))
        if title.endswith(' - ' + source):
            title = title[:-(len(source) + 3)]
        url = item.findtext('link', '').strip()
        if not title or fold(title.strip(' -–—')) == fold(source) or urllib.parse.urlparse(url).scheme not in ('https', 'http'):
            continue
        try:
            date = parsedate_to_datetime(item.findtext('pubDate', ''))
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            published = date.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError):
            published = None
        districts, category = classify(title)
        identity = hashlib.sha256((fold(title) + '|' + fold(source)).encode()).hexdigest()[:24]
        result.append((identity, title, source, url, published, now().isoformat(), json.dumps(districts, ensure_ascii=False), category))
    return result

def fetch_feed(label, query):
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': query, 'hl': 'tr', 'gl': 'TR', 'ceid': 'TR:tr'})
    request = urllib.request.Request(url, headers={'User-Agent': 'ErzurumGundem/1.0 (personal news reader)'})
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = response.read(3_000_001)
    if len(payload) > 3_000_000:
        raise ValueError('Akış boyut sınırını aştı')
    return parse_feed(payload)

def collect():
    if not LOCK.acquire(blocking=False):
        return {'busy': True}
    try:
        statuses, count = [], 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fetch_feed, label, query): label for label, query in QUERIES}
            for future in concurrent.futures.as_completed(futures):
                label = futures[future]
                try:
                    rows = future.result()
                    with connect() as c:
                        before = c.total_changes
                        c.executemany('INSERT OR IGNORE INTO articles (id,title,source,url,published,first_seen,districts,category) VALUES (?,?,?,?,?,?,?,?)', rows)
                        count += c.total_changes - before
                    statuses.append({'name': label, 'ok': True, 'count': len(rows)})
                except Exception as e:
                    logging.exception('Akış alınamadı: %s', label)
                    statuses.append({'name': label, 'ok': False, 'error': str(e)[:220]})
        success = sum(s['ok'] for s in statuses)
        result = {'at': now().isoformat(), 'new': count, 'success': success, 'total': len(QUERIES), 'sources': statuses}
        with connect() as c:
            setmeta(c, 'last_run', result)
            if success:
                setmeta(c, 'last_success', now().isoformat())
        if success:
            folder = DATA / 'brifingler'
            folder.mkdir(exist_ok=True)
            (folder / (now().astimezone(TR).strftime('%Y-%m-%d') + '.md')).write_text(briefing(24), encoding='utf-8')
        logging.info('Tarama: %s yeni haber, %s/%s akış', count, success, len(QUERIES))
        return result
    finally:
        LOCK.release()

def articles(hours=24 * 7):
    cutoff = (now() - timedelta(hours=hours)).isoformat()
    with connect() as c:
        rows = c.execute('SELECT * FROM articles WHERE published >= ? AND published <= ? ORDER BY published DESC', (cutoff, (now() + timedelta(minutes=10)).isoformat())).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        if fold(item['title'].strip(' -–—')) == fold(item['source']):
            continue
        item['districts'] = json.loads(item['districts'])
        item['category'] = classify(item['title'])[1]
        result.append(item)
    return result

def briefing(hours):
    rows = articles(hours)
    with connect() as c:
        status = getmeta(c, 'last_run', {})
    lines = ['# Erzurum Gündem — Danışman Brifingi', '', now().astimezone(TR).strftime('%d.%m.%Y %H:%M') + f' (Türkiye saati) · Son {hours} saat', '',
        f'{len(rows)} haber kaydı · {len(set(r["source"] for r in rows))} yayıncı', '',
        'Bu belge kaynaklı bir başlık derlemesidir; haber metinlerinin özeti veya doğruluk teyidi değildir. Konu ve ilçe etiketleri başlıktan otomatik çıkarılır. Google Haberler dizini tüm haberleri kapsamaz.', '',
        f'Son tarama: {status.get("success", 0)}/{status.get("total", len(QUERIES))} akış başarılı.', '']
    if not rows:
        lines += ['Bu zaman aralığında kayıt yok. Akış durumunu kontrol edin; bu sonuç kentte haber olmadığı anlamına gelmez.']
    for category in list(CATEGORIES) + ['Genel']:
        selected = [r for r in rows if r['category'] == category]
        if selected:
            lines += ['## ' + category, '']
            seen = set()
            for row in selected:
                key = fold(row['title'])
                if key in seen:
                    continue
                seen.add(key)
                title = row['title'].replace('[', '(').replace(']', ')')
                date = datetime.fromisoformat(row['published']).astimezone(TR).strftime('%d.%m %H:%M')
                lines += [f'- **{title}** — {row["source"]} · {date} · {", ".join(row["districts"])}', f'  Kaynak: {row["url"]}']
                if row['note']:
                    lines += ['  Danışman notu: ' + row['note'].replace('\n', ' ')]
            lines += ['']
    lines += ['## Teyit ve takip', '', '- Kurumu ilgilendiren iddiaları kaynak metinden ve ilgili kurumdan teyit edin.', '- İhale ve duyuruların tarihlerini resmi kaynaktan kontrol edin.', '- Aynı haberin farklı yayıncılarda yer alması bağımsız teyit sayılmaz.', '']
    return '\n'.join(lines)

def scheduler():
    while True:
        with connect() as c:
            last = getmeta(c, 'last_success')
            run = getmeta(c, 'last_run', {})
        local = now().astimezone(TR)
        due = not last or (datetime.fromisoformat(last).astimezone(TR).date() < local.date() and local.hour >= 8)
        retry_ready = not run.get('at') or (now() - datetime.fromisoformat(run['at'])).total_seconds() >= 3600
        if retry_ready and (due or run.get('success', 0) < len(QUERIES)):
            collect()
        time.sleep(60)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logging.info(fmt, *args)

    def send(self, value, status=200, kind='application/json; charset=utf-8', filename=None):
        data = (json.dumps(value, ensure_ascii=False) if kind.startswith('application/json') else value).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if filename:
            self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
        self.end_headers()
        self.wfile.write(data)

    def valid_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def do_GET(self):
        if not self.valid_host():
            return self.send({'error': 'Geçersiz sunucu adresi'}, 403)
        parsed = urllib.parse.urlparse(self.path)
        try:
            hours = min(24 * 365, max(1, int(urllib.parse.parse_qs(parsed.query).get('hours', ['168'])[0])))
        except ValueError:
            return self.send({'error': 'Geçersiz süre'}, 400)
        if parsed.path == '/api/state':
            with connect() as c:
                status = getmeta(c, 'last_run')
                watch = getmeta(c, 'watch', ['ihale', 'yatırım', 'çiftçi', 'su kesintisi'])
                unknown = c.execute('SELECT COUNT(*) FROM articles WHERE published IS NULL').fetchone()[0]
            return self.send({'articles': articles(hours), 'last_run': status, 'busy': LOCK.locked(), 'watch': watch, 'districts': DISTRICTS, 'categories': list(CATEGORIES) + ['Genel'], 'token': TOKEN, 'unknown_dates': unknown})
        if parsed.path == '/api/briefing':
            return self.send(briefing(hours), kind='text/markdown; charset=utf-8', filename='erzurum-brifing.md')
        if parsed.path == '/api/csv':
            output = io.StringIO()
            output.write('\ufeff')
            writer = csv.writer(output)
            writer.writerow(['Başlık', 'Kaynak', 'Yayın zamanı (Türkiye)', 'Konu', 'İlçe', 'Bağlantı', 'Not'])
            for r in articles(hours):
                cells = [r['title'], r['source'], datetime.fromisoformat(r['published']).astimezone(TR).strftime('%Y-%m-%d %H:%M'), r['category'], ', '.join(r['districts']), r['url'], r['note']]
                writer.writerow(["'" + v if v.lstrip().startswith(('=', '+', '-', '@')) else v for v in cells])
            return self.send(output.getvalue(), kind='text/csv; charset=utf-8', filename='erzurum-haberler.csv')
        files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
        if parsed.path in files:
            name, kind = files[parsed.path]
            return self.send((ROOT / 'web' / name).read_text(encoding='utf-8'), kind=kind + '; charset=utf-8')
        self.send({'error': 'Bulunamadı'}, 404)

    def do_POST(self):
        if not self.valid_host() or self.headers.get('X-Gundem-Token') != TOKEN:
            return self.send({'error': 'İstek doğrulanamadı'}, 403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 20000:
                raise ValueError()
            body = json.loads(self.rfile.read(length) or '{}')
            if self.path == '/api/refresh':
                if not LOCK.locked():
                    threading.Thread(target=collect, daemon=True).start()
                return self.send({'ok': True}, 202)
            if self.path == '/api/watch':
                words = body.get('words')
                if not isinstance(words, list) or len(words) > 30 or not all(isinstance(w, str) and 0 < len(w) <= 60 for w in words):
                    raise ValueError()
                with connect() as c:
                    setmeta(c, 'watch', words)
                return self.send({'ok': True})
            if self.path == '/api/article':
                with connect() as c:
                    if 'saved' in body:
                        c.execute('UPDATE articles SET saved=? WHERE id=?', (int(bool(body['saved'])), str(body['id'])))
                    if 'note' in body:
                        c.execute('UPDATE articles SET note=? WHERE id=?', (str(body['note'])[:5000], str(body['id'])))
                return self.send({'ok': True})
            return self.send({'error': 'Bulunamadı'}, 404)
        except (ValueError, KeyError, TypeError):
            return self.send({'error': 'Geçersiz veri'}, 400)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--collect', action='store_true', help='Haberleri derle ve çık')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    init()
    logging.basicConfig(filename=DATA / 'uygulama.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')
    if args.collect:
        result = collect()
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get('success') == len(QUERIES) else 1
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    threading.Thread(target=scheduler, daemon=True).start()
    logging.info('Panel hazır: http://127.0.0.1:%s', args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
