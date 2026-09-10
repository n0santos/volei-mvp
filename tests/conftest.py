import os
import tempfile

# app.database builds its engine at import time from DB_PATH; point it at a
# throwaway file so importing app.main never touches the real volei.db.
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
