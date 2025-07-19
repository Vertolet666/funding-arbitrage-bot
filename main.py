# ✅ ФИНАЛЬНАЯ ВЕРСИЯ АРБИТРАЖ-БОТА ДЛЯ ФАНДИНГА

import requests
import telebot
import time
import datetime

from config import TELEGRAM_TOKEN, CHAT_ID

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Настройки
EXCHANGES = ["binance", "bybit", "kucoin", "gate", "bingx", "mexc"]
MIN_DIFF = 0.1  # Минимальная разница ставок (%)
FREQ_CHANGE_TRACKER = {}


# Получаем данные с Defillama
def fetch_funding_data():
    url = "https://funding.llama.fi/funding-rates"
    try:
        response = requests.get(url)
        return response.json().get("data", [])
    except:
        return []


# Генерация ссылок на фьючерсы
def generate_links(symbol):
    return {
        "bybit": f"https://www.bybit.com/trade/usdt/{symbol}USDT",
        "binance": f"https://www.binance.com/futures/{symbol}_USDT",
        "gate": f"https://www.gate.io/futures/USDT/{symbol}_USDT",
        "bingx": f"https://bingx.com/perpetual/{symbol}-USDT",
        "kucoin": f"https://www.kucoin.com/futures/trade/{symbol}USDTM",
        "mexc": f"https://www.mexc.com/exchange/{symbol}_USDT"
    }


# Преобразуем timestamp в читаемое время и интервал
def format_time(t):
    dt = datetime.datetime.utcfromtimestamp(t / 1000)
    delta = int((t - int(time.time() * 1000)) / 1000 / 60 / 60)
    return dt.strftime("%H:%M"), delta


# Основная логика
sent_notifications = set()

while True:
    data = fetch_funding_data()
    assets = {}

    for d in data:
        coin = d["coin"].upper()
        exchange = d["exchange"].lower()
        if exchange not in EXCHANGES:
            continue

        rate = d.get("rate", 0) * 100
        next_funding = d.get("nextFundingTime")
        granularity = d.get("fundingInterval", 0)
        price = d.get("price", 0)

        if coin not in assets:
            assets[coin] = {}
        assets[coin][exchange] = {
            "rate": rate,
            "price": price,
            "time": next_funding,
            "interval": granularity
        }

        # Проверка изменения частоты выплаты
        key = f"{coin}:{exchange}"
        if key in FREQ_CHANGE_TRACKER and FREQ_CHANGE_TRACKER[key] != granularity:
            t_hours = int(granularity / 1000 / 60 / 60)
            msg = f"⚠️ {coin} — ставка на {exchange.capitalize()} теперь начисляется каждые {t_hours} ч."
            bot.send_message(CHAT_ID, msg)

        FREQ_CHANGE_TRACKER[key] = granularity

    # Поиск арбитража
    for coin, exchs in assets.items():
        best_long = min(exchs.items(), key=lambda x: x[1]["rate"], default=(None, None))
        best_short = max(exchs.items(), key=lambda x: x[1]["rate"], default=(None, None))

        if not best_long or not best_short:
            continue

        diff = best_short[1]["rate"] - best_long[1]["rate"]
        if diff < MIN_DIFF:
            continue

        # Средний суточный PnL
        avg_pnl = diff * 3
        price_diff = best_short[1]["price"] - best_long[1]["price"]
        pkey = f"{coin}-{best_long[0]}-{best_short[0]}"

        if pkey in sent_notifications:
            continue

        sent_notifications.add(pkey)

        # Форматируем время
        time_l, delta_l = format_time(best_long[1]["time"])
        time_s, delta_s = format_time(best_short[1]["time"])

        links = generate_links(coin)

        msg = f"<b>{coin}</b>\n\n"
        msg += f"Средний суточный PNL: <b>{avg_pnl:.2f}%</b>\n"
        msg += f"Разница в цене: {price_diff / best_long[1]['price'] * 100:.2f}%\n\n"
        msg += f"Лонг {best_long[0].capitalize()} ({links.get(best_long[0])}) -> Шорт {best_short[0].capitalize()} ({links.get(best_short[0])})\n\n"

        msg += "<b>Биржа   Ставка  Цена     Начисление</b>\n"
        msg += f"{best_long[0].capitalize()}   {best_long[1]['rate']:.2f}%   {best_long[1]['price']:.5f}  {time_l} ({delta_l}ч)\n"
        msg += f"{best_short[0].capitalize()}  {best_short[1]['rate']:.2f}%   {best_short[1]['price']:.5f}  {time_s} ({delta_s}ч)\n\n"

        msg += "<b>Другие биржи:</b>\n"
        for ex, info in exchs.items():
            t, d = format_time(info["time"])
            msg += f"{ex.capitalize()}  {info['rate']:.2f}%   {info['price']:.5f}  {t} ({d}ч)\n"

        # Ссылки снизу
        msg += "\n" + " ".join([f"<a href='{url}'>{ex.capitalize()}</a>" for ex, url in links.items() if ex in exchs])

        bot.send_message(CHAT_ID, msg, parse_mode="HTML")

    time.sleep(600)  # каждые 10 минут
