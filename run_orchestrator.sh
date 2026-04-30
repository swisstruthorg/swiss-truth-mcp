#!/bin/bash
# Konservativer Modus: 1 Domain pro Stunde, kleine Batches, lange Pausen
# Verhindert Rate-Limit-Probleme bei open-claude.com
export SWISS_TRUTH_API_KEY=xLUQPyk2Lubht
export SWISS_TRUTH_API_BASE=https://swisstruth.org
export SWISS_TRUTH_TARGET=200
export SWISS_TRUTH_BATCH=5
export SWISS_TRUTH_MAX_ROUNDS=3
export SWISS_TRUTH_SLEEP=120
export SWISS_TRUTH_MAX_RUNTIME=3300
export SWISS_TRUTH_MAX_STALE=2
export SWISS_TRUTH_RETRY_COUNT=3
export SWISS_TRUTH_RETRY_DELAY=15

LOG=/opt/swiss-truth/logs/orchestrator.log
mkdir -p /opt/swiss-truth/logs

# Rotate log if > 10MB
if [ -f "$LOG" ] && [ $(stat -c%s "$LOG") -gt 10485760 ]; then
    mv "$LOG" "${LOG}.old"
fi

echo "" >> "$LOG"
echo "========================================" >> "$LOG"
echo "[START] $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "========================================" >> "$LOG"

python3 /opt/swiss-truth/manage_claims.py 2>&1 | tee -a "$LOG"

echo "[END] $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
