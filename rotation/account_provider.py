"""
Kiro Account Rotation - Account Provider

Standalone version - no droid_new dependency.
Uses local codes file for buying Google accounts.
"""
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

from .local_codes_manager import get_next_code, mark_code_success, mark_code_invalid, get_stats

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
    active.sort(key=lambda x: x[1].get("last_used", ""), reverse=True)
    return active[0][0]


def get_account_password(email: str) -> Optional[str]:
    """
    Get password for email from local storage.
    
    Passwords are stored in ~/.kiro-gateway/passwords.txt
    Format: email|password
    """
    passwords_file = Path.home() / ".kiro-gateway" / "passwords.txt"
    if not passwords_file.exists():
        return None
    
    for line in passwords_file.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("|")
        if len(parts) >= 2 and parts[0] == email:
            return parts[1]
    return None


def _save_password(email: str, password: str):
    """Save email/password to local storage."""
    passwords_file = Path.home() / ".kiro-gateway" / "passwords.txt"
    passwords_file.parent.mkdir(parents=True, exist_ok=True)
    
    if not passwords_file.exists():
        passwords_file.write_text("# email|password\n")
    
    # Check if already exists
    existing = passwords_file.read_text()
    if email in existing:
        return
    
    with open(passwords_file, "a") as f:
        f.write(f"{email}|{password}\n")


def _check_code_history(code: str, api_url: str) -> Optional[Dict]:
    """
    Check code status via history.php before using api.php.
    
    Returns:
        - {"status": "fresh"} - Balance 1, no email yet, safe to activate
        - {"status": "activated", "email": ..., "password": ..., "timestamp": ...} - Already activated, check age
        - {"status": "expired"} - Balance 0, no email or too old
        - None - API error
    """
    import requests
    import re
    
    url = f"{api_url}history.php?key_value={code}"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            return None
        
        text = resp.text
        
        # Parse balance
        balance_match = re.search(r'Balance:\s*(\d+)', text)
        balance = int(balance_match.group(1)) if balance_match else 0
        
        # Parse email/password/timestamp from table
        # Format: <td>2026-01-14 13:27:34</td><td>email@domain</td><td>password</td>
        row_match = re.search(r'<td>(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})</td><td>([^<]+@[^<]+)</td><td>([^<]+)</td>', text)
        
        if balance == 1 and not row_match:
            return {"status": "fresh"}
        
        if row_match:
            timestamp_str = row_match.group(1)
            email = row_match.group(2).strip()
            password = row_match.group(3).strip()
            return {
                "status": "activated",
                "email": email,
                "password": password,
                "timestamp": timestamp_str
            }
        
        return {"status": "expired"}
        
    except Exception as e:
        print(f"[ROTATION] history.php error: {e}")
        return None


def _is_timestamp_fresh(timestamp_str: str, max_hours: int = 12) -> bool:
    """Check if timestamp (China timezone) is within max_hours."""
    from datetime import datetime, timedelta, timezone
    
    try:
        # Parse China time (UTC+8)
        china_tz = timezone(timedelta(hours=8))
        activated_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=china_tz)
        now_china = datetime.now(china_tz)
        age = now_china - activated_time
        return age.total_seconds() < max_hours * 3600
    except Exception as e:
        print(f"[ROTATION] Timestamp parse error: {e}")
        return False


