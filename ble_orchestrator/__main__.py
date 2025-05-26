#!/usr/bin/env python3
"""
BLE Orchestratorのパッケージエントリーポイント
python -m ble_orchestrator で実行される
"""

import sys
import asyncio
from .main import main

if __name__ == "__main__":
    try:
        # Pythonバージョンチェック
        if sys.version_info < (3, 9):
            print("Error: Python 3.9 or higher is required")
            sys.exit(1)
            
        # メイン実行
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1) 