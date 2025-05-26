    def __init__(self):
        """
        サーバーの初期化
        各コンポーネントのインスタンス化と連携設定
        """
        # スキャナー
        self.scanner = BLEScanner()
        
        # BLE処理ハンドラの初期化
        self.handler = BLERequestHandler(
            get_device_func=self.scanner.cache.get_device,
            get_scan_data_func=self.scanner.cache.get_device  # スキャンキャッシュから取得する関数を渡す
        )
        
        # リクエストキュー
        self.queue_manager = RequestQueueManager(self.handler.handle_request)
        
        # ウォッチドッグ
        self.watchdog = BLEWatchdog(
            self.handler.get_consecutive_failures,
            self.handler.reset_failure_count
        )
