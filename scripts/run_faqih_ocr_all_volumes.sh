#!/usr/bin/env bash
# Run Apple Vision OCR on all 4 Man La Yahduruhu Al-Faqih volumes.
# Each volume takes several minutes; 2-minute sleep between volumes.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON="${REPO}/venv/bin/python"
OCR="${SCRIPT_DIR}/ocr_faqih_arabic.py"
PDFS="${REPO}/datasets/man-la-yahduruhu-al-faqih/pdfs"
CSVS="${REPO}/datasets/man-la-yahduruhu-al-faqih"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ---------------------------------------------------------------------------
# Volume 1  hadiths 1 – 1573
# ---------------------------------------------------------------------------
log "=== VOL 1 (1-1573) ==="
"${PYTHON}" "${OCR}" \
    --pdf  "${PDFS}/man-la-yahduruhu-al-faqih-vol.1.pdf" \
    --csv  "${CSVS}/man-la-yahduruhu-al-faqih-vol.1_hadiths.csv" \
    --hadith-start 1 \
    --hadith-end   1573

log "Vol 1 done. Sleeping 2 minutes before vol 2…"
sleep 120

# ---------------------------------------------------------------------------
# Volume 2  hadiths 1574 – 3215
# ---------------------------------------------------------------------------
log "=== VOL 2 (1574-3215) ==="
"${PYTHON}" "${OCR}" \
    --pdf  "${PDFS}/man-la-yahduruhu-al-faqih-vol.2.pdf" \
    --csv  "${CSVS}/man-la-yahduruhu-al-faqih-vol.2_hadiths.csv" \
    --hadith-start 1574 \
    --hadith-end   3215

log "Vol 2 done. Sleeping 2 minutes before vol 3-1…"
sleep 120

# ---------------------------------------------------------------------------
# Volume 3-1  hadiths 3216 – 4967
# ---------------------------------------------------------------------------
log "=== VOL 3-1 (3216-4967) ==="
"${PYTHON}" "${OCR}" \
    --pdf  "${PDFS}/man-la-yahduruhu-al-faqih-vol.3-1.pdf" \
    --csv  "${CSVS}/man-la-yahduruhu-al-faqih-vol.3-1_hadiths.csv" \
    --hadith-start 3216 \
    --hadith-end   4967

log "Vol 3-1 done. Sleeping 2 minutes before vol 4…"
sleep 120

# ---------------------------------------------------------------------------
# Volume 4  hadiths 4968 – 5920
# ---------------------------------------------------------------------------
log "=== VOL 4 (4968-5920) ==="
"${PYTHON}" "${OCR}" \
    --pdf  "${PDFS}/man-la-yahduruhu-al-faqih-vol.4.pdf" \
    --csv  "${CSVS}/man-la-yahduruhu-al-faqih-vol.4_hadiths.csv" \
    --hadith-start 4968 \
    --hadith-end   5920

log "=== ALL VOLUMES COMPLETE ==="
