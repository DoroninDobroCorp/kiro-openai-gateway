"""
Kiro Account Rotation - Account Provider

Gets Google accounts from factory_accounts DB for Kiro login.
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List

# Add droid_new to path for DB access
DROID_NEW_PATH = Path(__file__).parent.parent.parent.parent / "droid_new"
sys.path.insert(0, str(DROID_NEW_PATH))

try:
    from core.factory_accounts_db import get_connection
except ImportError:
    get_connection = None

USED_EMAILS_FILE = Path.home() / ".kiro-gateway" / "used_emails.txt"


def _ensure_used_emails_file():
    """Create used_emails file if not exists."""
    USED_EMAILS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not USED_EMAILS_FILE.exists():
        USED_EMAILS_FILE.write_text("# email|status|last_used\n")


def get_used_emails() -> Dict[str, dict]:
    """Get dict of used emails with their status."""
    _ensure_used_emails_file()
    result = {}
    for line in USED_EMAILS_FILE.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("|")
        if len(parts) >= 2:
            email = parts[0]
            status = parts[1] if len(parts) > 1 else "active"
            last_used = parts[2] if len(parts) > 2 else ""
            result[email] = {"status": status, "last_used": last_used}
    return result


def mark_email_used(email: str, status: str = "active"):
    """Add or update email in used_emails file."""
    _ensure_used_emails_file()
    used = get_used_emails()
    used[email] = {"status": status, "last_used": datetime.now().isoformat()}
    
    lines = ["# email|status|last_used"]
    for e, info in used.items():
        lines.append(f"{e}|{info['status']}|{info['last_used']}")
    USED_EMAILS_FILE.write_text("\n".join(lines) + "\n")


def mark_email_dead(email: str):
    """Mark email as dead (doesn't work)."""
    mark_email_used(email, status="dead")


def get_last_active_email() -> Optional[str]:
    """Get last added active email."""
    used = get_used_emails()
    active = [(e, info) for e, info in used.items() if info["status"] == "active"]
    if not active:
        return None
    # Sort by last_used, return most recent
    active.sort(key=lambda x: x[1].get("last_used", ""), reverse=True)
    return active[0][0]


def get_fresh_account_from_db(max_age_hours: int = 10) -> Optional[Dict]:
    """
    Get fresh account from factory_accounts DB.
    
    Returns account that:
    - Created less than max_age_hours ago
    - Not already used for Kiro
    """
    if get_connection is None:
        print("Warning: factory_accounts_db not available")
        return None
    
    used = get_used_emails()
    used_list = list(used.keys())
    
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # Build query with exclusion list
            # OFFSET 1 to skip the most recent (current) account and get the second one
            if used_list:
                placeholders = ",".join(["%s"] * len(used_list))
                query = f"""
                    SELECT google_email, google_password
                    FROM factory_accounts
                    WHERE created_at > NOW() - INTERVAL '{max_age_hours} hours'
                      AND google_email NOT IN ({placeholders})
                      AND status IN ('active', 'pending')
                    ORDER BY created_at DESC
                    LIMIT 1 OFFSET 2
                """
                cursor.execute(query, used_list)
            else:
                cursor.execute(f"""
                    SELECT google_email, google_password
                    FROM factory_accounts
                    WHERE created_at > NOW() - INTERVAL '{max_age_hours} hours'
                      AND status IN ('active', 'pending')
                    ORDER BY created_at DESC
                    LIMIT 1 OFFSET 2
                """)
            
            row = cursor.fetchone()
            if row:
                return {"email": row[0], "password": row[1]}
            return None
    except Exception as e:
        print(f"DB error: {e}")
        return None


def get_account_password(email: str) -> Optional[str]:
    """Get password for email from DB."""
    if get_connection is None:
        return None
    
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT google_password FROM factory_accounts WHERE google_email = %s",
                (email,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception as e:
        print(f"DB error: {e}")
        return None


def get_next_account() -> Optional[Dict]:
    """
    Get next account for Kiro login.
    
    Priority:
    1. Last active email we used (re-login)
    2. Fresh account from DB (< 10 hours, not used)
    """
    # Try last active first
    last_email = get_last_active_email()
    if last_email:
        password = get_account_password(last_email)
        if password:
            return {"email": last_email, "password": password, "source": "last_active"}
    
    # Try fresh from DB
    fresh = get_fresh_account_from_db()
    if fresh:
        return {"email": fresh["email"], "password": fresh["password"], "source": "fresh_db"}
    
    return None


if __name__ == "__main__":
    print("Testing account provider...")
    print(f"Used emails file: {USED_EMAILS_FILE}")
    print(f"Used emails: {get_used_emails()}")
    print(f"Last active: {get_last_active_email()}")
    
    account = get_next_account()
    if account:
        print(f"Next account: {account['email']} (source: {account['source']})")
    else:
        print("No account available")
