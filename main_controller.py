"""main_controller.py: System orchestrator script to manage RTK data flow.
- Connects to the Raspberry Pi via SSH.
- Transfers the RTKLIB configuration file.
- Starts rtkrcv on the Raspberry Pi.
- Launches the local data server and live map visualization."""

import subprocess
import time
import sys
import os
from dotenv import load_dotenv
import paramiko

load_dotenv()

# Configuration Variables from the .env file
ROVER_HOST = os.getenv("ROVER_HOST", "0.0.0.0")
ROVER_USER = os.getenv("ROVER_USER")
ROVER_PASSWD = os.getenv("ROVER_PASSWD")
ROVER_PORT = int(os.getenv("ROVER_PORT","22"))
RTKLIB_CONFIG_PATH = os.getenv("RTKLIB_CONFIG_PATH", "rtklib.conf")
SERVER_SCRIPT_PATH = os.getenv("SERVER_SCRIPT_PATH", "server.py")
PLOT_SCRIPT_PATH = os.getenv("PLOT_SCRIPT_PATH", "map.py")

RTKCONFIG_UPDATES = {
    "inpstr1-path": os.getenv("RTKLIB_CONFIG_INPUT_PATH"),
    "outstr1-path": os.getenv("RTKLIB_CONFIG_OUTPUT_PATH"),
    "inpstr2-path": os.getenv("RTKLIB_CONFIG_CORRECTION_CREDENTIALS")
}

def update_config(file_path, updates):
    """Updates the RTKLIB configuration file with new input and output parameters."""
    lines = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                lines.append(line)
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                if key.strip() in updates:
                    line = f"{key}={updates[key.strip()]}"
            lines.append(line)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def run_routine():
    """
    Main function to run the entire IoT routine for RTK positioning system.
    
    Orchestrates the following workflow:
    1. Establishes SSH connection to Raspberry Pi rover
    2. Updates and transfers RTKLIB configuration file to remote device
    3. Starts local data server in background
    4. Launches live map plotter GUI
    5. Executes RTK receiver (rtkrcv) on Raspberry Pi
    6. Monitors all processes and handles shutdown
    
    The function maintains three background processes:
    - local_server_process: TCP server for data streaming
    - plotter_process: Map visualization GUI
    - remote SSH session: RTK receiver on Raspberry Pi
    """

    ssh = None
    local_server_process = None
    plotter_process = None

    try:
        # 1. SSH Connection to Raspberry Pi
        print(f"[INFO] Connecting to {ROVER_HOST}:{ROVER_PORT}...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        ssh.connect(
            ROVER_HOST,
            port=ROVER_PORT,
            username=ROVER_USER,
            password=ROVER_PASSWD
        )
        print("[OK] Connected to the Rover.")

        # Define paths for configuration file transfer
        remote_desktop_path = f"/home/{ROVER_USER}/Desktop"
        remote_file_path = f"{remote_desktop_path}/{RTKLIB_CONFIG_PATH}"
        local_file_path = os.path.join(os.getcwd(), RTKLIB_CONFIG_PATH)

        # 2. Update and transfer RTKLIB configuration file
        print(f"[INFO] Copying {RTKLIB_CONFIG_PATH} to remote Desktop...")
        sftp = ssh.open_sftp()
        try:
            print(f"[INFO] Updating configuration file {local_file_path}...")
            update_config(local_file_path, RTKCONFIG_UPDATES)

            sftp.put(local_file_path, remote_file_path)
            print("[OK] File copied successfully.")
        except FileNotFoundError:
            print(f"[ERROR] Local file {local_file_path} does not exist.")
            return
        finally:
            sftp.close()

        # 3. Start local TCP server in background
        print(f"[INFO] Starting {SERVER_SCRIPT_PATH} on local PC...")
        local_server_process = subprocess.Popen([sys.executable, "-u", SERVER_SCRIPT_PATH])
        print(f"[OK] Data server started (PID: {local_server_process.pid}).")

        # 4. Start map plotter GUI in background
        print(f"[INFO] Opening map ({PLOT_SCRIPT_PATH})...")
        plotter_process = subprocess.Popen([sys.executable, PLOT_SCRIPT_PATH])
        print(f"[OK] GUI started (PID: {plotter_process.pid}).")

        # Give some time for server and plotter to initialize
        time.sleep(2)

        # 5. rtkrcv execution on Raspberry Pi
        cmd_raspberry = f"cd {remote_desktop_path} && rtkrcv -o {RTKLIB_CONFIG_PATH} -s -nc"
        print(f"[INFO] Remote execution: {cmd_raspberry}")

        # Execute the command with a pseudo-terminal to simulate a real terminal for rtkrcv CLI
        stdin, stdout, stderr = ssh.exec_command(cmd_raspberry, get_pty=True)

        # 6. Monitor processes
        print("-" * 40)
        print("SYSTEM ACTIVE.")
        print("  -> TCP Server: Active")
        print("  -> Plotter: Active")
        print("  -> Raspberry: RTK processing started")
        print("Press Ctrl+C to terminate.")
        print("-" * 40)

        # Infinite loop
        while True:
            # no need to read ssh stdout, just clear it to avoid blocking
            if stdout.channel.recv_ready():
                _ = stdout.channel.recv(1024)

            # Check if local server has crashed
            if local_server_process.poll() is not None:
                print("\n[WARNING] Data server has unexpectedly closed!")
                break

            # Check if plotter has crashed
            if plotter_process.poll() is not None:
                pass

            # Sleep briefly to reduce CPU usage
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n[INFO] Interrupt detected (Ctrl+C). Starting shutdown procedure...")

    except paramiko.SSHException as e:
        print(f"\n[ERROR] SSH error: {e}")

    except Exception as e:
        print(f"\n[ERROR] Generic error: {e}")

    finally:
        # 6. Cleanup procedure
        print("-" * 40)

        # Closing GUI
        if plotter_process:
            print("[CLEANUP] Closing map...")
            plotter_process.terminate() # request graceful termination
            try:
                plotter_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                plotter_process.kill() # force kill if not closed after timeout
            print("[OK] Map closed.")

        # Closing Local Server
        if local_server_process:
            print("[CLEANUP] Closing data server...")
            local_server_process.terminate()
            try:
                local_server_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                local_server_process.kill()
            print("[OK] Server terminated.")

        # Closing rtkrcv on Raspberry Pi rover and SSH connection
        if ssh:
            print("[CLEANUP] Stopping rtkrcv on Raspberry Pi...")
            try:
                ssh.exec_command("killall rtkrcv")
            except paramiko.SSHException:
                pass
            time.sleep(1)
            ssh.close()
            print("[END] SSH connection closed.")

        print("[END] Shutdown complete. Exiting.")

if __name__ == "__main__":
    run_routine()
