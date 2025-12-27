"""Monitoring application for RTK data stored in InfluxDB 3, with live map plotting using TkinterMapView."""
import os
import tkinter as tk
from tkintermapview import TkinterMapView
from influxdb_client_3 import InfluxDBClient3
import pandas
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION MAP VIEW---
PLOT_REFRESH_RATE_MS = int(os.getenv("PLOT_REFRESH_RATE_MS", "1000"))
PLOT_ZOOM_LEVEL = int(os.getenv("PLOT_ZOOM_LEVEL", "19"))

# --- CONFIGURATION INFLUXDB 3 ---
INFLUXDB_HOST = os.getenv("INFLUXDB_HOST")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUXDB_DBNAME = os.getenv("INFLUXDB_DBNAME")
INFLUXDB_TABLE = os.getenv("INFLUXDB_TABLE")

class RTKMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Monitor RTK Live - InfluxDB 3")
        self.root.geometry("1000x700")

        # 1. Setup Client InfluxDB
        try:
            self.client = InfluxDBClient3(
                host=INFLUXDB_HOST,
                token=INFLUXDB_TOKEN,
                database=INFLUXDB_DBNAME
            )
            print("InfluxDB client initialized.")
        except Exception as e:
            print(f"Erorr initializing InfluxDB: {e}")

        # 2. Setup della Mappa
        self.map_widget = TkinterMapView(self.root, width=800, height=600, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_tile_server("https://a.tile.openstreetmap.org/{z}/{x}/{y}.png")

        # 3. Setup dashboard (Overlay)
        self.info_frame = tk.Frame(self.root, bg="white", bd=2)
        self.info_frame.place(relx=0.02, rely=0.02, anchor="nw")

        self.lbl_status = tk.Label(self.info_frame, text="Connecting to the DB...", font=("Arial", 12), bg="white")
        self.lbl_status.pack(padx=10, pady=5)

        self.lbl_coords = tk.Label(self.info_frame, text="Lat: -  Lon: -", font=("Arial", 10), bg="white")
        self.lbl_coords.pack(padx=10, pady=2)

        self.lbl_quality = tk.Label(self.info_frame, text="Q: -", font=("Arial", 12, "bold"), bg="white")
        self.lbl_quality.pack(padx=10, pady=5)

        # state variables
        self.current_marker = None
        self.path_list = []

        # Starting the update loop
        self.update_plot()

    def get_color_by_quality(self, q_val):
        """Restituisce il colore in base alla qualità RTK (Q)"""
        # Cast to int if the value is float/string
        try:
            q = int(q_val)
        except:
            q = 0

        if q == 1:
            return "green"  # Fixed
        elif q == 2:
            return "orange" # Float
        elif q == 4:
            return "blue"   # DGPS
        elif q == 5:
            return "red"    # Single
        else:
            return "gray"   # No solution

    def get_quality_label(self, q_val):
        try:
            q = int(q_val)
        except:
            return f"Q={q_val}"

        if q == 1:
            return "FIXED"
        if q == 2:
            return "FLOAT"
        if q == 4:
            return "DGPS"
        if q == 5:
            return "SINGLE"
        return f"Q={q}"

    def fetch_latest_data(self):
        """Execute a query to fetch the latest data point from InfluxDB."""
        try:
            # Take the latest DB entry
            query = f"SELECT * FROM \"{INFLUXDB_TABLE}\" ORDER BY time DESC LIMIT 1"

            # Execute the query
            table = self.client.query(query=query, language="sql")

            # Conversion to pandas DataFrame for easier handling
            df = table.to_pandas()

            if not df.empty:
                # Take the first row
                row = df.iloc[0]
                return row
            else:
                return None

        except Exception as e:
            print(f"InfluxDB query error: {e}")
            return None

    def update_plot(self):
        row = self.fetch_latest_data()

        if row is not None:
            try:
                # The latitude and longitude columns must match those in your InfluxDB
                lat = float(row['latitude'])
                lon = float(row['longitude'])

                # If quality column exists in the DB
                q = row['quality'] if 'quality' in row else 0

                # 1. Update Dashboard
                color = self.get_color_by_quality(q)
                status_text = self.get_quality_label(q)

                self.lbl_coords.config(text=f"{lat:.6f}, {lon:.6f}")
                self.lbl_quality.config(text=status_text, fg=color)
                self.lbl_status.config(text="Live from InfluxDB")

                # 2. Update Map
                if self.current_marker:
                    self.current_marker.delete()

                self.current_marker = self.map_widget.set_marker(lat, lon, text=status_text)

                # Center the map on the new position
                self.map_widget.set_position(lat, lon)

                # Initialize zoom level on first data point
                if len(self.path_list) == 0:
                    self.map_widget.set_zoom(PLOT_ZOOM_LEVEL)

                self.path_list.append((lat, lon))

            except KeyError as e:
                print(f"[ERROR]: Missing column: {e}. Check comumns name's in the InfluxDB table.")
                self.lbl_status.config(text="[ERR] Missing column.")
        else:
            self.lbl_status.config(text="No data available.")

        # Loop
        self.root.after(PLOT_REFRESH_RATE_MS, self.update_plot)

if __name__ == "__main__":
    root = tk.Tk()
    app = RTKMonitorApp(root)
    root.mainloop()
