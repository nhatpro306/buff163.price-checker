import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# === Config ===
SKINS = [
    {"goods_id": "42552", "name": "Butterfly | Damascus Steel", "condition": "Field-Tested"},
    {"goods_id": "42555", "name": "Butterfly | Doppler", "condition": "Factory New"},
    {"goods_id": "42998", "name": "Karambit | Doppler", "condition": "Factory New"},
    {"goods_id": "42533", "name": "Butterfly | Blue Steel", "condition": "Field-Tested"},
    {"goods_id": "83578", "name": "Gloves | Nocts", "condition": "Field-Tested"},
    {"goods_id": "42587", "name": "Butterfly | Tiger Tooth", "condition": "Factory New"},
]

SHEET_NAME = "BuffKnifeTracker"
LOG_SHEET_NAME = "HistoryLog"
DASHBOARD_SHEET_NAME = "Dashboard"

# === Google Sheets Setup ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

# Open or create sheets
spreadsheet = client.open(SHEET_NAME)
try:
    log_sheet = spreadsheet.worksheet(LOG_SHEET_NAME)
except:
    log_sheet = spreadsheet.add_worksheet(title=LOG_SHEET_NAME, rows="1000", cols="10")
    log_sheet.append_row(["Timestamp", "Knife Type", "Skin Name", "Condition", "Price (¥)", "Sell Listings"])

try:
    dashboard_sheet = spreadsheet.worksheet(DASHBOARD_SHEET_NAME)
except:
    dashboard_sheet = spreadsheet.add_worksheet(title=DASHBOARD_SHEET_NAME, rows="1000", cols="10")
    dashboard_sheet.append_row(["Skin Name", "Latest Price (¥)", "Price Trend", "Sell Listings", "Average Price (¥)", "Price Change %"])

# === Scrape and Log Data ===
headers = {"User-Agent": "Mozilla/5.0"}
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
log_rows = []

for skin in SKINS:
    try:
        url = f"https://buff.163.com/api/market/goods/sell_order?game=csgo&goods_id={skin['goods_id']}&page_num=1&sort_by=default"
        response = requests.get(url, headers=headers)
        data = response.json()

        orders = data["data"]["items"]
        sell_count = data["data"]["total_count"]

        if orders:
            price = float(orders[0]["price"])
            knife_type = skin["name"].split(" | ")[0].strip()
            log_row = [timestamp, knife_type, skin["name"], skin["condition"], price, sell_count]
            log_rows.append(log_row)

    except Exception as e:
        print(f"❌ Error fetching {skin['name']}: {e}")

if log_rows:
    log_sheet.append_rows(log_rows, value_input_option="USER_ENTERED")
    print("✅ Logged data to HistoryLog sheet.")
else:
    print("⚠️ No data to log.")

# === Dashboard Update ===
def update_dashboard():
    all_logs = log_sheet.get_all_values()[1:]  # Skip header
    skin_prices = {skin['name'].strip(): [] for skin in SKINS}

    for row in all_logs:
        skin_name = row[2].strip()
        price_str = row[4].replace(",", ".")
        try:
            price = float(price_str)
        except:
            price = 0
        if skin_name in skin_prices:
            skin_prices[skin_name].append(price)
        else:
            print(f"⚠️ Unknown skin found in log: {skin_name}")

    for skin in SKINS:
        skin_name = skin['name'].strip()
        prices = skin_prices.get(skin_name, [])
        if prices:
            latest_price = prices[-1]
            avg_price = sum(prices) / len(prices)
            price_change = ((latest_price - prices[0]) / prices[0]) * 100 if prices[0] else 0

            row_data = [
                skin_name,
                latest_price,
                f'=SPARKLINE(E2:E{len(prices)+1})',
                len(prices),
                round(avg_price, 2),
                round(price_change, 2)
            ]

            dashboard_sheet.append_row(row_data)


if log_rows:
    update_dashboard()
    print("✅ Dashboard updated with the latest data.")
