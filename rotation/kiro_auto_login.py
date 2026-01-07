"""
Kiro Auto Login via Selenium
Based on droid_new/autoclicker/register.py
"""
import os
import sys
import time
import subprocess
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

CHROME_DEBUG_PORT = 9223  # Use different port than droid_new (9222)
KIRO_CLI_PATH = "/Users/vladimirdoronin/.local/bin/kiro-cli"


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def get_chrome_driver():
    options = webdriver.ChromeOptions()
    options.add_experimental_option('debuggerAddress', f'127.0.0.1:{CHROME_DEBUG_PORT}')
    return webdriver.Chrome(options=options)


CHROME_PROFILE_DIR = "/tmp/kiro_chrome_profile"


def kill_chrome():
    """Kill only our debug Chrome on port 9223, not Yandex or user's Chrome."""
    log(f"Killing Chrome on port {CHROME_DEBUG_PORT}...")
    # Kill only processes listening on our debug port
    subprocess.run(["lsof", "-ti", f":{CHROME_DEBUG_PORT}"], capture_output=True)
    result = subprocess.run(
        f"lsof -ti:{CHROME_DEBUG_PORT} | xargs kill -9 2>/dev/null",
        shell=True, capture_output=True
    )
    subprocess.run(["pkill", "-9", "chromedriver"], capture_output=True)
    time.sleep(1)
    
    # Remove profile dir to start completely fresh (no cached accounts)
    import shutil
    if os.path.exists(CHROME_PROFILE_DIR):
        log(f"Removing Chrome profile: {CHROME_PROFILE_DIR}")
        shutil.rmtree(CHROME_PROFILE_DIR, ignore_errors=True)
    time.sleep(1)


