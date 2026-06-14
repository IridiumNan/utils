#!/usr/bin/env python3
"""
TG - TMP-GUARD - Temporary File Management Tool
Core feature: Manages temp files in ~/tmp, auto-syncs disk snapshots,
and enforces regular file cleanup via rolling snapshot deletion.
"""

import os
import sys
import subprocess
import time
import signal
import logging
import shutil
from pathlib import Path
import getpass
from contextlib import contextmanager
from typing import List

# -------------------------- Global Constants --------------------------
# Current system user running the script
USER = getpass.getuser()
# In-memory temp directory (based on /tmp tmpfs, cleared on reboot)
TMP_DIR = Path("/", "tmp", USER)
# Symlink entry in user home ~/tmp, points to the in-memory temp directory
SRC_DIR = Path.home() / "tmp"
# Root directory for disk snapshots, used as fallback backup for temp files
SNAP_DIR = Path.home() / ".cache" / "tmp-snapshots"
# Historical snapshot from last boot cycle (only 1 copy kept, deleted on next boot)
LAST_DIR = SNAP_DIR / "last"
# Real-time sync directory for the current boot cycle
CURR_DIR = SNAP_DIR / "curr"

# Default directory permission
DIR_MODE = 0o755
# Background service polling interval (seconds)
SERVE_SLEEP_INTERVAL = 1
# Buffer time to wait for data flush before service exit (seconds)
EXIT_WAIT_SECONDS = 2

# Basic logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# -------------------------- Global State Variables --------------------------
# Service stop flag, used for graceful shutdown on signal reception
stop_flag = False
# Sync mutex lock, ensures only one rsync process runs at a time
sync_lock = False


# -------------------------- Signal Handling --------------------------
def signal_handler(signum: int, frame) -> None:
    """
    Handle system termination signals
    Supports SIGTERM (systemd stop) and SIGINT (Ctrl+C) for graceful shutdown
    """
    global stop_flag
    signal_name = signal.strsignal(signum)
    logger.info(
        f"\nReceived signal {signum} ({signal_name}), exiting in {EXIT_WAIT_SECONDS}s"
    )
    stop_flag = True


# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)  # Handle systemd stop command
signal.signal(signal.SIGINT, signal_handler)  # Handle terminal Ctrl+C


# -------------------------- Sync Lock Utility --------------------------
@contextmanager
def sync_lock_context():
    """
    Context manager for sync mutex lock
    Automatically handles lock acquisition and release.
    Guarantees lock release even if exceptions occur during sync, preventing deadlocks.
    Returns True if lock is acquired successfully, False otherwise.
    """
    global sync_lock
    # Lock is already held, skip and return failure
    if sync_lock:
        yield False
        return

    try:
        sync_lock = True
        yield True
    finally:
        # Always release the lock regardless of sync success or failure
        sync_lock = False


# -------------------------- Common Utility Functions --------------------------
def ensure_dirs(path: Path) -> None:
    """
    Ensure the specified directory exists; create it if not.
    Wraps repeated directory creation logic with unified permission configuration.
    """
    os.makedirs(path, mode=DIR_MODE, exist_ok=True)
    logger.info(f"Ensured directory exists: {path}")


def backup_if_exist(path: Path) -> None:
    """
    Automatically create a .bak backup if the target file already exists.
    Prevents data loss from accidental file overwrite.
    """
    if path.exists():
        bak_path = path.with_suffix(path.suffix + ".bak")
        path.rename(bak_path)
        logger.info(f"Backed up original file: {path} -> {bak_path}")


