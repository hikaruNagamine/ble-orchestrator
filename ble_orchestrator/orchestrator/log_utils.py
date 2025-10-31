"""
ログ管理ユーティリティ
ログファイルのクリーンアップと監視機能を提供
"""

import logging
import os
import time
from pathlib import Path
from typing import List, Optional
import gzip
import shutil

logger = logging.getLogger(__name__)


class LogDirectoryManager:
    """
    ログディレクトリの管理クラス
    古いログファイルの削除、圧縮、サイズ監視などを行う
    """
    
    def __init__(
        self,
        log_dir: str,
        max_total_size_mb: float = 100.0,
        max_age_days: int = 30,
        enable_compression: bool = True,
        compression_age_days: int = 7
    ):
        """
        初期化
        
        Args:
            log_dir: ログディレクトリのパス
            max_total_size_mb: ログディレクトリの最大サイズ（MB）
            max_age_days: ログファイルの最大保持期間（日）
            enable_compression: 古いログの圧縮を有効化
            compression_age_days: 圧縮対象とする日数
        """
        self.log_dir = Path(log_dir)
        self.max_total_size_bytes = int(max_total_size_mb * 1024 * 1024)
        self.max_age_seconds = max_age_days * 24 * 3600
        self.enable_compression = enable_compression
        self.compression_age_seconds = compression_age_days * 24 * 3600
        
    def get_log_files(self, include_compressed: bool = True) -> List[Path]:
        """
        ログファイルのリストを取得
        
        Args:
            include_compressed: 圧縮ファイルを含めるか
            
        Returns:
            ログファイルのパスのリスト（更新日時の古い順）
        """
        if not self.log_dir.exists():
            return []
        
        patterns = ["*.log", "*.log.*"]
        if include_compressed:
            patterns.extend(["*.log.*.gz"])
        
        files = []
        for pattern in patterns:
            files.extend(self.log_dir.glob(pattern))
        
        # 更新日時でソート（古い順）
        files.sort(key=lambda f: f.stat().st_mtime)
        
        return files
    
    def get_directory_size(self) -> int:
        """
        ログディレクトリの合計サイズを取得（バイト）
        
        Returns:
            ディレクトリの合計サイズ（バイト）
        """
        if not self.log_dir.exists():
            return 0
        
        total_size = 0
        for file_path in self.get_log_files():
            try:
                total_size += file_path.stat().st_size
            except (OSError, FileNotFoundError):
                continue
        
        return total_size
    
    def cleanup_old_files(self) -> int:
        """
        古いログファイルを削除
        
        Returns:
            削除したファイル数
        """
        current_time = time.time()
        deleted_count = 0
        
        for file_path in self.get_log_files():
            try:
                file_age = current_time - file_path.stat().st_mtime
                
                if file_age > self.max_age_seconds:
                    logger.info(f"Deleting old log file: {file_path.name} (age: {file_age/86400:.1f} days)")
                    file_path.unlink()
                    deleted_count += 1
            except (OSError, FileNotFoundError) as e:
                logger.warning(f"Error deleting file {file_path}: {e}")
                
        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} old log files")
            
        return deleted_count
    
    def cleanup_by_size(self) -> int:
        """
        サイズ制限に基づいてログファイルを削除
        
        Returns:
            削除したファイル数
        """
        current_size = self.get_directory_size()
        
        if current_size <= self.max_total_size_bytes:
            return 0
        
        logger.warning(
            f"Log directory size ({current_size/1024/1024:.1f}MB) exceeds limit "
            f"({self.max_total_size_bytes/1024/1024:.1f}MB)"
        )
        
        deleted_count = 0
        files = self.get_log_files()
        
        # 古いファイルから削除
        for file_path in files:
            if current_size <= self.max_total_size_bytes:
                break
                
            try:
                file_size = file_path.stat().st_size
                logger.info(f"Deleting log file to reduce size: {file_path.name}")
                file_path.unlink()
                current_size -= file_size
                deleted_count += 1
            except (OSError, FileNotFoundError) as e:
                logger.warning(f"Error deleting file {file_path}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} log files to meet size limit")
            
        return deleted_count
    
    def compress_old_files(self) -> int:
        """
        古いログファイルを圧縮
        
        Returns:
            圧縮したファイル数
        """
        if not self.enable_compression:
            return 0
        
        current_time = time.time()
        compressed_count = 0
        
        for file_path in self.get_log_files(include_compressed=False):
            # 既に圧縮されているファイルはスキップ
            if file_path.suffix == ".gz":
                continue
            
            # 現在使用中のログファイルはスキップ
            if file_path.name.endswith(".log") and not any(c.isdigit() for c in file_path.name):
                continue
            
            try:
                file_age = current_time - file_path.stat().st_mtime
                
                if file_age > self.compression_age_seconds:
                    logger.info(f"Compressing old log file: {file_path.name}")
                    self._compress_file(file_path)
                    compressed_count += 1
            except (OSError, FileNotFoundError) as e:
                logger.warning(f"Error compressing file {file_path}: {e}")
        
        if compressed_count > 0:
            logger.info(f"Compressed {compressed_count} log files")
            
        return compressed_count
    
    def _compress_file(self, file_path: Path) -> None:
        """
        ファイルをgzip圧縮
        
        Args:
            file_path: 圧縮するファイルのパス
        """
        compressed_path = Path(str(file_path) + ".gz")
        
        with open(file_path, "rb") as f_in:
            with gzip.open(compressed_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # 元のファイルを削除
        file_path.unlink()
    
    def run_maintenance(self) -> dict:
        """
        ログディレクトリのメンテナンスを実行
        
        Returns:
            メンテナンス結果の辞書
        """
        logger.info("Starting log directory maintenance")
        
        # 実行前のサイズ
        size_before = self.get_directory_size()
        
        # メンテナンス実行
        compressed_count = self.compress_old_files()
        deleted_by_age = self.cleanup_old_files()
        deleted_by_size = self.cleanup_by_size()
        
        # 実行後のサイズ
        size_after = self.get_directory_size()
        
        result = {
            "compressed_files": compressed_count,
            "deleted_by_age": deleted_by_age,
            "deleted_by_size": deleted_by_size,
            "size_before_mb": size_before / 1024 / 1024,
            "size_after_mb": size_after / 1024 / 1024,
            "space_freed_mb": (size_before - size_after) / 1024 / 1024,
        }
        
        logger.info(
            f"Log maintenance completed: "
            f"compressed={compressed_count}, "
            f"deleted={deleted_by_age + deleted_by_size}, "
            f"freed={result['space_freed_mb']:.1f}MB"
        )
        
        return result
    
    def get_status(self) -> dict:
        """
        ログディレクトリの状態を取得
        
        Returns:
            状態情報の辞書
        """
        files = self.get_log_files()
        current_size = self.get_directory_size()
        
        return {
            "log_dir": str(self.log_dir),
            "total_files": len(files),
            "total_size_mb": current_size / 1024 / 1024,
            "max_size_mb": self.max_total_size_bytes / 1024 / 1024,
            "usage_percent": (current_size / self.max_total_size_bytes * 100) if self.max_total_size_bytes > 0 else 0,
            "oldest_file": files[0].name if files else None,
            "newest_file": files[-1].name if files else None,
        }


class LogMaintenanceScheduler:
    """
    ログメンテナンスのスケジューラー
    定期的にログディレクトリのメンテナンスを実行
    """
    
    def __init__(
        self,
        manager: LogDirectoryManager,
        interval_hours: float = 24.0
    ):
        """
        初期化
        
        Args:
            manager: LogDirectoryManagerインスタンス
            interval_hours: メンテナンス実行間隔（時間）
        """
        self.manager = manager
        self.interval_seconds = interval_hours * 3600
        self.last_run = 0.0
        
    def should_run(self) -> bool:
        """
        メンテナンスを実行すべきかチェック
        
        Returns:
            実行すべき場合はTrue
        """
        current_time = time.time()
        return (current_time - self.last_run) >= self.interval_seconds
    
    def run_if_needed(self) -> Optional[dict]:
        """
        必要に応じてメンテナンスを実行
        
        Returns:
            メンテナンスを実行した場合は結果、しなかった場合はNone
        """
        if not self.should_run():
            return None
        
        result = self.manager.run_maintenance()
        self.last_run = time.time()
        
        return result


# グローバルなログマネージャーインスタンス（必要に応じて使用）
_log_manager: Optional[LogDirectoryManager] = None


def get_log_manager(
    log_dir: Optional[str] = None,
    **kwargs
) -> LogDirectoryManager:
    """
    LogDirectoryManagerのシングルトンインスタンスを取得
    
    Args:
        log_dir: ログディレクトリのパス
        **kwargs: LogDirectoryManagerのその他の引数
        
    Returns:
        LogDirectoryManagerインスタンス
    """
    global _log_manager
    
    if _log_manager is None and log_dir is not None:
        _log_manager = LogDirectoryManager(log_dir, **kwargs)
    
    return _log_manager

