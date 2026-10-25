"""
VitaranIQ Engine Server Launcher
Run this script to launch the FastAPI backend server and executive dashboard.

Usage:
    python run_vitaraniq.py
"""

import sys
import subprocess
from pathlib import Path

# Auto-detect and delegate to backend/.venv if current python interpreter lacks dependencies
venv_python = Path(__file__).resolve().parent / "backend" / ".venv" / "Scripts" / "python.exe"
if venv_python.exists() and sys.executable.lower() != str(venv_python).lower():
    try:
        import sqlalchemy
        import uvicorn
    except ImportError:
        ret = subprocess.run([str(venv_python), str(Path(__file__).resolve())] + sys.argv[1:])
        sys.exit(ret.returncode)

import uvicorn

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from vitaraniq.db.session import get_db_path, get_sqlite_connection
from vitaraniq.db.schema import init_db
from vitaraniq.services.data_svc import DataService

def main():
    print("=" * 65)
    print("  VitaranIQ: AI-Powered FMCG Distribution Intelligence Engine")
    print("  Problem Statement 2 | Innovate-x (Lead: Devendra Nimbalkar)")
    print("=" * 65)

    db_path = get_db_path()
    conn = get_sqlite_connection(db_path)
    init_db(conn)

    # Check if dataset seed 42 exists; if not, seed automatically
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM datasets WHERE seed = 42;")
    if cur.fetchone()[0] == 0:
        print("[*] Initializing canonical dataset (seed=42, 219k records)...")
        conn.close()
        DataService.generate_and_save(seed=42, db_path=db_path)
        print("[+] Canonical dataset ready.")
    else:
        conn.close()
        print("[+] Database loaded with active dataset.")

    print("\n[+] Launching VitaranIQ Engine at http://127.0.0.1:8000")
    print("    - Executive Dashboard: http://127.0.0.1:8000/")
    print("    - Interactive API Docs: http://127.0.0.1:8000/docs")
    print("    - Health Endpoint:      http://127.0.0.1:8000/api/v1/health")
    print("\nPress Ctrl+C to terminate.")

    uvicorn.run("vitaraniq.api.main:app", host="127.0.0.1", port=8000, reload=False)

if __name__ == "__main__":
    main()
