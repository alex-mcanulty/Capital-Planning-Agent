"""Start all servers for the Capital Planning system in separate windows.

Uses Windows Terminal if available, otherwise falls back to PowerShell
with QuickEdit mode disabled to prevent console freezing on click.
"""
import ctypes
import subprocess
import shutil
import sys
import time
from pathlib import Path


def find_windows_terminal():
    """Find Windows Terminal executable"""
    # Check if wt.exe is in PATH
    wt_path = shutil.which('wt.exe') or shutil.which('wt')
    if wt_path:
        return wt_path

    # Check common installation locations
    local_app_data = Path.home() / 'AppData' / 'Local'
    possible_paths = [
        # Microsoft Store installation
        local_app_data / 'Microsoft' / 'WindowsApps' / 'wt.exe',
        # Scoop installation
        Path.home() / 'scoop' / 'apps' / 'windows-terminal' / 'current' / 'wt.exe',
    ]

    for p in possible_paths:
        if p.exists():
            return str(p)

    return None


def start_server_process(name, command, cwd=None, wt_path=None):
    """Start a server in a new Windows Terminal tab or PowerShell window"""
    print(f"Starting {name}...")

    working_dir = str(cwd) if cwd else str(Path.cwd())

    if wt_path:
        # Use Windows Terminal (no QuickEdit issues)
        wt_args = [
            wt_path,
            'new-tab',
            '--title', name,
            '-d', working_dir,
            'powershell.exe', '-NoExit', '-Command', command
        ]
        process = subprocess.Popen(wt_args)
    else:
        # Launch via a wrapper that disables QuickEdit using ctypes
        disable_quickedit = (
            "import ctypes; "
            "k=ctypes.windll.kernel32; "
            "h=k.GetStdHandle(-10); "
            "m=ctypes.c_ulong(); "
            "k.GetConsoleMode(h,ctypes.byref(m)); "
            "k.SetConsoleMode(h,(m.value&~64)|128)"
        )
        wrapper_cmd = f'python -c "{disable_quickedit}"; {command}'

        ps_args = [
            'powershell.exe',
            '-NoExit',
            '-Command',
            f'$Host.UI.RawUI.WindowTitle = "{name}"; cd "{working_dir}"; {wrapper_cmd}'
        ]
        process = subprocess.Popen(ps_args, creationflags=subprocess.CREATE_NEW_CONSOLE)

    return process

def main():
    base_dir = Path(__file__).parent

    print("=" * 70)
    print("Capital Planning System - Starting All Servers")
    print("=" * 70)
    print()

    # Try to find Windows Terminal
    wt_path = find_windows_terminal()
    if wt_path:
        print(f"Using Windows Terminal: {wt_path}")
        print("Each server will open in a separate Windows Terminal tab")
    else:
        print("Windows Terminal not found, using PowerShell windows")
        print("(Tip: Install Windows Terminal to avoid QuickEdit freezing issues)")
    print()

    # Start OIDC server
    start_server_process(
        "OIDC Server (port 8000)",
        "uv run python -m oidc_server.main",
        cwd=base_dir,
        wt_path=wt_path
    )
    time.sleep(2)

    # Start Services
    start_server_process(
        "Services API (port 8001)",
        "uv run python -m services.main",
        cwd=base_dir,
        wt_path=wt_path
    )
    time.sleep(2)

    # Start MCP Server
    start_server_process(
        "MCP Server (streamable-http on port 8002)",
        "uv run python -m mcp_server.main",
        cwd=base_dir,
        wt_path=wt_path
    )
    time.sleep(2)

    # Start Agent Service
    start_server_process(
        "Agent Service (port 8003)",
        "uv run python -m agent.main",
        cwd=base_dir,
        wt_path=wt_path
    )
    time.sleep(2)

    # Start Frontend
    frontend_dir = base_dir / "frontend"
    start_server_process(
        "Frontend Server (port 8080)",
        "uv run python -m http.server 8080",
        cwd=frontend_dir,
        wt_path=wt_path
    )

    print()
    print("=" * 70)
    print("All servers started!")
    print("=" * 70)
    print()
    print("Services running:")
    print("  - OIDC Server:    http://localhost:8000")
    print("  - Services API:   http://localhost:8001")
    print("  - MCP Server:     http://localhost:8002")
    print("  - Agent Service:  http://localhost:8003")
    print("  - Frontend:       http://localhost:8080")
    print()
    print("Open http://localhost:8080 in your browser to start testing")
    print()
    print("To stop servers: Close each tab/window or press Ctrl+C in them")
    print("You can close this window now - the servers will keep running")
    print("=" * 70)

if __name__ == "__main__":
    main()
