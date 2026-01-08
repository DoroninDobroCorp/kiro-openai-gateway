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


def buy_account_from_code() -> Optional[Dict]:
    """
    Buy a new Google account using an available code from local file.
    
    1. Get available code from local codes file
    2. Call API to get email|password
    3. Save password locally
    4. Mark code as used
    
    Returns account dict or None if failed.
    """
    import requests
    
    code_info = get_next_code()
    if not code_info:
        print("[ROTATION] No available codes!")
        stats = get_stats()
        print(f"[ROTATION] Stats: {stats}")
        return None
    
    code = code_info["code"]
    api_url = code_info.get("api_url", "https://sv5.api999api.com/google/")
    
    print(f"[ROTATION] Trying code {code[:8]}...")
    
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
                    return None
                
                print(f"[ROTATION] Got account: {email}")
                
                # Save password locally
                _save_password(email, password)
                
                # Mark code as success
                mark_code_success(code, email)
                mark_email_used(email, status="active")
                
                return {
                    "email": email,
                    "password": password,
                    "source": "new_code",
                    "code": code
                }
            else:
                print(f"[ROTATION] Code {code[:8]}... invalid: {text[:50]}")
                mark_code_invalid(code, text[:30])
                return None
        else:
            print(f"[ROTATION] API error: {resp.status_code}")
            mark_code_invalid(code, f"http_{resp.status_code}")
            return None
            
    except requests.Timeout:
        print(f"[ROTATION] API timeout for code {code[:8]}...")
        mark_code_invalid(code, "timeout")
        return None
    except Exception as e:
        print(f"[ROTATION] API request failed: {e}")
        mark_code_invalid(code, str(e)[:30])
        return None


def get_next_account() -> Optional[Dict]:
    """
    Get next account for Kiro login.
    
    Priority:
    1. Last active email we used (re-login)
    2. Buy new account from code
    """
    used = get_used_emails()
    dead_emails = [e for e, info in used.items() if info["status"] == "dead"]
    
    # Try last active first (if not dead)
    last_email = get_last_active_email()
    if last_email and last_email not in dead_emails:
        password = get_account_password(last_email)
        if password:
            return {"email": last_email, "password": password, "source": "last_active"}
    
    # Buy new account from code
    print("[ROTATION] No existing accounts available, buying from code...")
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
