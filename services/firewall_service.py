import subprocess
import sys
from pathlib import Path


def get_exe_path() -> str:
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable))
    return str(Path(sys.argv[0]).resolve())


def add_firewall_rule(app_name: str = "LAN-FT") -> tuple[bool, str]:
    """Try to add a Windows Firewall inbound rule. Returns (success, message)."""
    if check_rule_exists(app_name):
        return True, "Правило брандмауера вже існує."
    exe = get_exe_path()
    cmd = (
        f'netsh advfirewall firewall add rule name="{app_name}" '
        f'dir=in action=allow program="{exe}" enable=yes'
    )
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return True, "Правило брандмауера додано успішно."
        return False, result.stderr.strip() or result.stdout.strip()
    except PermissionError:
        return False, "Потрібні права адміністратора."
    except Exception as e:
        return False, str(e)


def check_rule_exists(app_name: str = "LAN-FT") -> bool:
    cmd = f'netsh advfirewall firewall show rule name="{app_name}"'
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and "No rules match" not in result.stdout
    except Exception:
        return False
