"""
Kiro Auto Login via Selenium

Opens kiro.dev in Chrome and performs Google OAuth.
Works with kiro-cli login flow.
"""
import os
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime

# Selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

CHROME_DEBUG_PORT = 9222
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def get_chrome_driver():
    """Connect to existing Chrome on debug port."""
    options = webdriver.ChromeOptions()
    options.add_experimental_option('debuggerAddress', f'127.0.0.1:{CHROME_DEBUG_PORT}')
    return webdriver.Chrome(options=options)


def start_chrome_if_needed():
    """Start Chrome with debug port if not running."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', CHROME_DEBUG_PORT))
    sock.close()
    
    if result != 0:
        log(f"Starting Chrome on port {CHROME_DEBUG_PORT}...")
        profile_dir = "/tmp/kiro_chrome_profile"
        os.makedirs(profile_dir, exist_ok=True)
        
        subprocess.Popen([
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            f"--remote-debugging-port={CHROME_DEBUG_PORT}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1440,900",
            "about:blank"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
        log("Chrome started")
    else:
        log("Chrome already running")


def screenshot(driver, name: str):
    """Save screenshot for debugging."""
    path = SCREENSHOTS_DIR / f"{name}_{int(time.time())}.png"
    try:
        driver.save_screenshot(str(path))
        log(f"Screenshot: {path}")
    except:
        pass


def get_kiro_login_url_from_yandex() -> str:
    """Get Kiro login URL from Yandex browser via AppleScript."""
    result = subprocess.run([
        "osascript", "-e",
        'tell application "Yandex" to get URL of active tab of front window'
    ], capture_output=True, text=True)
    
    url = result.stdout.strip()
    if "kiro.dev" in url:
        return url
    return ""


def wait_for_kiro_url(timeout: int = 10) -> str:
    """Wait for Kiro URL to appear in Yandex."""
    for _ in range(timeout):
        url = get_kiro_login_url_from_yandex()
        if url:
            return url
        time.sleep(1)
    return ""


def do_google_oauth(driver, email: str, password: str) -> bool:
    """
    Perform Google OAuth flow.
    Returns True if successful.
    """
    wait = WebDriverWait(driver, 15)
    
    try:
        # Step 1: Click "Sign in with Google" if on Kiro page
        current_url = driver.current_url
        log(f"Current URL: {current_url}")
        
        if "kiro.dev" in current_url and "accounts.google.com" not in current_url:
            try:
                google_btn = wait.until(EC.element_to_be_clickable((
                    By.XPATH, "//button[contains(., 'Google') or contains(., 'google')]"
                )))
                google_btn.click()
                log("Clicked Google sign-in button")
                time.sleep(2)
            except:
                log("No Google button found, might already be on OAuth page")
        
        screenshot(driver, "01_oauth_start")
        
        # Step 2: Enter email
        try:
            email_input = wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR, "input[type='email'], input#identifierId"
            )))
            email_input.clear()
            email_input.send_keys(email)
            log(f"Entered email: {email}")
            time.sleep(0.5)
            
            # Click Next
            next_btn = driver.find_element(By.CSS_SELECTOR, "#identifierNext, button[type='submit']")
            next_btn.click()
            log("Clicked Next after email")
            time.sleep(2)
        except TimeoutException:
            log("Email input not found - might be already logged in or different flow")
            screenshot(driver, "02_no_email_input")
        
        screenshot(driver, "03_after_email")
        
        # Step 3: Enter password
        try:
            password_input = wait.until(EC.presence_of_element_located((
                By.CSS_SELECTOR, "input[type='password'], input[name='Passwd']"
            )))
            password_input.clear()
            password_input.send_keys(password)
            log("Entered password")
            time.sleep(0.5)
            
            # Click Next
            next_btn = driver.find_element(By.CSS_SELECTOR, "#passwordNext, button[type='submit']")
            next_btn.click()
            log("Clicked Next after password")
            time.sleep(3)
        except TimeoutException:
            log("Password input not found")
            screenshot(driver, "04_no_password_input")
        
        screenshot(driver, "05_after_password")
        
        # Step 4: Handle consent/continue screens
        for i in range(5):
            time.sleep(2)
            current_url = driver.current_url
            log(f"Current URL: {current_url}")
            
            # Success - redirected to localhost (kiro-cli callback)
            if "localhost" in current_url:
                log("SUCCESS: Redirected to localhost callback")
                return True
            
            # Success - back on kiro.dev with success
            if "kiro.dev" in current_url and "success" in current_url:
                log("SUCCESS: Back on kiro.dev with success")
                return True
            
            # Try clicking Continue/Allow buttons
            try:
                for selector in [
                    "//button[contains(., 'Continue')]",
                    "//button[contains(., 'Allow')]",
                    "//button[contains(., 'Разрешить')]",
                    "//button[@id='confirm']",
                    "//input[@type='submit']"
                ]:
                    try:
                        btn = driver.find_element(By.XPATH, selector)
                        if btn.is_displayed():
                            driver.execute_script("arguments[0].click()", btn)
                            log(f"Clicked button: {selector}")
                            time.sleep(2)
                            break
                    except:
                        continue
            except:
                pass
            
            screenshot(driver, f"06_consent_{i}")
        
        # Check final state
        final_url = driver.current_url
        if "localhost" in final_url or ("kiro.dev" in final_url and "success" in final_url):
            return True
        
        log(f"OAuth flow ended at: {final_url}")
        return False
        
    except Exception as e:
        log(f"OAuth error: {e}")
        screenshot(driver, "error")
        return False


def kiro_login(email: str, password: str) -> bool:
    """
    Full Kiro login flow:
    1. Start kiro-cli login (opens Yandex)
    2. Get URL from Yandex
    3. Open URL in our Chrome
    4. Do Google OAuth
    5. kiro-cli gets callback and saves token
    """
    log(f"Starting Kiro login for {email}")
    
    # Logout first
    log("Logging out...")
    subprocess.run(["kiro-cli", "logout"], capture_output=True)
    time.sleep(1)
    
    # Start kiro-cli login in background
    log("Starting kiro-cli login...")
    kiro_proc = subprocess.Popen(
        ["kiro-cli", "login", "--social", "google"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    
    # Wait for URL in Yandex
    log("Waiting for Kiro URL in Yandex...")
    time.sleep(3)
    kiro_url = wait_for_kiro_url(timeout=10)
    
    if not kiro_url:
        log("ERROR: Could not get Kiro URL from Yandex")
        kiro_proc.kill()
        return False
    
    log(f"Got Kiro URL: {kiro_url[:80]}...")
    
    # Start Chrome and do OAuth
    start_chrome_if_needed()
    driver = get_chrome_driver()
    
    try:
        # Open Kiro URL in our Chrome
        log("Opening Kiro URL in Chrome...")
        driver.get(kiro_url)
        time.sleep(2)
        
        # Do OAuth
        success = do_google_oauth(driver, email, password)
        
        if success:
            log("OAuth successful, waiting for kiro-cli to finish...")
            # Wait for kiro-cli to get callback
            for _ in range(15):
                if kiro_proc.poll() is not None:
                    log("kiro-cli finished")
                    break
                time.sleep(1)
            
            # Verify token was saved
            time.sleep(2)
            token_check = subprocess.run(
                ["kiro-cli", "whoami"],
                capture_output=True,
                text=True
            )
            if token_check.returncode == 0:
                log(f"SUCCESS: Logged in as {token_check.stdout.strip()}")
                return True
            else:
                log("WARNING: kiro-cli whoami failed")
                return False
        else:
            log("OAuth failed")
            kiro_proc.kill()
            return False
            
    except Exception as e:
        log(f"Error: {e}")
        kiro_proc.kill()
        return False


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python kiro_auto_login.py <email> <password>")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    
    success = kiro_login(email, password)
    sys.exit(0 if success else 1)