def buy_account_from_code() -> Optional[Dict]:
    """
    Buy a new Google account using an available code from local file.
    
    Algorithm:
    1. Get next available code
    2. Check history.php first:
       - Balance 1, no email -> fresh code, call api.php to activate
       - Balance 0, has email with timestamp < 12h -> use that email directly
       - Balance 0, timestamp > 12h or no email -> truly expired, skip
    3. Loop until success or no codes left
    
    Returns account dict or None if failed.
    """
    import requests
    
    max_attempts = 50  # Safety limit
    attempts = 0
    
    while attempts < max_attempts:
        attempts += 1
        
        code_info = get_next_code()
        if not code_info:
            print("[ROTATION] No available codes!")
            stats = get_stats()
            print(f"[ROTATION] Stats: {stats}")
            return None
        
        code = code_info["code"]
        api_url = code_info.get("api_url", "https://sv5.api999api.com/google/")
        
        print(f"[ROTATION] Trying code {code[:8]}...")
        
        # Step 1: Check history.php first
        history = _check_code_history(code, api_url)
        
        if history is None:
            print(f"[ROTATION] Code {code[:8]}... history check failed, trying api.php...")
            # Fall through to api.php
        elif history["status"] == "expired":
            print(f"[ROTATION] Code {code[:8]}... truly expired (balance 0, no valid email)")
            mark_code_invalid(code, "expired_confirmed")
            continue
        elif history["status"] == "activated":
            # Already activated - check if fresh enough
            email = history["email"]
            password = history["password"]
            timestamp = history["timestamp"]
            
            if _is_timestamp_fresh(timestamp, max_hours=12):
                print(f"[ROTATION] Code {code[:8]}... already activated {timestamp}, using existing: {email}")
                
                # Check if this email was already used by us
                used = get_used_emails()
                if email in used:
                    print(f"[ROTATION] Email {email} already used by us (status: {used[email]['status']})")
                    mark_code_invalid(code, "email_reused")
                    continue
                
                # Use this email directly
                _save_password(email, password)
                mark_code_success(code, email)
                mark_email_used(email, status="active")
                
                return {
                    "email": email,
                    "password": password,
                    "source": "history_recovery",
                    "code": code
                }
            else:
                print(f"[ROTATION] Code {code[:8]}... activated too long ago ({timestamp}), expired")
                mark_code_invalid(code, "too_old")
                continue
        elif history["status"] == "fresh":
            print(f"[ROTATION] Code {code[:8]}... is fresh (balance 1), activating...")
            # Fall through to api.php to activate
        
        # Step 2: Call api.php to activate (for fresh codes or history check failed)
        url = f"{api_url}api.php?key_value={code}"
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200:
                text = resp.text.strip()
                if '|' in text and '@' in text:
                    email, password = text.split('|')[:2]
                    email = email.strip()
                    password = password.strip()
                    
                    # Check if this email was already used
                    used = get_used_emails()
                    if email in used:
                        print(f"[ROTATION] Email {email} already used (status: {used[email]['status']})")
                        mark_code_invalid(code, "email_reused")
                        continue
                    
                    print(f"[ROTATION] Got account: {email}")
                    
                    _save_password(email, password)
                    mark_code_success(code, email)
                    mark_email_used(email, status="active")
                    
                    return {
                        "email": email,
                        "password": password,
                        "source": "new_code",
                        "code": code
                    }
                else:
                    # api.php returned error - but maybe history.php has the email
                    # Re-check history in case of race condition
                    print(f"[ROTATION] api.php returned: {text[:50]}, re-checking history...")
                    history2 = _check_code_history(code, api_url)
                    if history2 and history2["status"] == "activated":
                        email = history2["email"]
                        password = history2["password"]
                        
                        used = get_used_emails()
                        if email not in used:
                            print(f"[ROTATION] Found email in history after api.php error: {email}")
                            _save_password(email, password)
                            mark_code_success(code, email)
                            mark_email_used(email, status="active")
                            return {
                                "email": email,
                                "password": password,
                                "source": "history_after_error",
                                "code": code
                            }
                    
                    print(f"[ROTATION] Code {code[:8]}... invalid: {text[:50]}")
                    mark_code_invalid(code, text[:30])
                    continue
            else:
                print(f"[ROTATION] API error: {resp.status_code}")
                mark_code_invalid(code, f"http_{resp.status_code}")
                continue
                
        except requests.Timeout:
            print(f"[ROTATION] API timeout for code {code[:8]}...")
            mark_code_invalid(code, "timeout")
            continue
        except Exception as e:
            print(f"[ROTATION] API request failed: {e}")
            mark_code_invalid(code, str(e)[:30])
            continue
    
    print(f"[ROTATION] Exhausted {max_attempts} attempts")
    return None


def get_next_account() -> Optional[Dict]:
    """
    Get next account for Kiro login.
    
    Priority:
    1. Last active email we used (re-login) - but only if not dead
    2. Buy new account from code
    """
    used = get_used_emails()
    
    # Try last active first (if not dead)
    last_email = get_last_active_email()
    if last_email:
        last_status = used.get(last_email, {}).get("status", "unknown")
        if last_status != "dead":
            password = get_account_password(last_email)
            if password:
                print(f"[ROTATION] Using last active email: {last_email}")
                return {"email": last_email, "password": password, "source": "last_active"}
        else:
            print(f"[ROTATION] Last active email {last_email} is marked dead, skipping")
    
    # Buy new account from code
    print("[ROTATION] No existing active accounts available, buying from code...")
    new_account = buy_account_from_code()
    if new_account:
        return new_account
    
    print("[ROTATION] No accounts available!")
    return None


if __name__ == "__main__":
    from .local_codes_manager import print_stats
    
    print("Testing account provider...")
    print(f"Used emails file: {USED_EMAILS_FILE}")
    print(f"Used emails: {get_used_emails()}")
    print(f"Last active: {get_last_active_email()}")
    print()
    print_stats()
    
    account = get_next_account()
    if account:
        print(f"\nNext account: {account['email']} (source: {account['source']})")
    else:
        print("\nNo account available")
