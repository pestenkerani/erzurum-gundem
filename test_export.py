import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import build

class ExportTests(unittest.TestCase):
    def test_notes_are_never_published_and_failed_refresh_preserves_news(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            root = Path(temp)
            for name in ('index.html', 'app.js', 'style.css'):
                (root / name).write_text('test')
            with patch.object(build, 'ROOT', root), patch.object(build.app, 'DATA', root / 'data'), patch.object(build.app, 'DB', root / 'data' / 'db.sqlite3'):
                build.app.init()
                now = build.app.now().isoformat()
                with build.app.connect() as c:
                    c.execute('INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?)', ('id','Erzurum haber','Kaynak','https://example.com',now,now,'["Yakutiye"]','Genel',1,'SECRET NOTE'))
                run = {'at': now, 'success': 6, 'total': 6, 'new': 1, 'sources': []}
                with patch.object(build.app, 'collect', return_value=run):
                    build.build()
                raw = (root / 'dist' / 'news.json').read_text(encoding='utf-8')
                self.assertNotIn('SECRET NOTE', raw)
                self.assertNotIn('"saved"', raw)
                self.assertEqual(len(json.loads(raw)['articles']), 1)
                with patch.object(build.app, 'collect', return_value={**run, 'success': 0}):
                    build.build()
                result = json.loads((root / 'dist' / 'news.json').read_text(encoding='utf-8'))
                self.assertEqual(len(result['articles']), 1)
                self.assertEqual(result['last_success'], now)

if __name__ == '__main__':
    unittest.main()
