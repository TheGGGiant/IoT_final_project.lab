"""RTK Server for receiving RTK solution data and storing it in InfluxDB 3."""
import socket
import signal
import sys
import time
from datetime import datetime
import os
from influxdb_client_3 import InfluxDBClient3, Point
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
HOST = os.getenv("SERVER_HOST", "0.0.0.0")
PORT = int(os.getenv("SERVER_PORT", "5000"))

# --- CONFIGURATION INFLUXDB 3 ---
INFLUX_HOST = os.getenv("INFLUXDB_HOST")
INFLUX_TOKEN = os.getenv("INFLUXDB_TOKEN")
INFLUX_DB = os.getenv("INFLUXDB_DBNAME")

running = True

try:
    client = InfluxDBClient3(host=INFLUX_HOST, token=INFLUX_TOKEN, database=INFLUX_DB)
except Exception as e:
    print(f"[ERR] Unable to create Influx client: {e}")
    sys.exit(1)

def signal_handler(sig, frame):
    """Handle termination signals to gracefully shut down the server."""
    global running
    print("\n[STOP] Received termination signal. Shutting down...")
    running = False

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def dms_to_dd(d, m, s):
    """RTKLIB provides coordinates in DMS format; convert to decimal degrees."""
    try:
        return float(d) + float(m)/60 + float(s)/3600
    except ValueError:
        return 0.0

def parse_and_send(line):
    """parse the RTKlib solution line and send it to InfluxDB 3."""
    if not running:
        return # if it's stopping, do nothing

    try:
        parts = line.split()
        if len(parts) < 19 or line.startswith('%'): # invalid line
            return

        # 1. Parsing date/time
        dt_str = f"{parts[0]} {parts[1]}"
        timestamp = datetime.strptime(dt_str, "%Y/%m/%d %H:%M:%S.%f")

        # 2. Parsing geometry
        lat_dd = dms_to_dd(parts[2], parts[3], parts[4])
        lon_dd = dms_to_dd(parts[5], parts[6], parts[7])
        height = float(parts[8])
        quality = int(parts[9])

        # 3. Parsing accuracy and other info
        ns = int(parts[10])         # number of visible satellites
        sdn = float(parts[11])      # Std Dev North (m)
        sde = float(parts[12])      # Std Dev East (m)
        sdu = float(parts[13])      # Std Dev Up (m)
        # covariance values
        sdne = float(parts[14])
        sdeu = float(parts[15])
        sdue = float(parts[16])
        age = float(parts[17])      # Age of observations between rover and base (s)
        ratio = float(parts[18])    # Ratio factor (?)

        # 4. Creation of InfluxDB Point (for writing on the DB)
        point = (
            Point("gps_rtk")
            .tag("rover_id", "raspberry_01")
            .field("latitude", lat_dd)
            .field("longitude", lon_dd)
            .field("height", height)
            .field("quality", quality)
            .field("satellites", ns)
            .field("sd_north", sdn)
            .field("sd_east", sde)
            .field("sd_up", sdu)
            .field("sd_ne", sdne)
            .field("sd_eu", sdeu)
            .field("sd_ue", sdue)
            .field("age", age)
            .field("ar_ratio", ratio)
            .time(timestamp)
        )

        # --- WRITE TO INFLUXDB 3 ---
        try:
            client.write(point)
            print(f"[DB] {dt_str} lat={lat_dd:2.6f} lon={lon_dd:2.6f} Q={quality} Sats={ns}", end='\r')
        except Exception as e:
            if not running: # if stopping, ignore DB write errors
                pass
            else:
                print(f"\n[ERROR] DB Write: {e}")

    except Exception as e:
        print(f"\n[ERROR] Parsing: {e}")

def start_server():
    """" Start the RTK server to listen for incoming RTK solution data.
    1. Listens on specified HOST and PORT.
    2. Parses incoming RTK solution lines.
    3. Stores parsed data into InfluxDB 3.
    4. Shuts down after a period of inactivity.
    """""

    global running
    print(f"--- Server RTK active on port {PORT} ---")

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    #Initialize inactivity timer
    start_activity = time.time()
    inactivity_timeout = 20

    print(f"[INFO] The server will automatically shut down after {inactivity_timeout} seconds of inactivity.\n")

    try:
        # server setup
        server_socket.bind((HOST, PORT))
        server_socket.listen()
        server_socket.settimeout(1.0)

        while running:
            try:
                conn, addr = server_socket.accept()

                start_activity = time.time()
            except socket.timeout:
                # If no connection is received, check inactivity timer
                elapsed_time = time.time() - start_activity

                if elapsed_time >= inactivity_timeout:
                    print(f"[INFO] The server will automatically shut down after {inactivity_timeout} seconds of inactivity.\n")
                    break
                continue
            except OSError:
                break

            with conn:
                print(f"\n[CONN] Connected from: {addr}")
                buffer_str = ""
                conn.settimeout(2.0) # timeout for recv calls to check inactivity

                while running:
                    try:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break

                        # reset inactivity timer on data reception
                        start_activity = time.time()

                        buffer_str += chunk.decode('utf-8', errors='ignore')
                        # process complete lines in buffer
                        while '\n' in buffer_str:
                            line, buffer_str = buffer_str.split('\n', 1)
                            parse_and_send(line.strip())

                    except socket.timeout:
                        # if no data is received, just continue the loop
                        # check inactivity timer
                        if time.time() - start_activity > inactivity_timeout:
                            running = False
                            break
                        continue
                    except Exception as e:
                        print(f"\n[ERROR] Connection: {e}")
                        break

            print("\n[INFO] Connection closed. Returning to listening (Timer reset).")
            # reset inactivity timer to give 20 more seconds until next attempt
            start_activity = time.time()

    except Exception as e:
        if running:
            print(f"\n[FATAL] {e}")
    finally:
        print("\n[CLEANUP] Closing socket and DB...")
        server_socket.close()
        try:
            client.close()
        except:
            pass
        print("[END] Server is offline.")

if __name__ == "__main__":
    start_server()
