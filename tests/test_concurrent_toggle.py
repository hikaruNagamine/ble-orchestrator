import asyncio
import subprocess
from datetime import datetime
import os

mac_address = "34:85:18:18:57:C2"
service_uuid = "cba20d00-224d-11e6-9fb8-0002a5d5c51b"
char_uuid = "cba20002-224d-11e6-9fb8-0002a5d5c51b"
commands = ["570101", "570102"]
log_file = "concurrent_toggle_test.log"

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    with open(log_file, "a") as f:
        f.write(line + "\n")
    print(line)

async def send_command(hex_cmd):
    cmd = [
        "python3",
        "ble_orchestrator/examples/send_command_example.py",
        mac_address,
        service_uuid,
        char_uuid,
        hex_cmd
    ]
    log(f"Executing command: {hex_cmd}")
    try:
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await result.communicate()

        stdout_str = stdout.decode().strip()
        stderr_str = stderr.decode().strip()

        log(f"stdout:\n{stdout_str}")
        log(f"stderr:\n{stderr_str}")

        if "ERROR" in stdout_str or "ERROR" in stderr_str:
            log("Error detected, stopping test.")
            raise Exception("Error occurred")

    except Exception as e:
        log(f"Exception: {e}")
        raise

async def main():
    index = 0
    while True:
        hex_cmd = commands[index % 2]
        log(f"Starting batch of 10 commands: {hex_cmd}")
        tasks = [send_command(hex_cmd) for _ in range(10)]

        try:
            await asyncio.gather(*tasks)
        except Exception:
            break

        index += 1
        await asyncio.sleep(2)

    log("Test finished.")

if __name__ == "__main__":
    asyncio.run(main())
