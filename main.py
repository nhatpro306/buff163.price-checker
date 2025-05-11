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
        "goods_id": "42533",
        "name": "Butterfly | Blue Steel",
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
    # Create log sheet if not exist
    spreadsheet = client.open(SHEET_NAME)
    log_sheet = spreadsheet.add_worksheet(title=LOG_SHEET_NAME, rows="1000", cols="10")
    log_sheet.append_row(["Timestamp", "Knife Type", "Skin Name", "Condition", "Price (¥)", "Sell Listings"])

# === Scrape and Append ===
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

# === Append to Log Sheet ===
if log_rows:
    log_sheet.append_rows(log_rows, value_input_option="USER_ENTERED")
    print("✅ Logged data to HistoryLog sheet.")
else:
    print("⚠️ No data to log.")
# === Dashboard Setup ===
DASHBOARD_SHEET_NAME = "Dashboard"

# Check if dashboard sheet exists, create it if not
try:
    dashboard_sheet = client.open(SHEET_NAME).worksheet(DASHBOARD_SHEET_NAME)
except:
    spreadsheet = client.open(SHEET_NAME)
    dashboard_sheet = spreadsheet.add_worksheet(title=DASHBOARD_SHEET_NAME, rows="1000", cols="10")
    dashboard_sheet.append_row(["Skin Name", "Latest Price (¥)", "Price Trend", "Sell Listings", "Average Price (¥)", "Price Change %"])

 # === Update Dashboard ===
def update_dashboard(log_rows):
    # Read all log data
    all_logs = log_sheet.get_all_values()
    skin_names = {skin['name']: [] for skin in SKINS}

    # Collect price data per skin
    for row in all_logs[1:]:  # Skip header
        skin_name = row[2]
        price_str = row[4]
        
        # Handle price format with commas
        if price_str:
            # Replace comma with dot for conversion
            price_str = price_str.replace(',', '.')
            
            try:
                price = float(price_str)
            except ValueError:
                price = 0  # If conversion fails, set price to 0
        else:
            price = 0

        skin_names[skin_name].append(price)

    # Update dashboard with latest prices and trends
    for skin in SKINS:
        skin_name = skin['name']
        prices = skin_names.get(skin_name, [])
        
        if prices:
            latest_price = prices[-1]  # Latest price
            avg_price = sum(prices) / len(prices)  # Average price
            price_change = ((latest_price - prices[0]) / prices[0]) * 100 if prices[0] else 0  # Price change %

            # Insert values and formulas
            row_data = [
                skin_name, 
                latest_price, 
                f'=SPARKLINE(E{len(skin_names)}:E{len(skin_names)+len(prices)-1})',  # Sparkline chart
                len(prices),  # Number of listings
                avg_price, 
                price_change
            ]

            # Update the row in the dashboard sheet
            dashboard_sheet.append_row(row_data)

# === Update Dashboard after logging new data ===
if log_rows:
    update_dashboard(log_rows)
    print("✅ Dashboard updated with the latest data.")
