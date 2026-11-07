import sys, os, urllib.request, tempfile

BASE = os.environ.get('PYSYSCALE_BASE') or 'https://hanguangxingchen.top/pypsyScale/'

MODULES = (
    ('schema', 'py/schema.py'),
    ('item_parser', 'py/item_parser.py'),
    ('scoring', 'py/scoring.py'),
    ('fetch', 'tui/fetch.py'),
    ('app', 'tui/app.py'),
)

TMP = tempfile.mkdtemp(prefix='pysyscale-')


def grab(name, rel):
    req = urllib.request.Request(BASE + rel, headers={'User-Agent': 'pysyscale-tui'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        with open(os.path.join(TMP, name + '.py'), 'wb') as fh:
            fh.write(resp.read())


for name, rel in MODULES:
    grab(name, rel)

sys.path.insert(0, TMP)
import app
app.main()