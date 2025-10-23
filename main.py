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
latest_sell_counts = {}

for skin in SKINS:
    try:
        url = f"https://buff.163.com/api/market/goods/sell_order?game=csgo&goods_id={skin['goods_id']}&page_num=1&sort_by=default"
        response = requests.get(url, headers=headers)
        data = response.json()

        orders = data["data"]["items"]
        sell_count = data["data"]["total_count"]
        latest_sell_counts[skin['name']] = sell_count  # 🔥 Store for Dashboard

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
            sell_count = latest_sell_counts.get(skin_name, "N/A")  # ✅ Use live listing count

            row_data = [
                skin_name,
                latest_price,
                f'=SPARKLINE(E2:E{len(prices)+1})',
                sell_count,
                round(avg_price, 2),
                round(price_change, 2)
            ]

            dashboard_sheet.append_row(row_data)

if log_rows:
    update_dashboard()
    print("✅ Dashboard updated with the latest data.")
    # === ARIMA Forecasting ===
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

def run_forecasting():
    print("🔮 Running ARIMA price forecasting...")

    try:
        # Load all log data from HistoryLog
        log_data = log_sheet.get_all_records()
        df = pd.DataFrame(log_data)

        if df.empty:
            print("⚠️ No historical data found for forecasting.")
            return

        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        df["Price (¥)"] = pd.to_numeric(df["Price (¥)"], errors="coerce")
        df = df.dropna(subset=["Price (¥)"])

        # Create or open forecast sheet
        try:
            forecast_sheet = spreadsheet.worksheet("Forecast")
        except:
            forecast_sheet = spreadsheet.add_worksheet(title="Forecast", rows="200", cols="5")
            forecast_sheet.append_row(["Skin Name", "Date", "Predicted Price (¥)"])

        forecast_sheet.clear()
        forecast_sheet.append_row(["Skin Name", "Date", "Predicted Price (¥)"])

        # Loop through each skin
        for skin_name in df["Skin Name"].unique():
            skin_df = df[df["Skin Name"] == skin_name].copy()
            skin_df = skin_df.sort_values("Timestamp")

            if len(skin_df) < 5:
                print(f"⚠️ Not enough data to forecast for {skin_name} ({len(skin_df)} points).")
                continue

            price_series = skin_df["Price (¥)"].values

            try:
                model = ARIMA(price_series, order=(1, 1, 1))
                model_fit = model.fit()
                forecast = model_fit.forecast(steps=7)

                # Generate 7 future dates starting from last known date
                last_date = skin_df["Timestamp"].iloc[-1]
                forecast_dates = pd.date_range(start=last_date, periods=7, freq="D")

                forecast_df = pd.DataFrame({
                    "Skin Name": [skin_name] * 7,
                    "Date": [d.strftime("%Y-%m-%d") for d in forecast_dates],
                    "Predicted Price (¥)": [round(p, 2) for p in forecast]
                })

                forecast_sheet.append_rows(forecast_df.values.tolist(), value_input_option="USER_ENTERED")

                print(f"✅ Forecast complete for {skin_name}")

            except Exception as e:
                print(f"❌ Forecast failed for {skin_name}: {e}")

    except Exception as e:
        print(f"❌ Forecasting error: {e}")

# Run forecasting only if new data was logged
if log_rows:
    run_forecasting()
    print("✅ ARIMA forecasting completed and written to 'Forecast' sheet.")

