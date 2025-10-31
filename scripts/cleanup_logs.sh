#!/bin/bash
#
# BLE Orchestrator ログクリーンアップスクリプト
# 古いログファイルを削除し、ディスク容量を管理します
#
# 使用方法:
#   ./cleanup_logs.sh [LOG_DIR] [MAX_SIZE_MB] [MAX_AGE_DAYS]
#
# 例:
#   ./cleanup_logs.sh /var/log/ble-orchestrator 100 30
#

set -e

# デフォルト設定
DEFAULT_LOG_DIR="/var/log/ble-orchestrator"
DEFAULT_MAX_SIZE_MB=100
DEFAULT_MAX_AGE_DAYS=30

# 引数の取得
LOG_DIR="${1:-$DEFAULT_LOG_DIR}"
MAX_SIZE_MB="${2:-$DEFAULT_MAX_SIZE_MB}"
MAX_AGE_DAYS="${3:-$DEFAULT_MAX_AGE_DAYS}"

# ログディレクトリの存在確認
if [ ! -d "$LOG_DIR" ]; then
    echo "Log directory does not exist: $LOG_DIR"
    exit 1
fi

echo "BLE Orchestrator Log Cleanup"
echo "============================"
echo "Log directory: $LOG_DIR"
echo "Max size: ${MAX_SIZE_MB}MB"
echo "Max age: ${MAX_AGE_DAYS} days"
echo ""

# 現在のディレクトリサイズを取得
get_dir_size_mb() {
    du -sm "$LOG_DIR" 2>/dev/null | cut -f1
}

# 現在のサイズを表示
CURRENT_SIZE=$(get_dir_size_mb)
echo "Current size: ${CURRENT_SIZE}MB"

# 古いファイルを削除
echo ""
echo "Cleaning up old files (older than ${MAX_AGE_DAYS} days)..."
DELETED_COUNT=$(find "$LOG_DIR" -name "*.log.*" -type f -mtime +${MAX_AGE_DAYS} -print -delete | wc -l)
echo "Deleted $DELETED_COUNT old files"

# サイズチェックと削除
CURRENT_SIZE=$(get_dir_size_mb)
if [ "$CURRENT_SIZE" -gt "$MAX_SIZE_MB" ]; then
    echo ""
    echo "Directory size (${CURRENT_SIZE}MB) exceeds limit (${MAX_SIZE_MB}MB)"
    echo "Removing oldest backup files..."
    
    # 古いバックアップファイルから削除
    while [ "$CURRENT_SIZE" -gt "$MAX_SIZE_MB" ]; do
        OLDEST_FILE=$(find "$LOG_DIR" -name "*.log.*" -type f -printf '%T+ %p\n' 2>/dev/null | sort | head -n 1 | cut -d' ' -f2-)
        
        if [ -z "$OLDEST_FILE" ]; then
            echo "No more backup files to delete"
            break
        fi
        
        echo "Deleting: $(basename "$OLDEST_FILE")"
        rm -f "$OLDEST_FILE"
        
        CURRENT_SIZE=$(get_dir_size_mb)
    done
fi

# 未圧縮の古いバックアップを圧縮（gzipが利用可能な場合）
if command -v gzip &> /dev/null; then
    echo ""
    echo "Compressing old uncompressed backup files (older than 7 days)..."
    COMPRESSED_COUNT=0
    
    find "$LOG_DIR" -name "*.log.[0-9]*" -type f -mtime +7 2>/dev/null | while read -r file; do
        # .gz拡張子がついていないファイルのみ圧縮
        if [[ ! "$file" =~ \.gz$ ]]; then
            echo "Compressing: $(basename "$file")"
            gzip "$file"
            COMPRESSED_COUNT=$((COMPRESSED_COUNT + 1))
        fi
    done
    
    echo "Compressed files: $COMPRESSED_COUNT"
fi

# 最終結果を表示
echo ""
echo "Cleanup completed"
echo "================="
FINAL_SIZE=$(get_dir_size_mb)
FREED_SIZE=$((CURRENT_SIZE - FINAL_SIZE))
echo "Final size: ${FINAL_SIZE}MB"
echo "Space freed: ${FREED_SIZE}MB"
echo ""

# ファイル一覧を表示
echo "Current log files:"
ls -lh "$LOG_DIR"

exit 0

