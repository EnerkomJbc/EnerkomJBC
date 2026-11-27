import os
import re
import sys
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def safe_location(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def main():
    username = os.environ.get("EDC_USERNAME", "").strip()
    password = os.environ.get("EDC_PASSWORD", "")
    if not username or not password:
        print("EDC_LOGIN_CONFIG_ERROR: Chybí EDC_USERNAME nebo EDC_PASSWORD.")
        return 2

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(15000)

        stage = "otevření portálu"
        try:
            print("EDC_LOGIN: Otevírám portál EDC.")
            response = page.goto(
                "https://portal.edc-cr.cz/",
                wait_until="commit",
                timeout=60000,
            )
            print("EDC_PORTAL_RESPONSE:", response.status if response else "bez HTTP odpovědi")
            page.wait_for_timeout(1500)

            stage = "nalezení odkazu na přihlášení"
            login_link = page.get_by_role(
                "link", name=re.compile(r"Registrace\s*/\s*Přihlášení", re.I)
            ).first
            login_button = page.get_by_role(
                "button", name=re.compile(r"Registrace\s*/\s*Přihlášení", re.I)
            ).first

            if login_link.count():
                login_link.click()
            elif login_button.count():
                login_button.click()
            else:
                print("EDC_LOGIN_FORM_NOT_FOUND: Na úvodní stránce není rozpoznáno tlačítko přihlášení.")
                print("EDC_PAGE:", safe_location(page.url))
                return 3

            stage = "otevření přihlašovací stránky"
            page.wait_for_timeout(1200)
            opened_pages = [candidate for candidate in context.pages if candidate != page]
            if opened_pages:
                page = opened_pages[-1]
                page.set_default_timeout(15000)
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(1200)

            stage = "vyhledání přihlašovacího formuláře"
            password_input = page.locator('input[type="password"]:visible').first
            if password_input.count() == 0:
                print("EDC_LOGIN_FORM_NOT_FOUND: Přihlašovací formulář neobsahuje viditelné pole hesla.")
                print("EDC_PAGE:", safe_location(page.url))
                return 4

            email_input = page.locator('input[type="email"]:visible').first
            if email_input.count():
                username_input = email_input
            else:
                candidates = page.locator(
                    'input:visible:not([type="password"]):not([type="hidden"]):not([type="submit"]):not([type="button"])'
                )
                username_input = None
                for i in range(candidates.count()):
                    item = candidates.nth(i)
                    input_type = (item.get_attribute("type") or "text").lower()
                    input_name = (item.get_attribute("name") or "").lower()
                    input_id = (item.get_attribute("id") or "").lower()
                    hint = " ".join([input_type, input_name, input_id])
                    if input_type in ("text", "email") and any(
                        word in hint for word in ("email", "mail", "user", "login")
                    ):
                        username_input = item
                        break
                if username_input is None and candidates.count():
                    username_input = candidates.first

            if username_input is None:
                print("EDC_LOGIN_FORM_NOT_FOUND: Nepodařilo se rozpoznat pole uživatelského jména.")
                print("EDC_PAGE:", safe_location(page.url))
                return 5

            stage = "vyplnění přihlašovacího formuláře"
            username_input.fill(username)
            password_input.fill(password)

            stage = "odeslání přihlašovacího formuláře"
            submit = page.locator(
                'button[type="submit"]:visible, input[type="submit"]:visible'
            ).first
            if submit.count():
                submit.click()
            else:
                password_input.press("Enter")

            try:
                page.wait_for_load_state("domcontentloaded", timeout=12000)
            except PlaywrightTimeoutError:
                pass
            page.wait_for_timeout(4000)

            body = ""
            try:
                body = page.locator("body").inner_text(timeout=5000).lower()
            except Exception:
                pass

            success_markers = (
                "odhlásit",
                "odhlášení",
                "správa dat",
                "zobrazení dat",
            )
            error_markers = (
                "neplatné přihlašovací",
                "nesprávné heslo",
                "chybný e-mail",
                "přihlášení se nezdařilo",
                "captcha",
            )

            print("EDC_PAGE:", safe_location(page.url))
            if any(marker in body for marker in success_markers):
                print("EDC_LOGIN_SUCCESS: Portál EDC potvrdil přihlášení.")
                return 0
            if any(marker in body for marker in error_markers):
                print("EDC_LOGIN_REJECTED: Portál zobrazil upozornění na neúspěšné přihlášení nebo ověření.")
                return 6

            print("EDC_LOGIN_UNCONFIRMED: Stránka nevrátila jednoznačné potvrzení přihlášení.")
            print("EDC_PAGE_TITLE:", page.title()[:120])
            return 7

        except Exception as exc:
            # Do not print exception details: browser/network errors can contain URLs or request data.
            print("EDC_LOGIN_TECHNICAL_ERROR:", type(exc).__name__, "| fáze:", stage)
            return 8
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
