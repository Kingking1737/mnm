import os
import secrets
import hashlib
import time
import requests
import nano_rspow
import logging
from nanopy import Account

# ---------- تنظیمات ----------
WAIT_AFTER_SUCCESS = 10
EXTRA_WAIT_ON_RETRY = 10
LOG_FILE = "faucet_run.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# ---------- seed یک‌بار ----------
# اگه روی Railway متغیر SEED رو ست کنی، از همون استفاده می‌کنه،
# وگرنه هر بار رندوم می‌سازه.
seed = os.getenv("SEED") or secrets.token_hex(32).upper()
logging.info("=" * 70)
logging.info(f"SEED: {seed}")
logging.info("=" * 70)


def derive_account(index: int):
    private_key = hashlib.blake2b(
        bytes.fromhex(seed) + index.to_bytes(4, 'big'),
        digest_size=32
    ).hexdigest().upper()
    return Account(sk=private_key), private_key


def extract_retry_seconds(body: dict):
    if not isinstance(body, dict):
        return None
    for key in ("retry_after_seconds", "retryAfterSeconds", "retry_after"):
        if key in body:
            try:
                return int(body[key])
            except (ValueError, TypeError):
                pass
    return None


def try_claim(addr: str):
    try:
        ch = requests.get(
            f"https://feeless402.com/faucet/challenge?address={addr}",
            timeout=30
        ).json()
    except Exception as e:
        logging.error(f"خطا در گرفتن challenge: {e}")
        return ("fail", None)

    logging.info(f"CHALLENGE: {ch}")

    if "error" in ch:
        wait = extract_retry_seconds(ch)
        if wait is not None:
            return ("retry", wait)
        logging.error(f"❌ خطا از فاست: {ch['error']}")
        return ("fail", None)

    logging.info("در حال حل Proof-of-Work...")
    try:
        w = nano_rspow.generate_work_with_threshold(ch["root"], ch["difficulty"])
    except Exception as e:
        logging.error(f"خطا در PoW: {e}")
        return ("fail", None)

    logging.info(f"Nonce: {w.nonce_hex}")

    try:
        valid = nano_rspow.validate_work_with_threshold(
            ch["root"], w.nonce_hex, ch["difficulty"]
        )
    except Exception as e:
        logging.error(f"خطا در validate: {e}")
        return ("fail", None)

    logging.info(f"Nonce معتبر است؟ {valid}")
    if not valid:
        logging.error("❌ PoW نامعتبر")
        return ("fail", None)

    try:
        r = requests.post(
            "https://feeless402.com/faucet",
            json={"address": addr, "work": w.nonce_hex},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
    except Exception as e:
        logging.error(f"خطا در ارسال درخواست: {e}")
        return ("fail", None)

    logging.info(f"RESPONSE: {r.text}")

    try:
        body = r.json()
    except Exception:
        body = None

    if body:
        wait = extract_retry_seconds(body)
        if wait is not None:
            return ("retry", wait)

    text_lower = r.text.lower()
    if "error" in text_lower or '"success":false' in text_lower.replace(" ", ""):
        return ("fail", None)
    return ("ok", None)


# ---------- حلقه اصلی (بی‌نهایت) ----------
index = 0
while True:
    account, private_key = derive_account(index)

    logging.info(f"\nINDEX:   {index}")
    logging.info(f"PRIVATE: {private_key}")
    logging.info(f"ADDRESS: {account.addr}")

    status, wait = try_claim(account.addr)

    if status == "ok":
        logging.info(f"✅ فاست داد برای index={index}")
        index += 1
        logging.info(f"صبر {WAIT_AFTER_SUCCESS} ثانیه قبل از آدرس بعدی...")
        time.sleep(WAIT_AFTER_SUCCESS)
        continue

    elif status == "retry":
        total_wait = wait + EXTRA_WAIT_ON_RETRY
        logging.warning(
            f"⏳ فاست گفت {wait} ثانیه صبر کن. "
            f"کل انتظار: {total_wait} ثانیه، "
            f"بعد دوباره همون index={index} رو امتحان می‌کنم."
        )
        time.sleep(total_wait)
        continue

    else:  # fail
        logging.warning(f"⛔ خطای غیرقابل‌retry (index={index}). بستن برنامه.")
        break

logging.info("Finished.")
