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
                    LIMIT 1
                """
                cursor.execute(query, used_list)
            else:
                cursor.execute(f"""
                    SELECT google_email, google_password
                    FROM factory_accounts
                    WHERE created_at > NOW() - INTERVAL '{max_age_hours} hours'
                      AND status IN ('active', 'pending')
                    ORDER BY created_at DESC
                    LIMIT 1
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


def create_new_account_task() -> Optional[Dict]:
    """
    Create a new account by adding buy_google task to droid_new queue.
    Waits for the account to appear in factory_accounts DB.
    
    Returns account dict or None if failed.
    """
    if get_connection is None:
        print("Warning: factory_accounts_db not available")
        return None
    
    import time
    
    print("[ROTATION] Creating new account via droid_new queue...")
    
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Get available google_code
            cursor.execute("""
                SELECT code_id, code FROM google_codes
                WHERE status = 'available'
                ORDER BY imported_at DESC
                LIMIT 1
            """)
            code_row = cursor.fetchone()
            
            if not code_row:
                print("[ROTATION] No available google_codes!")
                return None
            
            code_id, code = code_row
            print(f"[ROTATION] Using google_code id={code_id}")
            
            # 2. Mark code as reserved
            cursor.execute(
                "UPDATE google_codes SET status = 'reserved' WHERE code_id = %s",
                (code_id,)
            )
            
            # 3. Create buy_google task
            # NOTE: worker expects code_id in google_email field (legacy design)
            cursor.execute("""
                INSERT INTO registration_tasks
                    (task_type, device_code, google_email, max_attempts)
                VALUES ('buy_google', %s, %s, 10)
                RETURNING task_id
            """, (code, str(code_id)))
            task_id = cursor.fetchone()[0]
            conn.commit()
            
            print(f"[ROTATION] Created task #{task_id}, waiting for completion...")
            
            # 4. Poll for new account in factory_accounts (worker adds it there after buy)
            # As soon as Google account is bought, we can use it - no need to wait for Factory registration
            start_time = time.time()
            max_wait = 300  # 5 minutes (Google buy is fast, ~1-2 min)
            poll_interval = 10  # seconds
            
            while time.time() - start_time < max_wait:
                time.sleep(poll_interval)
                
                # Check task status first
                cursor.execute(
                    "SELECT status FROM registration_tasks WHERE task_id = %s",
                    (task_id,)
                )
                task = cursor.fetchone()
                
                if not task:
                    print(f"[ROTATION] Task #{task_id} not found!")
                    return None
                
                status = task[0]
                elapsed = int(time.time() - start_time)
                
                if status == 'failed':
                    print(f"[ROTATION] Task #{task_id} failed!")
                    return None
                
                # Check if account appeared in factory_accounts (linked via google_codes)
                cursor.execute("""
                    SELECT fa.google_email, fa.google_password 
                    FROM factory_accounts fa
                    JOIN google_codes gc ON gc.factory_account_id = fa.account_id
                    WHERE gc.code_id = %s
                """, (code_id,))
                account = cursor.fetchone()
                
                if account and account[0] and account[1]:
                    email, password = account
                    print(f"[ROTATION] Google account ready: {email} ({elapsed}s)")
                    return {"email": email, "password": password, "source": "new_task"}
                
                print(f"[ROTATION] Task #{task_id} status: {status}, waiting... ({elapsed}s)")
            
            print(f"[ROTATION] Timeout waiting for task #{task_id}")
            return None
            
    except Exception as e:
        print(f"[ROTATION] Error creating new account: {e}")
        return None


def get_next_account() -> Optional[Dict]:
    """
    Get next account for Kiro login.
    
    Priority:
    1. Last active email we used (re-login)
    2. Fresh account from DB (< 24 hours, not dead)
    3. Create new account via droid_new queue
    """
    # Get dead emails to exclude
    used = get_used_emails()
    dead_emails = [e for e, info in used.items() if info["status"] == "dead"]
    
    # Try last active first (if not dead)
    last_email = get_last_active_email()
    if last_email and last_email not in dead_emails:
        password = get_account_password(last_email)
        if password:
            return {"email": last_email, "password": password, "source": "last_active"}
    
    # Try fresh from DB (increased to 24 hours)
    fresh = get_fresh_account_from_db(max_age_hours=24)
    if fresh and fresh["email"] not in dead_emails:
        return {"email": fresh["email"], "password": fresh["password"], "source": "fresh_db"}
    
    # DISABLED: Fallback to create new account via droid_new - too complex
    # print("[ROTATION] No existing accounts available, creating new one...")
    # new_account = create_new_account_task()
    # if new_account:
    #     return new_account
    
    print("[ROTATION] No existing accounts available!")
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
