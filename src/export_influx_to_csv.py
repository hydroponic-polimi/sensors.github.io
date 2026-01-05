import os
import pandas as pd
from influxdb_client import InfluxDBClient
from dotenv import load_dotenv

# ---------------------------------------------------------
# LOAD ENV FILE
# ---------------------------------------------------------
# Looks for a file named ".env" in the same directory as the script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH)

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
INFLUX_URL = os.getenv("INFLUXDB_URL", "http://192.168.100.2:8086")
ORG = os.getenv("INFLUXDB_ORG", "my-org")
BUCKET = os.getenv("INFLUXDB_BUCKET", "iot_raw")
TOKEN = os.getenv("INFLUXDB_TOKEN")

if not TOKEN:
    raise RuntimeError("INFLUXDB_TOKEN missing! Make sure it is defined in .env")


# How far back in time to export (change if you want)
RANGE_START = "-24h"   # last 24 hour

DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------------------------------------
# UNIT DETECTION
# ---------------------------------------------------------
def infer_unit(group: pd.DataFrame) -> str | None:
    """Determine unit from HA tags or measurement name."""
    # 1) unit_of_measurement tag, if present
    if "unit_of_measurement" in group.columns:
        u = group["unit_of_measurement"].dropna().unique()
        if len(u) == 1:
            return u[0]

    # 2) Use _measurement if it looks like a unit
    if "_measurement" in group.columns:
        meas = group["_measurement"].dropna().unique()
        if len(meas) == 1:
            m = meas[0]
            # crude heuristics; extend if needed
            if any(sym in m for sym in ["°", "%", "lx", "lux", "ppm", "pH", "C", "F"]):
                return m

    return None

# ---------------------------------------------------------
# MAIN EXPORT LOGIC
# ---------------------------------------------------------
def main():
    if not TOKEN or TOKEN == "REPLACE_WITH_YOUR_TOKEN":
        raise RuntimeError("INFLUXDB_TOKEN not set and no fallback token provided.")

    client = InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG)
    query_api = client.query_api()

    query = f"""
from(bucket: "{BUCKET}")
  |> range(start: {RANGE_START})
  |> filter(fn: (r) => r["_field"] == "value")
  |> filter(fn: (r) => exists r["entity_id"])
  |> aggregateWindow(every: 1m, fn: mean, createEmpty: true)
  |> fill(usePrevious: true)
"""

    print("Running Flux query...")
    df = query_api.query_data_frame(query=query, org=ORG)

    if isinstance(df, list):
        df = pd.concat(df, ignore_index=True)

    if df.empty:
        print("No data returned from InfluxDB.")
        return

    df = df.rename(columns={"_time": "time", "_value": "value"})
    df["time"] = pd.to_datetime(df["time"])

    if "entity_id" not in df.columns:
        raise RuntimeError("No 'entity_id' column in query result – check HA Influx config.")

    print("Entities found:", df["entity_id"].nunique())

    # Export one CSV per entity_id
    for entity_id, group in df.groupby("entity_id"):
        g = group.dropna(subset=["value"]).copy()
        if g.empty:
            continue

        unit = infer_unit(g)

        out = g[["time", "value"]].copy()
        out["unit"] = unit

        # sanitize filename: sensor.esp32_1_temperature -> sensor_esp32_1_temperature.csv
        safe_name = entity_id.replace(".", "_")
        filename = os.path.join(DATA_DIR, f"{safe_name}.csv")

        out.to_csv(filename, index=False)
        print(f"Wrote {filename} (rows={len(out)}, unit={unit})")

    print("Export complete.")

if __name__ == "__main__":
    main()

