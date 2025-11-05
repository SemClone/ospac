#!/usr/bin/env python3
"""Monitor OSPAC data generation progress."""

import json
import time
from pathlib import Path

def monitor_progress():
    """Monitor the progress of OSPAC data generation."""
    data_dir = Path("data")
    progress_file = data_dir / "generation_progress.json"

    while True:
        if progress_file.exists():
            try:
                with open(progress_file, 'r') as f:
                    progress = json.load(f)

                total = progress.get('total_processed', 0)
                last_updated = progress.get('last_updated', 'Unknown')

                print(f"\r[{time.strftime('%H:%M:%S')}] Processed: {total}/712 licenses (Last: {last_updated[:19]})", end='', flush=True)

                # Check if any recent license files were created
                spdx_dir = data_dir / "licenses" / "spdx"
                if spdx_dir.exists():
                    actual_count = len(list(spdx_dir.glob("*.yaml")))
                    if actual_count != total:
                        print(f" | Files: {actual_count}")

            except Exception as e:
                print(f"\rError reading progress: {e}", end='', flush=True)
        else:
            print(f"\r[{time.strftime('%H:%M:%S')}] Waiting for progress file...", end='', flush=True)

        time.sleep(5)

if __name__ == "__main__":
    try:
        monitor_progress()
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")