def start_chrome_if_needed(force_restart: bool = True):
    import socket
    
    if force_restart:
        kill_chrome()
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', CHROME_DEBUG_PORT))
    sock.close()
    
    if result != 0:
        log(f"Starting Chrome on port {CHROME_DEBUG_PORT}...")
        subprocess.Popen([
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            f"--remote-debugging-port={CHROME_DEBUG_PORT}",
            f"--user-data-dir={CHROME_PROFILE_DIR}",
            "--no-first-run", "--no-default-browser-check",
            "--disable-background-mode",
            "--window-size=1440,900", "about:blank"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Wait for Chrome to actually start and be ready
        for _ in range(10):
            time.sleep(1)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', CHROME_DEBUG_PORT))
            sock.close()
            if result == 0:
                log("Chrome is ready")
                break
        else:
            log("Warning: Chrome may not be ready")


def handle_chrome_popup(driver):
    """Handle Chrome 'Sign in to Chrome?' popup via Shadow DOM."""
    if "chrome://" not in driver.current_url:
        return False
    try:
        log(f"Chrome popup: {driver.current_url}")
        result = driver.execute_script('''
            var app = document.querySelector('managed-user-profile-notice-app');
            if (app && app.shadowRoot) {
                var btns = app.shadowRoot.querySelectorAll('cr-button');
                for (var b of btns) {
                    if (b.textContent.toLowerCase().includes('without')) {
                        b.click();
                        return 'clicked';
                    }
                }
            }
            return 'none';
        ''')
        log(f"Popup result: {result}")
        time.sleep(2)
        return result == 'clicked'
    except Exception as e:
        log(f"Popup error: {e}")
    return False


def switch_to_oauth_window(driver):
    for h in driver.window_handles:
        driver.switch_to.window(h)
        if 'accounts.google' in driver.current_url:
            return True
    return False


def handle_google_confirmations(driver, max_attempts: int = 10) -> bool:
    """Handle Google confirmation screens (Razumem/I understand) - can appear 1-2 times for new accounts."""
    log("Checking for Google confirmations (Razumem/I understand)...")
    
    for attempt in range(max_attempts):
        time.sleep(1)
        
        try:
            url = driver.current_url
        except:
            continue
            
        # Already redirected - success
        if "localhost" in url or "auth_status=success" in url or "kiro.dev" in url:
            log("Redirected away from Google - confirmations done")
            return True
        
        # Only handle on Google pages
        if "accounts.google" not in url:
            continue
        
        # Scroll down first
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.3)
        except:
            pass
        
        button_clicked = False
        
        # Try confirm button by ID (Razumem)
        try:
            btn = driver.find_element(By.ID, "confirm")
            if btn.is_displayed():
                log("Found confirm button (Razumem)")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", btn)
                log("Clicked confirm/Razumem!")
                button_clicked = True
                time.sleep(2)
                
                # Check if button appeared again (can happen twice)
                try:
                    btn2 = driver.find_element(By.ID, "confirm")
                    if btn2.is_displayed():
                        log("Confirm button appeared AGAIN - clicking second time!")
                        driver.execute_script("arguments[0].click();", btn2)
                        time.sleep(2)
                except:
                    pass
                continue
        except:
            pass
        
        # Try "I understand" button variants
        if not button_clicked:
            understand_xpaths = [
                "//button[contains(translate(text(), 'IUNDERSTAND', 'iunderstand'), 'i understand')]",
                "//button[contains(translate(., 'IUNDERSTAND', 'iunderstand'), 'i understand')]",
                "//*[@role='button'][contains(translate(text(), 'IUNDERSTAND', 'iunderstand'), 'i understand')]",
                "//span[contains(translate(text(), 'IUNDERSTAND', 'iunderstand'), 'i understand')]",
            ]
            for xpath in understand_xpaths:
                try:
                    btns = driver.find_elements(By.XPATH, xpath)
                    for btn in btns:
                        if btn.is_displayed() and btn.is_enabled():
                            log(f"Found I understand button: {btn.text[:30]}")
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", btn)
                            log("Clicked I understand!")
                            button_clicked = True
                            time.sleep(2)
                            
                            # Check if appeared again
                            try:
                                btns2 = driver.find_elements(By.XPATH, xpath)
                                for btn2 in btns2:
                                    if btn2.is_displayed() and btn2.is_enabled():
                                        log("I understand appeared AGAIN - clicking!")
                                        driver.execute_script("arguments[0].click();", btn2)
                                        time.sleep(2)
                                        break
                            except:
                                pass
                            break
                    if button_clicked:
                        break
                except:
                    pass
        
        # Try Continue/Allow buttons
        if not button_clicked:
            for text in ["Continue", "Allow", "Next", "OK"]:
                try:
                    btn = driver.find_element(By.XPATH, f'//button[contains(.,"{text}")]')
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        log(f"Clicked {text}")
                        button_clicked = True
                        time.sleep(2)
                        break
                except:
                    pass
        
        if not button_clicked:
            log(f"No confirmation button found (attempt {attempt + 1})")
    
    return True


def do_google_oauth(driver, email: str, password: str) -> bool:
    wait = WebDriverWait(driver, 15)
    original_window = driver.current_window_handle
    
    try:
        # Click Google button
        if "kiro.dev" in driver.current_url:
            try:
                btn = driver.find_element(By.XPATH, '//*[contains(text(),"Google")]')
                btn.click()
                log("Clicked Google")
                time.sleep(3)
                
                # Wait for OAuth window/popup
                for _ in range(10):
                    if len(driver.window_handles) > 1:
                        break
                    time.sleep(0.5)
                
                # Switch to OAuth window if opened
                for handle in driver.window_handles:
                    if handle != original_window:
                        driver.switch_to.window(handle)
                        log(f"Switched to OAuth window: {driver.current_url[:50]}")
                        break
                
                time.sleep(2)
            except Exception as e:
                log(f"Google button error: {e}")
        
        log(f"Current URL: {driver.current_url[:80]}")
        
        # Enter email
        email_input = wait.until(EC.presence_of_element_located((
            By.CSS_SELECTOR, "input[type='email'], input#identifierId"
        )))
        email_input.clear()
        email_input.send_keys(email)
        driver.find_element(By.ID, "identifierNext").click()
        log(f"Email: {email}")
        time.sleep(3)
        
        # Enter password
        pwd_input = wait.until(EC.presence_of_element_located((
            By.CSS_SELECTOR, "input[type='password'], input[name='Passwd']"
        )))
        pwd_input.send_keys(password)
        driver.find_element(By.ID, "passwordNext").click()
        log("Password entered")
        time.sleep(4)
        
        # Handle Chrome popup
        if "chrome://" in driver.current_url:
            handle_chrome_popup(driver)
            switch_to_oauth_window(driver)
        
        # Handle Google confirmations (Razumem/I understand) - appears for new accounts
        handle_google_confirmations(driver)
        
        # Wait for auth_status=success (kiro-cli gets callback via postMessage, not redirect)
        for _ in range(15):
            time.sleep(2)
            url = driver.current_url
            log(f"Current URL: {url[:80]}")
            
            # Success = auth_status=success or localhost redirect
            if "localhost" in url or "auth_status=success" in url:
                log("SUCCESS - OAuth completed")
                return True
            
            # Error check
            if "error" in url.lower():
                log(f"OAuth error in URL: {url}")
                return False
            
            # Try to click Continue/Allow buttons if present
            try:
                driver.find_element(By.XPATH, '//button[contains(.,"Continue")]').click()
                log("Clicked Continue")
            except:
                pass
            
            try:
                driver.find_element(By.XPATH, '//button[contains(.,"Allow")]').click()
                log("Clicked Allow")
            except:
                pass
        
        log("Timeout waiting for OAuth completion")
        return False
        
    except Exception as e:
        log(f"OAuth error: {e}")
        return False


def kiro_login(email: str, password: str) -> bool:
    """Login to Kiro via Google OAuth - simple approach."""
    log(f"Kiro login: {email}")
    
    # First logout
    log("Running kiro-cli logout...")
    subprocess.run([KIRO_CLI_PATH, "logout"], capture_output=True, timeout=10)
    time.sleep(1)
    
    # Start kiro-cli login in background FIRST (it will listen on localhost:49153)
    log("Starting kiro-cli login --social google...")
    kiro_proc = subprocess.Popen(
        [KIRO_CLI_PATH, "login", "--social", "google"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(3)  # Wait for it to open Yandex
    
    # Get the special Kiro URL from Yandex (contains redirect_uri to localhost)
    kiro_url = None
    log("Getting Kiro URL from Yandex...")
    for _ in range(10):
        try:
            result = subprocess.run(
                ["osascript", "-e", 'tell application "Yandex" to get URL of active tab of front window'],
                capture_output=True, text=True, timeout=3
            )
            url = result.stdout.strip()
            if "kiro.dev" in url and "redirect_uri" in url:
                kiro_url = url
                log(f"Got Kiro URL with redirect: {url[:80]}...")
                break
        except:
            pass
        time.sleep(0.5)
    
    # Close Yandex tab (not whole window)
    log("Closing Yandex tab...")
    try:
        subprocess.run(
            ["osascript", "-e", 'tell application "Yandex" to close active tab of front window'],
            capture_output=True, timeout=3
        )
    except:
        pass
    time.sleep(1)
    
    # Now start clean Chrome
    start_chrome_if_needed()
    time.sleep(2)  # Extra wait for Chrome to be fully ready
    
    try:
        driver = get_chrome_driver()
        
        # Open the special Kiro URL (with localhost redirect) in our Chrome
        if kiro_url:
            log(f"Opening Kiro URL in Chrome...")
            driver.get(kiro_url)
        else:
            log("No special URL found, using default signin")
            driver.get("https://app.kiro.dev/signin")
        time.sleep(2)
        
        # Do OAuth flow
        success = do_google_oauth(driver, email, password)
        
        if success:
            # Wait for kiro-cli to receive callback and save token
            log("Waiting for kiro-cli to complete...")
            try:
                stdout, stderr = kiro_proc.communicate(timeout=30)
                log(f"kiro-cli exit code: {kiro_proc.returncode}")
                if kiro_proc.returncode == 0:
                    log("kiro-cli login successful!")
                    return True
                else:
                    log(f"kiro-cli failed: {stderr.decode()[:200]}")
                    return False
            except subprocess.TimeoutExpired:
                log("kiro-cli timeout")
                kiro_proc.kill()
                return False
        else:
            kiro_proc.kill()
            return False
            
    except Exception as e:
        log(f"Error: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python kiro_auto_login.py <email> <password>")
        sys.exit(1)
    
    success = kiro_login(sys.argv[1], sys.argv[2])
    sys.exit(0 if success else 1)
