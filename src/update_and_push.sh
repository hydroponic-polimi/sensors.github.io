#!/usr/bin/env bash
set -e

# ABSOLUTE PATH TO YOUR REPO
REPO_DIR="/home/hydroponic-polimi/sensors.github.io"

# CONDA
PYTHON_PATH="/home/hydroponic-polimi/miniconda3/bin/python"

cd "$REPO_DIR"

echo "[`date`] Running export script..."
$PYTHON_PATH src/export_influx_to_csv.py

echo "[`date`] Git add/commit/push..."
git add data/*.csv

# If there are no changes, commit will fail; ignore that case
git commit -m "Update CSV data `date -Iseconds`" || echo "No changes to commit."

git push

echo "[`date`] Done."

