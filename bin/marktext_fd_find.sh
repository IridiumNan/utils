#!/bin/bash

# 检查依赖
check_dependency() {
    if ! command -v "$1" &>/dev/null; then
        echo "error: can't find the command $1, please install it"
        exit 1
    fi
}
check_dependency "fd"
check_dependency "marktext"

# 如果没有参数，直接打开 marktext
if [ $# -eq 0 ]; then
    marktext &
    exit 0
fi

# 遍历所有输入的关键词
for keyword in "$@"; do
    # 用 fd 搜索文件（不限制路径，全局搜索）
    found_file=$(fd "$keyword" | head -n 1)

    if [ -z "$found_file" ]; then
        echo "warning: no file found for '$keyword'"
        continue
    fi

    echo "found: $found_file"
    marktext "$found_file" &>/dev/null &
done
