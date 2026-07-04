#!/bin/bash
set -euo pipefail

# Global paths
BASE_STATE="$HOME/.local/state/package-snapshots"
DIR_LATEST="${BASE_STATE}/snap-latest"
DIR_HISTORY="${BASE_STATE}/snap-history"
SNAP_LOG="${BASE_STATE}/snapshot-log.txt"
MAX_KEEP=30

# Default variables
COMMENT=""
TIMESTAMP=$(date +%Y-%m-%d_%H-%M)
CURR_HIST_DIR="${DIR_HISTORY}/${TIMESTAMP}"

# Short help (-h)
short_usage() {
    cat <<EOF
Usage: $(basename "$0") [COMMAND | OPTIONS]
Subcommands:
    log                 Open snapshot log with less pager
Options:
    -c "TEXT"           Attach comment to snapshot
    -h                  Show short help
    -H                  Show full detailed help manual
EOF
}

# Full detailed help (-H)
full_help() {
    cat <<EOF
================================================================================
Package Snapshot Tool - Full Manual
================================================================================
Purpose
    Create versioned Arch Linux package snapshots, track installation history,
    store explicit official/AUR packages, modified pacman configs & systemd units.

Directory Layout
    ~/.local/state/package-snapshots/
    ├── snapshot-log.txt          Log: timestamp | snapshot path | comment
    ├── snap-latest/              Symlink dir always pointing to newest snapshot
    │   ├── 01-explicit-official.txt
    │   ├── 02-all-packages.txt
    │   ├── 03-explicit-aur.txt
    │   ├── 04-modified-pacman-configs.txt
    │   └── 05-enabled-systemd-units.txt
    └── snap-history/             Timestamped archived snapshots
        ├── 2026-07-04_20-10/
        └── 2026-07-04_21-58/

Subcommands
    log
        Open snapshot-log.txt with less to view all historical snapshots and comments

Options
    -c "COMMENT_STRING"
        Attach human readable note to current snapshot entry in log file
        Wrap text with quotes if spaces exist.

    -h
        Print brief minimal usage help.

    -H
        Print this complete detailed manual.

Behavior Rules
    1. Auto clean old snapshots, keep only latest ${MAX_KEEP} archives
    2. snap-latest directory is rebuilt on every run via symlinks
    3. Log format: YYYY-MM-DD_HH-MM | full_snapshot_path | user_comment
    4. Auto detect paru/yay for AUR explicit package list export

Common Examples
1. Create snapshot with comment
    $(basename "$0") -c "After full system update + Hyprland rebuild"

2. View snapshot history log
    $(basename "$0") log

3. Quick short help
    $(basename "$0") -h

4. Full detailed manual
    $(basename "$0") -H

System Restore Commands (new machine recovery)
# Install all manually installed official packages
grep -v '^#' "$DIR_LATEST/01-explicit-official.txt" | sudo pacman -S --needed -

# Install all manually installed AUR packages
grep -v '^#' "$DIR_LATEST/03-explicit-aur.txt" | paru -S --needed -

# Check modified pacman config files
cat "$DIR_LATEST/04-modified-pacman-configs.txt"

# List enabled systemd boot services
cat "$DIR_LATEST/05-enabled-systemd-units.txt"
================================================================================
EOF
}

# Handle log subcommand first
if [[ $# -ge 1 && "$1" == "log" ]]; then
    mkdir -p "$BASE_STATE"
    less "$SNAP_LOG"
    exit 0
fi

# Parse flags
while getopts ":c:hH" opt; do
    case "$opt" in
    c)
        COMMENT="$OPTARG"
        ;;
    h)
        short_usage
        exit 0
        ;;
    H)
        full_help
        exit 0
        ;;
    \?)
        echo "Error: invalid option -$OPTARG" >&2
        short_usage >&2
        exit 1
        ;;
    :)
        echo "Error: option -$OPTARG requires argument" >&2
        short_usage >&2
        exit 1
        ;;
    esac
done
shift $((OPTIND - 1))

# Create all required directories before writing files
mkdir -p "$BASE_STATE" "$DIR_LATEST" "$DIR_HISTORY" "$CURR_HIST_DIR"

echo "========================================"
echo "Generating package snapshot archive: $CURR_HIST_DIR"
echo "Shortcut access directory: $DIR_LATEST"
[[ -n "$COMMENT" ]] && echo "Snapshot comment: $COMMENT"
echo "========================================"

# Export package & system info files
pacman -Qqe >"${CURR_HIST_DIR}/01-explicit-official.txt"
pacman -Q >"${CURR_HIST_DIR}/02-all-packages.txt"

if command -v paru &>/dev/null; then
    paru -Qqe >"${CURR_HIST_DIR}/03-explicit-aur.txt"
elif command -v yay &>/dev/null; then
    yay -Qqe >"${CURR_HIST_DIR}/03-explicit-aur.txt"
else
    echo "# No AUR helper found on system" >"${CURR_HIST_DIR}/03-explicit-aur.txt"
fi

pacman -Qii | awk '/\[modified\]/ {print $(NF - 1)}' >"${CURR_HIST_DIR}/04-modified-pacman-configs.txt"
systemctl list-unit-files --state=enabled >"${CURR_HIST_DIR}/05-enabled-systemd-units.txt"

# Rebuild snap-latest symlink directory
rm -rf "${DIR_LATEST:?}"/*
for file in "$CURR_HIST_DIR"/*; do
    ln -sf "$file" "$DIR_LATEST/"
done

# Write snapshot entry to log file
echo "${TIMESTAMP} | ${CURR_HIST_DIR} | ${COMMENT}" >>"$SNAP_LOG"

# Auto purge outdated snapshots
HIST_COUNT=$(ls -1d "${DIR_HISTORY}"/* 2>/dev/null | wc -l)
if [[ $HIST_COUNT -gt $MAX_KEEP ]]; then
    DELETE_COUNT=$((HIST_COUNT - MAX_KEEP))
    echo "Total history snapshots exceed limit ${MAX_KEEP}, removing oldest ${DELETE_COUNT} archives"
    ls -1d "${DIR_HISTORY}"/* | sort | head -n "$DELETE_COUNT" | xargs rm -rf
fi

echo -e "\nSnapshot task finished"
echo "Quick reference:"
echo "  View log: $(basename "$0") log"
echo "  Short help: $(basename "$0") -h"
echo "  Full manual: $(basename "$0") -H"
echo "========================================"
