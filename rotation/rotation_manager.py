"""
Kiro Rotation Manager

Coordinates account rotation when 402 or auth errors occur.
"""
import sys
from pathlib import Path
from datetime import datetime

# Support both relative and absolute imports
try:
    from .account_provider import (
        get_next_account,
        mark_email_used,
        mark_email_dead,
        get_last_active_email,
        get_fresh_account_from_db
    )
    from .kiro_auto_login import kiro_login
except ImportError:
    from account_provider import (
        get_next_account,
        mark_email_used,
        mark_email_dead,
        get_last_active_email,
        get_fresh_account_from_db
    )
    from kiro_auto_login import kiro_login


def log(msg: str):
    print(f"[ROTATION {datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def do_rotation() -> bool:
    """
    Perform account rotation.
    
    Returns True if successfully logged in with new account.
    """
    log("Starting rotation...")
    
    # Get next account
    account = get_next_account()
    
    if not account:
        log("ERROR: No account available for rotation")
        return False
    
    email = account["email"]
    password = account["password"]
    source = account.get("source", "unknown")
    
    log(f"Trying account: {email} (source: {source})")
    
    # Try login
    success = kiro_login(email, password)
    
    if success:
        log(f"SUCCESS: Logged in with {email}")
        mark_email_used(email, status="active")
        return True
    else:
        log(f"FAILED: Could not login with {email}")
        
        # If this was last_active, mark as dead and try fresh
        if source == "last_active":
            log("Marking as dead, trying fresh account...")
            mark_email_dead(email)
            
            fresh = get_fresh_account_from_db()
            if fresh:
                log(f"Trying fresh account: {fresh['email']}")
                success = kiro_login(fresh["email"], fresh["password"])
                if success:
                    mark_email_used(fresh["email"], status="active")
                    return True
                else:
                    mark_email_dead(fresh["email"])
        
        return False


def handle_402_error() -> bool:
    """Handle 402 (limit reached) error."""
    log("Handling 402 error - account limit reached")
    
    # Mark current account as needing rotation
    current = get_last_active_email()
    if current:
        log(f"Current account {current} hit limit")
        mark_email_dead(current)
    
    return do_rotation()


def handle_auth_error() -> bool:
    """Handle auth errors (No token, dispatch failure)."""
    log("Handling auth error")
    return do_rotation()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "402":
        success = handle_402_error()
    else:
        success = do_rotation()
    
    sys.exit(0 if success else 1)
