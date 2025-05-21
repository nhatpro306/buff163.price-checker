import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# === Config ===
SKINS = [
    {
        "goods_id": "42552",
        "name": "Butterfly | Damascus Steel",
        "condition": "Field-Tested"
    },
    {
        "goods_id": "42555",
        "name": "Butterfly | Doppler ",
        "condition": "Factory New"
    },
    {
        "goods_id": "42998",
        "name": "Karambit | Doppler",
        "condition": "Factory New"
    },
    {
        "goods_id": "42533",
        "name": "Butterfly | Blue Steel",
        "condition": "Field-Tested"
    },
    {
        "goods_id": "83578",
        "name": "Gloves | Nocts",
        "condition": "Field-Tested"
    },
    {
        "goods_id": "42587",
        "name": "Butterfly | Tiger Tooth",
        "condition": "Factory New"
    }
]

SHEET_NAME = "BuffKnifeTracker"
LOG_SHEET_NAME = "HistoryLog"

# === Google Sheets Setup ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

try:
    log_sheet = client.open(SHEET_NAME).worksheet(LOG_SHEET_NAME)
except:
    spreadsheet = client.open(SHEET_NAME)
    log_sheet = spreadsheet.add_worksheet(title=LOG_SHEET_NAME, rows="1000", cols="10")
    log_sheet.append_row(["Timestamp", "Knife Type", "Skin Name", "Condition", "Price (¥)", "Sell Listings"])

# === Scrape and Append ===
headers = {"User-Agent": "Mozilla/5.0"}
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
log_rows = []

for skin in SKINS:
    try:
        # Fetch lowest price
        url = f"https://buff.163.com/api/market/goods/sell_order?game=csgo&goods_id={skin['goods_id']}&page_num=1&sort_by=default"
        response = requests.get(url, headers=headers)
        data = response.json()
        orders = data["data"]["items"]

        # Fetch total sell count (correct one)
        info_url = f"https://buff.163.com/api/market/goods/goods_info?game=csgo&goods_id={skin['goods_id']}"
        info_response = requests.get(info_url, headers=headers)
        info_data = info_response.json()
        sell_count = info_data["data"]["sell_num"]

        if orders:
            price = float(orders[0]["price"])
            knife_type = skin["name"].split(" | ")[0].strip()
            log_row = [timestamp, knife_type, skin["name"], skin["condition"], price, sell_count]
            log_rows.append(log_row)

    except Exception as e:
        print(f"❌ Error fetching {skin['name']}: {e}")

# === Append to Log Sheet ===
if log_rows:
    log_sheet.append_rows(log_rows, value_input_option="USER_ENTERED")
    print("✅ Logged data to HistoryLog sheet.")
else:
    print("⚠️ No data to log.")

# === Dashboard Setup ===
DASHBOARD_SHEET_NAME = "Dashboard"

try:
    dashboard_sheet = client.open(SHEET_NAME).worksheet(DASHBOARD_SHEET_NAME)
except:
    spreadsheet = client.open(SHEET_NAME)
    dashboard_sheet = spreadsheet.add_worksheet(title=DASHBOARD_SHEET_NAME, rows="1000", cols="10")
    dashboard_sheet.append_row(["Skin Name", "Latest Price (¥)", "Price Trend", "Sell Listings", "Average Price (¥)", "Price Change %"])

# === Update Dashboard ===
def update_dashboard(log_rows):
    all_logs = log_sheet.get_all_values()
    skin_names = {skin['name']: [] for skin in SKINS}

    for row in all_logs[1:]:
        skin_name = row[2]
        price_str = row[4]
        if price_str:
            price_str = price_str.replace(',', '.')
            try:
                price = float(price_str)
            except ValueError:
                price =
