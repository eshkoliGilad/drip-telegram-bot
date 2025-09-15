"""
DRIP Telegram Bot
=================

Telegram bot that uses the exact DexScreener API endpoint:
https://api.dexscreener.com/latest/dex/tokens/<TOKEN_CA>

Features
- /start command: welcome message
- /volume: DRIP LP pairs sorted by 24H volume (descending), medals for top 3, 💰 for others, summary with SOL/DRIP (raydium).
- /ratio: DRIP LP pairs sorted by performance ratio (24H Volume ÷ Liquidity).
- /volume_other <TOKEN_CA>: Same as /volume but for any token contract.
- /ratio_other <TOKEN_CA>: Same as /ratio but for any token contract.

Requirements
- Python 3.9+
- pip install requests python-telegram-bot==13.15 python-dotenv
"""

import os
import logging
import requests
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

DEFAULT_API_URL = (
    "https://api.dexscreener.com/latest/dex/tokens/"
    "w131jbryFvFEmtqmZvx42Meiuc4Drmu3nodTdVgkREV"
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    except Exception:
        pass

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def format_usd(val):
    try:
        return f"${float(val):,.2f}"
    except Exception:
        return "N/A"


def format_pct(val):
    try:
        return f"{val:.2%}"
    except Exception:
        return "N/A"


def fetch_token_endpoint(contract_address: str):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{contract_address}"
    headers = {"User-Agent": "DRIP-Telegram-Bot/1.0"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "Welcome! Commands available:\n"
        "/volume → DRIP LP pairs by 24H volume\n"
        "/ratio → DRIP LP pairs by ratio\n"
        "/volume_other <TOKEN_CA> → LP pairs of another token by 24H volume\n"
        "/ratio_other <TOKEN_CA> → LP pairs of another token by ratio"
    )


def handle_volume(update: Update, contract_address: str, show_summary: bool = False) -> None:
    try:
        data = fetch_token_endpoint(contract_address)
    except Exception as e:
        logger.exception("Failed to fetch DexScreener data")
        update.message.reply_text(f"Error fetching data: {e}")
        return

    pairs = data.get("pairs") or []
    if not pairs:
        update.message.reply_text("No pairs found in DexScreener response.")
        return

    # Filter pairs with liquidity
    filtered_pairs = []
    for p in pairs:
        try:
            liquidity_val = float(p.get("liquidity", {}).get("usd") or 0)
        except Exception:
            liquidity_val = 0
        if liquidity_val > 0:
            filtered_pairs.append(p)

    if not filtered_pairs:
        update.message.reply_text("No valid LP pairs with liquidity found.")
        return

    # Sort pairs by 24h volume
    pairs_sorted = sorted(
        filtered_pairs,
        key=lambda p: float(p.get("volume", {}).get("h24") or 0),
        reverse=True,
    )

    total_volume = 0.0
    sol_ray_vol = 0.0

    lines = [f"Found {len(pairs_sorted)} active LP pairs\n"]
    for i, p in enumerate(pairs_sorted):
        base = (p.get("baseToken", {}).get("symbol") or "?").strip()
        quote = (p.get("quoteToken", {}).get("symbol") or "?").strip()
        dex = (p.get("dexId", "unknown") or "unknown").strip()

        try:
            liquidity_val = float(p.get("liquidity", {}).get("usd") or 0)
        except Exception:
            continue
        try:
            vol24h_val = float(p.get("volume", {}).get("h24") or 0)
        except Exception:
            vol24h_val = 0

        liquidity = format_usd(liquidity_val)
        vol24h = format_usd(vol24h_val)

        if i == 0:
            icon = "🥇"
        elif i == 1:
            icon = "🥈"
        elif i == 2:
            icon = "🥉"
        else:
            icon = "💰"

        line = (
            f"{icon} {base}/{quote} ({dex}) -\n"
            f"Liquidity: *{liquidity}* \n"
            f"24H Volume: *{vol24h}*\n\n"
        )
        lines.append(line)

        total_volume += vol24h_val
        symbols = {base.upper(), quote.upper()}
        if show_summary and symbols == {"SOL", "DRIP"} and dex.strip().lower() == "raydium":
            sol_ray_vol += vol24h_val

    if show_summary:
        total_other_vol = total_volume - sol_ray_vol
        lines.append("📊 Summary (24H Volume):")
        lines.append(f"- SOL/DRIP (raydium): *{format_usd(sol_ray_vol)}*")
        lines.append(f"- All others combined: *{format_usd(total_other_vol)}*")

    msg_text = "\n".join(lines)
    update.message.reply_text(msg_text, parse_mode="Markdown", disable_web_page_preview=True)


def handle_ratio(update: Update, contract_address: str) -> None:
    try:
        data = fetch_token_endpoint(contract_address)
    except Exception as e:
        logger.exception("Failed to fetch DexScreener data")
        update.message.reply_text(f"Error fetching data: {e}")
        return

    pairs = data.get("pairs") or []
    if not pairs:
        update.message.reply_text("No pairs found in DexScreener response.")
        return

    ratios = []
    for p in pairs:
        try:
            liquidity_val = float(p.get("liquidity", {}).get("usd") or 0)
            vol24h_val = float(p.get("volume", {}).get("h24") or 0)
        except Exception:
            continue
        if liquidity_val > 0 and vol24h_val > 0:
            ratio = vol24h_val / liquidity_val
            ratios.append((ratio, liquidity_val, vol24h_val, p))

    if not ratios:
        update.message.reply_text("No valid pairs with ratio data found.")
        return

    ratios_sorted = sorted(ratios, key=lambda x: x[0], reverse=True)

    lines = [f"Found {len(ratios_sorted)} LP pairs ranked by ratio (24H Volume ÷ Liquidity)\n"]
    for i, (ratio, liquidity_val, vol24h_val, p) in enumerate(ratios_sorted):
        base = (p.get("baseToken", {}).get("symbol") or "?").strip()
        quote = (p.get("quoteToken", {}).get("symbol") or "?").strip()
        dex = (p.get("dexId", "unknown") or "unknown").strip()

        liquidity = format_usd(liquidity_val)
        vol24h = format_usd(vol24h_val)
        ratio_pct = format_pct(ratio)

        if i == 0:
            icon = "🥇"
        elif i == 1:
            icon = "🥈"
        elif i == 2:
            icon = "🥉"
        else:
            icon = "💰"

        line = (
            f"{icon} {base}/{quote} ({dex}) -\n"
            f"Liquidity: *{liquidity}* \n"
            f"24H Volume: *{vol24h}* \n"
            f"Ratio: *{ratio_pct}*\n\n"
        )
        lines.append(line)

    msg_text = "\n".join(lines)
    update.message.reply_text(msg_text, parse_mode="Markdown", disable_web_page_preview=True)


# === Command wrappers ===

def volume(update: Update, context: CallbackContext) -> None:
    handle_volume(update, "w131jbryFvFEmtqmZvx42Meiuc4Drmu3nodTdVgkREV", show_summary=True)


def ratio(update: Update, context: CallbackContext) -> None:
    handle_ratio(update, "w131jbryFvFEmtqmZvx42Meiuc4Drmu3nodTdVgkREV")


def volume_other(update: Update, context: CallbackContext) -> None:
    if not context.args:
        update.message.reply_text("Usage: /volume_other <TOKEN_CA>")
        return
    contract_address = context.args[0]
    handle_volume(update, contract_address)


def ratio_other(update: Update, context: CallbackContext) -> None:
    if not context.args:
        update.message.reply_text("Usage: /ratio_other <TOKEN_CA>")
        return
    contract_address = context.args[0]
    handle_ratio(update, contract_address)


def main() -> None:
    if TELEGRAM_TOKEN is None:
        print("Error: TELEGRAM_TOKEN not set. Please set TELEGRAM_TOKEN as env var or in .env file.")
        return

    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("volume", volume))
    dp.add_handler(CommandHandler("ratio", ratio))
    dp.add_handler(CommandHandler("volume_other", volume_other))
    dp.add_handler(CommandHandler("ratio_other", ratio_other))

    logger.info("Bot started.")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
