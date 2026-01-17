"""
Kiro Rotation Manager

Coordinates account rotation when 402 or auth errors occur.
Standalone version - no droid_new dependency.
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

try:
    from .account_provider import (
        get_next_account, mark_email_used, mark_email_dead, get_last_active_email,
    )
    from .kiro_auto_login import kiro_login
except ImportError:
    from account_provider import (
        get_next_account, mark_email_used, mark_email_dead, get_last_active_email,
    )
    from kiro_auto_login import kiro_login

# Safety limits
MAX_ROTATIONS_PER_HOUR = 3
ROTATION_STATE_FILE = Path.home() / ".kiro-gateway" / "rotation_state.json"


def log(msg: str):
    print(f"[ROTATION {datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _load_rotation_state() -> dict:
    if not ROTATION_STATE_FILE.exists():
        return {"rotations": []}
    try:
        return json.loads(ROTATION_STATE_FILE.read_text())
    except:
        return {"rotations": []}


def _save_rotation_state(state: dict):
    ROTATION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ROTATION_STATE_FILE.write_text(json.dumps(state, indent=2))


def _record_rotation():
    state = _load_rotation_state()
    state["rotations"].append(datetime.now().isoformat())
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    state["rotations"] = [r for r in state["rotations"] if r > cutoff]
    _save_rotation_state(state)


def _get_rotations_last_hour() -> int:
    state = _load_rotation_state()
    cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
    return len([r for r in state["rotations"] if r > cutoff])


def check_rotation_limit() -> bool:
    count = _get_rotations_last_hour()
    if count >= MAX_ROTATIONS_PER_HOUR:
        log(f"SAFETY LIMIT: {count} rotations in last hour (max {MAX_ROTATIONS_PER_HOUR})")
        log("Waiting for human intervention to prevent burning all accounts")
        return False
    return True


def reset_rotation_limit():
    _save_rotation_state({"rotations": []})
    log("Rotation limit reset by human")


def check_network() -> bool:
    import socket
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


def do_rotation() -> bool:
    log("Starting rotation...")
    
    if not check_rotation_limit():
        return False
    
    if not check_network():
        log("ERROR: No network connection")
        return False
    
    account = get_next_account()
    if not account:
        log("ERROR: No account available")
        return False
    
    email, password = account["email"], account["password"]
    source = account.get("source", "unknown")
    log(f"Trying account: {email} (source: {source})")
    
    _record_rotation()
    
    if kiro_login(email, password):
        log(f"SUCCESS: Logged in with {email}")
        mark_email_used(email, status="active")
        return True
    else:
        log(f"FAILED: Could not login with {email}")
        mark_email_dead(email)
        return False


def handle_402_error() -> bool:
    log("Handling 402 error - account limit reached")
    current = get_last_active_email()
    if current:
        log(f"Current account {current} hit limit")
        mark_email_dead(current)
    return do_rotation()


def handle_auth_error() -> bool:
    log("Handling auth error")
    return do_rotation()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "402":
            success = handle_402_error()
        elif sys.argv[1] == "reset":
            reset_rotation_limit()
            print("Rotation limit reset")
            sys.exit(0)
        elif sys.argv[1] == "status":
            print(f"Rotations in last hour: {_get_rotations_last_hour()}/{MAX_ROTATIONS_PER_HOUR}")
            sys.exit(0)
        else:
            success = do_rotation()
    else:
        success = do_rotation()
    sys.exit(0 if success else 1)
