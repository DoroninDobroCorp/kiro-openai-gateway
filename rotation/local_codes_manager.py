"""
Local Google Codes Manager for Kirodroid

Standalone codes management without droid_new dependency.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

CODES_FILE = Path(__file__).parent.parent / "data" / "google_codes.txt"
STATE_FILE = Path.home() / ".kiro-gateway" / "codes_state.json"
USED_CODES_FILE = Path.home() / ".kiro-gateway" / "used_codes.txt"


def _load_codes_from_file() -> List[Dict]:
    """Load codes from text file."""
    if not CODES_FILE.exists():
        return []
    
    codes = []
    with open(CODES_FILE, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            if '|' in line:
                parts = line.split('|', 1)
                code = parts[0].strip()
                api_url = parts[1].strip() if len(parts) > 1 else "https://sv5.api999api.com/google/"
                codes.append({
                    "code": code,
                    "api_url": api_url,
                    "line_number": line_num
                })
    return codes


def _get_used_codes() -> Dict[str, dict]:
    """Get dict of used codes from tracking file."""
    if not USED_CODES_FILE.exists():
        return {}
    
    result = {}
    for line in USED_CODES_FILE.read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("|")
        if len(parts) >= 2:
            code = parts[0]
            status = parts[1] if len(parts) > 1 else "used"
            last_used = parts[2] if len(parts) > 2 else ""
            result[code] = {"status": status, "last_used": last_used}
    return result


def _mark_code_used(code: str, status: str = "used"):
    """Add or update code in used_codes file."""
    USED_CODES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not USED_CODES_FILE.exists():
        USED_CODES_FILE.write_text("# code|status|last_used\n")
    
    used = _get_used_codes()
    used[code] = {"status": status, "last_used": datetime.now().isoformat()}
    
    lines = ["# code|status|last_used"]
    for c, info in used.items():
        lines.append(f"{c}|{info['status']}|{info['last_used']}")
    USED_CODES_FILE.write_text("\n".join(lines) + "\n")


def get_next_code() -> Optional[Dict]:
    """
    Get next available code.
    
    Returns code dict or None if no codes available.
    """
    all_codes = _load_codes_from_file()
    used_codes = _get_used_codes()
    
    for code_info in all_codes:
        code = code_info["code"]
        if code not in used_codes:
            return code_info
    
    return None


def mark_code_success(code: str, email: str):
    """Mark code as successfully used."""
    _mark_code_used(code, status="success")
    print(f"[CODES] Code {code[:8]}... marked success -> {email}")


def mark_code_invalid(code: str, reason: str = "invalid"):
    """Mark code as invalid/expired."""
    _mark_code_used(code, status=f"invalid:{reason[:20]}")
    print(f"[CODES] Code {code[:8]}... marked invalid: {reason}")


def get_stats() -> Dict:
    """Get codes statistics."""
    all_codes = _load_codes_from_file()
    used_codes = _get_used_codes()
    
    success = sum(1 for c in used_codes.values() if c["status"] == "success")
    invalid = sum(1 for c in used_codes.values() if c["status"].startswith("invalid"))
    available = len(all_codes) - len(used_codes)
    
    return {
        "total": len(all_codes),
        "available": max(0, available),
        "success": success,
        "invalid": invalid,
        "used_total": len(used_codes)
    }


def print_stats():
    """Print statistics to console."""
    stats = get_stats()
    print("=" * 50)
    print("Kirodroid Local Codes Statistics")
    print("=" * 50)
    print(f"Total in file:  {stats['total']}")
    print(f"Available:      {stats['available']}")
    print(f"Used (success): {stats['success']}")
    print(f"Invalid:        {stats['invalid']}")
    print("=" * 50)


if __name__ == "__main__":
    print_stats()
    
    next_code = get_next_code()
    if next_code:
        print(f"\nNext available: {next_code['code'][:8]}...")
    else:
        print("\nNo codes available!")