# -------------------------- Core Business Logic --------------------------
def sync_to_snapshot() -> None:
    """
    Incrementally sync temp directory contents to the current snapshot directory.
    Uses rsync for delta sync, only syncs changed files, and auto-deletes removed files.
    """
    with sync_lock_context() as locked:
        # Failed to acquire lock, skip this sync cycle
        if not locked:
            return

        # Create symlink if ~/tmp does not exist
        if not SRC_DIR.exists():
            SRC_DIR.symlink_to(TMP_DIR, target_is_directory=True)
            logger.info(f"Created symlink: {TMP_DIR} -> {SRC_DIR}")
            return

        # Build rsync command
        rsync_cmd = [
            "rsync",
            "-a",  # Archive mode: preserves permissions, timestamps, symlinks, etc.
            "--quiet",  # Quiet mode: suppresses detailed sync output
            "--delete",  # Delete files in target that no longer exist in source, keep full consistency
            f"{SRC_DIR.as_posix()}/",
            f"{CURR_DIR.as_posix()}/",
        ]

        try:
            subprocess.run(
                rsync_cmd,
                capture_output=True,
                check=True,  # Raise exception on sync failure for error handling
                text=True,  # Return output as text instead of bytes
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Rsync sync failed: {e.stderr}")


def simple_list(path: Path) -> None:
    """
    just list name of all files/subdirectories in the specified path.
    """
    try:
        items = list(path.iterdir())
    except FileNotFoundError:
        logger.info("Snapshot directory does not exist, no files available")
        return

    if not items:
        logger.info("Snapshot directory is empty")
        return

    for item in items:
        print(item.name)


def list_info(path: Path) -> None:
    """
    List basic info of all files/subdirectories in the specified path.
    Includes file name, file size, and last modification time.
    """
    try:
        items = list(path.iterdir())
    except FileNotFoundError:
        logger.info("Snapshot directory does not exist, no files available")
        return

    if not items:
        logger.info("Snapshot directory is empty")
        return

    for item in items:
        file_stat = item.stat()
        size = file_stat.st_size
        mtime = time.ctime(file_stat.st_mtime)
        logger.info(f"{item.name}: size -> {size} bytes, modified -> {mtime}")


def list_pending(is_last: bool = True, is_simple: bool = True):
    dir = LAST_DIR if is_last else CURR_DIR

    remove_time = "next reboot" if is_last else "double reboot"
    use_command = "last-use" if is_last else "use"

    remove_hint = f"Files below will be permanently removed after {remove_time}"
    keep_hint = f"To keep a file, run: {use_command} filename <save-path>"

    if not is_simple:
        logger.info(remove_hint)
        logger.info(keep_hint)
        list_info(dir)
        return

    print(remove_hint)
    print(keep_hint)
    simple_list(dir)


def update_snapshots() -> None:
    """
    Perform snapshot rollover on service startup.
    1. Delete the old historical snapshot (last)
    2. Convert the previous current snapshot (curr) to historical snapshot (last)
    3. Create a new empty current snapshot directory for this boot cycle
    """
    logger.info("Cleaning up the following historical files:")
    list_info(LAST_DIR)

    # Remove old historical snapshot directory (supports non-empty directory deletion)
    if LAST_DIR.exists():
        shutil.rmtree(LAST_DIR)
        logger.info(f"Removed historical snapshot directory: {LAST_DIR}")

    # Roll over previous current snapshot to historical snapshot
    if CURR_DIR.exists():
        CURR_DIR.rename(LAST_DIR)
        logger.info(f"Snapshot rollover complete: {CURR_DIR} -> {LAST_DIR}")

    # Create empty snapshot directory for current boot cycle
    ensure_dirs(CURR_DIR)


def last_use_handler(file_name: str, dst_path: Path) -> None:
    src_path = LAST_DIR / file_name
    if not src_path.exists():
        logger.error(f"File {src_path} does not exist, please check the file name")
        return

    if dst_path.is_dir():
        dst_path = dst_path / file_name

    use_handler(src_path=src_path, dst_path=dst_path)


def curr_use_handler(file_name: str, dst_path: Path) -> None:
    src_path = CURR_DIR / file_name

    if not src_path.exists():
        logger.error(f"File {src_path} does not exist, please check the file name")
        return

    if dst_path.is_dir():
        dst_path = dst_path / file_name

    use_handler(src_path=src_path, dst_path=dst_path)


def use_handler(src_path: Path, dst_path: Path) -> None:
    """
    Archive a file from current snapshot via hard link for permanent preservation.
    :param file_name: Name of the file in snapshot
    :param dst_path: Target save path, supports both directory and full file path
    """
    # If target path is a directory, append the file name automatically
    # Backup if target file already exists
    backup_if_exist(dst_path)

    logger.info(f"File archived to: {dst_path}")
    try:
        # Zero-cost archiving via hard link, no extra disk space usage
        dst_path.hardlink_to(src_path)
    except OSError as e:
        logger.error(f"Failed to create hard link: {e}")


def serve() -> None:
    """Main background service loop, runs persistently to sync temp files to snapshot."""
    # Perform snapshot rollover on service startup
    update_snapshots()
    try:
        while not stop_flag:
            time.sleep(SERVE_SLEEP_INTERVAL)
            sync_to_snapshot()
    finally:
        # Reserve time before exit to ensure full data flush to disk
        logger.info(f"Waiting {EXIT_WAIT_SECONDS}s to ensure data is synced to disk")
        time.sleep(EXIT_WAIT_SECONDS)
        sys.exit(0)

def print_help(lang: str = "en") -> None:
    """Print command help information in the specified language."""
    help_en = """
TG - TMP-GUARD  v0.1
  Temporary file lifecycle manager with real‑time disk snapshot and forced cleanup.

━━━ CONCEPT ━━━
  ~/tmp  lives in RAM (tmpfs)  →  ultra‑fast writes, auto‑cleared on reboot.
  Changes are silently mirrored to disk (~/.cache/tmp-snapshots/curr) every second.
  On each boot the previous 'curr' snapshot becomes the single historical 'last' snapshot.
  Files that stay in 'last' for one whole boot cycle are permanently deleted on the next boot.

  This gives you a safe “scratch space” with a hard deadline: you have ONE boot cycle
  to review and archive anything left from the last session.  No more permanent junk.

━━━ COMMANDS ━━━
  tg serve
        Start the background sync daemon (normally launched by systemd).
        Performs snapshot rollover, then watches ~/tmp for changes every second.

  tg list [curr]
        Show files that are waiting to be cleaned up.
          (no argument)  →  files from the *previous* boot (will be deleted on next reboot)
          curr           →  files from the *current* boot (will become 'last' on next reboot)

  tg list-info [curr]
        Same as list, but also prints file size and modification time.

  tg use <filename> <target-path>
        Permanently keep a file from the *current* snapshot.
        Creates a hard link – no extra disk space, instant.
          target-path may be a directory (file name kept) or a full file path.
        If the target already exists, a .bak copy is made automatically.

  tg last-use <filename> <target-path>
        Same as 'use', but retrieves a file from the *previous* boot snapshot.
        Useful right after a reboot when you realise you forgot to save something.

  tg config [en|cn]
        Print a ready‑to‑use systemd user service template.
        Pipe the output directly into ~/.config/systemd/user/tmp-guard.service.

  tg help [en|cn]
        Show this help message.

━━━ TYPICAL WORKFLOW ━━━
  1. Set your browser / download manager to save files into ~/tmp.
  2. Work normally: unpack, compile, doodle, download – everything lands in ~/tmp.
  3. When you produce something worth keeping, just move it out:
         mv ~/tmp/report.pdf ~/Documents/
  4. If you forget to move something, the next boot will show you what's left (tg list).
  5. Rescue important leftovers with 'tg last-use' before the following reboot.

  You never need to manually clean ~/tmp – the tool enforces the deadline for you.

━━━ NOTES ━━━
  • Hard‑link rescue only works when the target is on the same filesystem as ~/.cache.
  • The 1‑second sync interval means at most the last 1 s of writes can be lost on a crash.
  • Disk usage is at most 2× the size of your temporary files (curr + last).
  • Do NOT keep files in ~/tmp that you need across multiple reboots without archiving them.
"""

    help_cn = """
TG - TMP-GUARD  v0.1
  临时文件生命周期管理器，具备实时磁盘快照与强制清理功能。

━━━ 设计理念 ━━━
  ~/tmp 位于内存 (tmpfs) → 写入极快，重启自动清空。
  文件变化每秒自动同步到磁盘快照 (~/.cache/tmp-snapshots/curr)。
  每次开机时，「本次」快照变为唯一的「上一次」历史快照，
  而「上上次」的历史快照会被彻底删除。

  这提供了一个安全的“草稿空间”，并设置了硬性期限：
  你有且仅有一个开机周期的时间来处理上一次遗留的文件，否则它们将永久消失。

━━━ 命令说明 ━━━
  tg serve
        启动后台实时同步服务（通常由 systemd 自动调用）。
        先执行快照轮换，然后每秒监控 ~/tmp 的变化并同步。

  tg list [curr]
        列出等待清理的文件。
          不带参数  →  列出“上次遗留”快照中的文件（下次重启时永久删除）
          curr     →  列出“本次”快照中的文件（再重启一次后会被清除）

  tg list-info [curr]
        与 list 类似，但额外显示文件大小和修改时间。

  tg use <文件名> <目标路径>
        从「本次」快照中永久保留指定文件。
        使用硬链接，不占用额外磁盘空间，瞬间完成。
          目标路径可以是目录（保留原文件名）或完整的文件路径。
        如果目标文件已存在，会自动创建 .bak 备份。

  tg last-use <文件名> <目标路径>
        与 use 相同，但从「上一次」遗留快照中提取文件。
        适合在开机后发现忘记保存时紧急抢救。

  tg config [en|cn]
        打印 systemd 用户服务配置模板。
        可将输出直接保存到 ~/.config/systemd/user/tmp-guard.service。

  tg help [en|cn]
        显示本帮助信息。

━━━ 典型用法 ━━━
  1. 将浏览器/下载工具的默认保存目录设置为 ~/tmp。
  2. 日常工作：解包、编译、随手下载，所有文件都丢进 ~/tmp。
  3. 产生需要保留的文件时，立即移走：
         mv ~/tmp/报表.pdf ~/文档/
  4. 如果忘记移走，下次开机时用 tg list 查看遗留文件。
  5. 在下下次开机前，用 tg last-use 抢救重要的遗留文件。

  你永远不需要手动清理 ~/tmp —— 工具会自动强制执行期限。

━━━ 注意事项 ━━━
  • 硬链接抢救仅在目标路径与 ~/.cache 处于同一文件系统时有效。
  • 1 秒的同步间隔意味着极端掉电时最多丢失最后 1 秒内的写入数据。
  • 磁盘占用最多为临时文件总量的 2 倍（curr + last）。
  • 不要将需要跨多个开机周期保留的文件长期存放在 ~/tmp 中。
"""
    print(help_en if lang.startswith("en") else help_cn)

def print_daemon_file(lang: str = "en") -> None:
    """Print systemd user service template with instructions."""
    tmpl_en = f"""
[Unit]
Description=tmp-guard real-time sync for ~/tmp
After=default.target

[Service]
Type=simple
ExecStart=%h/.local/bin/tg serve
Restart=on-failure
RestartSec=5

# Environment (uncomment to override default paths)
# Environment=TMP_GUARD_TMP_DIR=/tmp/{USER}
# Environment=TMP_GUARD_SNAP_ROOT=%h/.cache/tmp-snapshots

[Install]
WantedBy=default.target

# INSTALLATION:
#   mkdir -p ~/.config/systemd/user
#   Save this output to ~/.config/systemd/user/tmp-guard.service
#   systemctl --user daemon-reload
#   systemctl --user enable --now tmp-guard.service
"""

    tmpl_cn = f"""
[Unit]
Description=tmp-guard ~/tmp 实时同步服务
After=default.target

[Service]
Type=simple
ExecStart=%h/.local/bin/tg serve
Restart=on-failure
RestartSec=5

# 环境变量（如需覆盖默认路径，可取消注释）
# Environment=TMP_GUARD_TMP_DIR=/tmp/{USER}
# Environment=TMP_GUARD_SNAP_ROOT=%h/.cache/tmp-snapshots

[Install]
WantedBy=default.target

# 安装步骤:
#   mkdir -p ~/.config/systemd/user
#   将本输出保存为 ~/.config/systemd/user/tmp-guard.service
#   systemctl --user daemon-reload
#   systemctl --user enable --now tmp-guard.service
"""
    print(tmpl_en if lang.startswith("en") else tmpl_cn)


# -------------------------- Main Entry Function --------------------------
def main(args: List[str]) -> None:
    """
    Main program entry, parses command line arguments and dispatches corresponding functions.
    :param args: Command line argument list
    """
    # Show help by default if no arguments provided
    if len(args) < 2:
        print_help()
        return

    command = args[1].lower()

    # get lang config
    lang = "en"
    if len(args) >= 3 and command in ("help", "config"):
        possible_lang = args[2]
        if possible_lang in ("cn", "en"):
            lang = possible_lang

    if command in ["list", "ls"]:
        if len(args) == 3 and args[2].lower() == "curr":
            list_pending(is_last=False, is_simple=True)
            return

        list_pending()
    elif command in ["list-info", "ls-info"]:
        if len(args) == 3 and args[2].lower() == "curr":
            list_pending(is_last=False, is_simple=False)
            return
        list_pending(is_simple=False)

    elif command == "serve":
        # Ensure all required directories exist before service starts
        ensure_dirs(TMP_DIR)
        ensure_dirs(CURR_DIR)
        ensure_dirs(LAST_DIR)
        serve()
    elif command == "use":
        # Parameter validation
        if len(args) < 4:
            logger.error("Missing arguments for 'use' command!")
            logger.info("Usage: tg use <file-name> <save-path>")
            return
        curr_use_handler(args[2], Path(args[3]))
    elif command == "last-use":
        if len(args) < 4:
            logger.error("Missing arguments for 'use' command!")
            logger.info("Usage: tg use <file-name> <save-path>")
            return
        last_use_handler(args[2], Path(args[3]))
    elif command == "config":
        print_daemon_file(lang)
    else:
        # Show help for unknown commands
        print_help(lang)


if __name__ == "__main__":
    main(sys.argv)
