#!/usr/bin/env bash
#
# Usage: bash run.sh <mode> <formula>
#   mode: DIRECT or TOKENIZED
#   formula: LaTeX formula (backslashes will be auto-escaped for JSON)
#
# Example:
#   bash run.sh DIRECT '(K\odot X) = ((K_0 \cdot X_a))'
#
# Outputs are saved in requests/outputs/, keeping only the last 5.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/outputs"

MODE="${1:?Usage: bash run.sh <DIRECT|TOKENIZED> <formula>}"
FORMULA="${2:?Usage: bash run.sh <DIRECT|TOKENIZED> <formula>}"

# Auto-escape backslashes for JSON
FORMULA_ESCAPED=$(echo "$FORMULA" | sed 's/\\/\\\\/g')

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="$OUTPUT_DIR/${TIMESTAMP}_${MODE}.txt"

JSON_BODY="{\"mode\": \"$MODE\", \"search_formula\": \"$FORMULA_ESCAPED\"}"

CURL_CMD="curl -X POST http://localhost:3000/search-formula \\
  -H \"Content-Type: application/json\" \\
  -d '$JSON_BODY'"

# Run request
RESPONSE=$(curl -s -X POST http://localhost:3000/search-formula \
  -H "Content-Type: application/json" \
  -d "$JSON_BODY")

# Format output
{
  echo "$CURL_CMD"
  echo ""
  echo ""
  echo "$RESPONSE" | python3 -m json.tool
} | tee "$OUTPUT_FILE"

echo ""
echo "Saved to: $OUTPUT_FILE"

# Keep only the last 5 outputs
cd "$OUTPUT_DIR"
ls -t *.txt 2>/dev/null | tail -n +6 | xargs -r rm --
