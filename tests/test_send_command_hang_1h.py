# run_toggle_test.py
import subprocess
import time
from datetime import datetime, timedelta

# 設定
mac_address = "34:85:18:18:57:C2"
service_uuid = "cba20d00-224d-11e6-9fb8-0002a5d5c51b"
char_uuid = "cba20002-224d-11e6-9fb8-0002a5d5c51b"
commands = ["570101", "570102"]
duration = timedelta(hours=1)
log_file = "toggle_test.log"

# 実行終了時刻
end_time = datetime.now() + duration

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    with open(log_file, "a") as f:
        f.write(line + "\n")
    print(line)

index = 0
while datetime.now() < end_time:
    hex_cmd = commands[index]
    cmd = [
        "python3",
        "ble_orchestrator/examples/send_command_example.py",
        mac_address,
        service_uuid,
        char_uuid,
        hex_cmd,
    ]
    log(f"Executing command: {hex_cmd}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        log(f"stdout:\n{result.stdout.strip()}")
        log(f"stderr:\n{result.stderr.strip()}")

        # "ERROR" が含まれていた場合のみ停止
        if "ERROR" in result.stdout or "ERROR" in result.stderr:
            log("Error message detected in output, stopping test.")
            break

    except subprocess.TimeoutExpired:
        log("Timeout during command execution. Stopping test.")
        break

    index = (index + 1) % 2
    time.sleep(2)

log("Test finished.")
