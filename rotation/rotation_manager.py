"""
Kiro Rotation Manager

Coordinates account rotation when 402 or auth errors occur.
Standalone version - no droid_new dependency.
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
    )
    from .kiro_auto_login import kiro_login
except ImportError:
    from account_provider import (
        get_next_account,
        mark_email_used,
        mark_email_dead,
        get_last_active_email,
    )
    from kiro_auto_login import kiro_login


def log(msg: str):
    print(f"[ROTATION {datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def do_rotation() -> bool:
    """
    Perform account rotation.
    
    Returns True if successfully logged in with new account.
    
    Strategy:
    1. Try existing account from DB
    2. If login fails - mark as dead
    3. If no working accounts - CREATE NEW via droid_new queue
    """
    log("Starting rotation...")
    
    # Get next account (will try last_active, then fresh_db, then create_new)
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
        mark_email_dead(email)
        
        # DISABLED: Creating new accounts via droid_new - too complex, doesn't work reliably
        # if source in ("last_active", "fresh_db"):
        #     log("Existing account failed, creating NEW account via droid_new...")
        #     new_account = create_new_account_task()
        #     if new_account:
        #         log(f"New account created: {new_account['email']}")
        #         success = kiro_login(new_account["email"], new_account["password"])
        #         if success:
        #             log(f"SUCCESS: Logged in with NEW account {new_account['email']}")
        #             mark_email_used(new_account["email"], status="active")
        #             return True
        #         else:
        #             log(f"FAILED: Could not login with new account")
        #             mark_email_dead(new_account["email"])
        
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
