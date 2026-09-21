import sys
import json
from pathlib import Path
import logging

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shadow_reader import get_shadow_system_state
from bot.telegram_bot import mesaj_gonder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ShadowTelegram")

def get_delivery_state_file() -> Path:
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir / "shadow_telegram_delivery.json"

def load_delivery_state() -> dict:
    f = get_delivery_state_file()
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except:
        return {}

def save_delivery_state(state_dict: dict):
    f = get_delivery_state_file()
    f.write_text(json.dumps(state_dict, indent=2), encoding="utf-8")

def run_notification(mock_mesaj_gonder=None):
    state = get_shadow_system_state(ROOT_DIR)
    if not state:
        logger.info("No shadow state found. Exiting.")
        return "BLOCKED"

    status = state.get("status")
    session_date = state.get("session_date")
    event_id = state.get("event_id")

    if status != "OFFICIAL_CLEAN_FORWARD":
        logger.info(f"State is {status}. Only OFFICIAL_CLEAN_FORWARD triggers telegram. Silent exit.")
        return "BLOCKED"

    if not event_id:
        logger.error("Missing event_id in official state.")
        return "ERROR"

    delivery_state = load_delivery_state()
    current_status = delivery_state.get(event_id, {}).get("status", "NEW")

    if current_status in ["SENT", "PENDING", "AMBIGUOUS_DELIVERY"]:
        logger.info(f"Already processed event {event_id} with status {current_status}. Skipping.")
        return "BLOCKED"

    # Mark as pending
    delivery_state[event_id] = {"status": "PENDING", "session_date": session_date}
    save_delivery_state(delivery_state)

    # Build the message
    msg = f"🚀 <b>YENİ OFFICIAL CLEAN-FORWARD SİNYALİ</b>\n"
    msg += f"🗓️ Tarih: {session_date}\n\n"
    
    primary = state.get("primary", {})
    if primary and primary.get("ordered_top10"):
        msg += f"🏆 <b>PRIMARY SHADOW ({primary['candidate_id']})</b>\n"
        for i, item in enumerate(primary["ordered_top10"][:10], 1):
            msg += f"{i}. {item['ticker']} (Score: {item['raw_score']:.4f})\n"
        msg += "\n"

    secondary = state.get("secondary", {})
    if secondary and secondary.get("ordered_top10"):
        msg += f"⭐ <b>SECONDARY SHADOW ({secondary['candidate_id']})</b>\n"
        for i, item in enumerate(secondary["ordered_top10"][:10], 1):
            msg += f"{i}. {item['ticker']} (Score: {item['raw_score']:.4f})\n"

    msg += "\n<i>Bu bir karar destek sistemidir. Emir iletimi yapılmaz.</i>"

    # Use mock if provided (for testing)
    send_func = mock_mesaj_gonder if mock_mesaj_gonder else mesaj_gonder
    
    try:
        success = send_func(msg, parse_mode="HTML")
        if success:
            delivery_state[event_id]["status"] = "SENT"
            save_delivery_state(delivery_state)
            logger.info(f"Notification sent successfully for {event_id}")
            return "READY_AND_SENT"
        else:
            delivery_state[event_id]["status"] = "AMBIGUOUS_DELIVERY"
            save_delivery_state(delivery_state)
            logger.error("Failed to send telegram notification. Marked as AMBIGUOUS_DELIVERY.")
            return "AMBIGUOUS_DELIVERY"
    except Exception as e:
        logger.error(f"Exception during send: {e}")
        delivery_state[event_id]["status"] = "AMBIGUOUS_DELIVERY"
        save_delivery_state(delivery_state)
        return "AMBIGUOUS_DELIVERY"

if __name__ == "__main__":
    run_notification()
