#!/bin/sh
set -e

DATA_DIR="${DATA_DIR:-/data}"

# Kalau start sebagai root: pastikan folder data ada & bisa ditulis appuser,
# lalu jalankan perintah utama sebagai appuser.
if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DATA_DIR"
    chown -R appuser "$DATA_DIR" 2>/dev/null || true
    exec gosu appuser "$@"
fi

exec "$@"
