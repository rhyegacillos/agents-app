import os
from mangum import Mangum
from server import app

# v3: no Kaleido/Chrome. Keep Lambda writable dirs safe defaults.
os.environ.setdefault("HOME", "/tmp")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp")

# (Optional) If Graphviz needs a writable temp dir explicitly:
os.environ.setdefault("TMPDIR", "/tmp")

handler = Mangum(app)
