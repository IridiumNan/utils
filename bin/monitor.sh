#!/home/cai/miniconda3/bin/python

#!/usr/bin/env python3
"""
进程监控推送脚本（Python 版）
用法: ./monitor_process.py <PID> [日志文件路径]
"""

import os
import sys
import time
import json
import subprocess
import requests
from requests.exceptions import RequestException

# ================= 配置区 =================
BARK_URL = "http://100.120.81.67:9001"
BARK_KEY = "EsUT5MuPh9eGw9yHQKRoNb"
LOG_LINES = 50
TIMEOUT_SEC = 10  # 请求超时时间
SLEEP_INTERVAL = 2  # 检查进程间隔（秒）
ICON_URL = (
    "https://dong-dynabook-satellite-b35-r.tail015922.ts.net/icon/ubuntu_logo.jpeg"
)
# =========================================


def get_process_name(pid):
    """通过 ps 命令获取进程名，兼容无 psutil 环境"""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "comm="],
            capture_output=True,
            text=True,
            check=True,
        )
        name = result.stdout.strip()
        return name if name else "未知"
    except subprocess.CalledProcessError:
        return "未知"


def tail_file(filepath, n):
    """读取文件最后 n 行，返回字符串"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            # 简单实现：读取所有行取最后 n 行（适合小文件）
            lines = f.readlines()
            return "".join(lines[-n:])
    except FileNotFoundError:
        return f"未找到日志文件: {filepath}"
    except Exception as e:
        return f"读取日志文件出错: {e}"


def send_bark_notification(title, body):
    """发送 Bark 推送，自动处理 JSON 转义"""
    url = f"{BARK_URL}/{BARK_KEY}"
    payload = {
        "title": title,
        "body": body,
        "sound": "alarm",
        "isArchive": "1",
        "icon": ICON_URL,
    }
    try:
        resp = requests.post(
            url,
            json=payload,  # 自动转义并设置 Content-Type
            timeout=TIMEOUT_SEC,
        )
        if resp.status_code == 200:
            print("✅ 推送成功！")
        else:
            print(f"❌ 推送失败 (HTTP {resp.status_code})")
            print(f"响应内容: {resp.text}")
    except RequestException as e:
        print(f"❌ 请求异常: {e}")


def main():
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <进程PID> [日志文件路径]")
        sys.exit(1)

    try:
        pid = int(sys.argv[1])
    except ValueError:
        print("错误: PID 必须是整数")
        sys.exit(1)

    log_file = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"开始检查进程 PID: {pid} ...")

    # 获取进程名（如果进程存在）
    if os.path.exists(f"/proc/{pid}"):  # Linux 特有，但简单快速
        process_name = get_process_name(pid)
        print(f"进程名: {process_name}")
    else:
        process_name = "已结束的进程"
        print(f"进程 {pid} 已不存在，将直接发送通知。")

    # 检查进程是否正在运行
    try:
        os.kill(pid, 0)  # 发送空信号检查进程存在性
        process_exists = True
    except OSError:
        process_exists = False

    if not process_exists:
        print("⚠️ 警告：进程已结束或不存在！将立即发送通知。")
        exit_code = 1
        log_content = "进程在监控开始前已结束。未捕获到运行日志。"
    else:
        print("进程正在运行，开始等待...")
        while True:
            try:
                os.kill(pid, 0)
                time.sleep(SLEEP_INTERVAL)
            except OSError:
                break
        print("进程已结束。")
        exit_code = 0  # 无法获取真实退出码，假设正常

    # 读取日志
    if log_file:
        log_content = tail_file(log_file, LOG_LINES)
    else:
        log_content = "未指定日志文件。"

    # 构建消息
    if exit_code == 0:
        status_msg = f"✅ 进程 {pid} ({process_name}) 已完成"
    else:
        status_msg = f"⚠️ 进程 {pid} ({process_name}) 已结束 (可能已提前退出)"

    title = f"监控通知: PID {pid} ({process_name})"
    body = f"{status_msg}\n\n--- 日志内容 ---\n{log_content}"

    # 发送推送
    send_bark_notification(title, body)


if __name__ == "__main__":
    main()
