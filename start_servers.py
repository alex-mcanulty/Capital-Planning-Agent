"""Start all servers for the Capital Planning system in separate PowerShell windows"""
import subprocess
import sys
import time
from pathlib import Path

def start_powershell_server(name, command, cwd=None):
    """Start a server in a new PowerShell window"""
    print(f"Starting {name} in new PowerShell window...")

    # Convert path to string and escape it
    working_dir = str(cwd) if cwd else str(Path.cwd())

    # Build PowerShell command that keeps window open
    # Use -NoExit to keep window open, and proper escaping
    ps_args = [
        'powershell.exe',
        '-NoExit',
        '-Command',
        f'cd "{working_dir}"; {command}'
    ]

    process = subprocess.Popen(
        ps_args,
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    return process

def main():
    base_dir = Path(__file__).parent

    print("=" * 70)
    print("Capital Planning System - Starting All Servers")
    print("=" * 70)
    print()
    print("Each server will open in a separate PowerShell window")
    print("You can see logs in each window")
    print()

    # Start OIDC server
    start_powershell_server(
        "OIDC Server (port 8000)",
        "uv run python -m oidc_server.main",
        cwd=base_dir
    )
    time.sleep(2)

    # Start Services
    start_powershell_server(
        "Services API (port 8001)",
        "uv run python -m services.main",
        cwd=base_dir
    )
    time.sleep(2)

    # Start Frontend
    frontend_dir = base_dir / "frontend"
    start_powershell_server(
        "Frontend Server (port 8080)",
        "uv run python -m http.server 8080",
        cwd=frontend_dir
    )

    print()
    print("=" * 70)
    print("All servers started in separate PowerShell windows!")
    print("=" * 70)
    print()
    print("Services running:")
    print("  - OIDC Server:    http://localhost:8000    (PowerShell window 1)")
    print("  - Services API:   http://localhost:8001    (PowerShell window 2)")
    print("  - Frontend:       http://localhost:8080    (PowerShell window 3)")
    print()
    print("Open http://localhost:8080 in your browser to start testing")
    print()
    print("To stop servers: Close each PowerShell window or press Ctrl+C in them")
    print("You can close this window now - the servers will keep running")
    print("=" * 70)

if __name__ == "__main__":
    main()
