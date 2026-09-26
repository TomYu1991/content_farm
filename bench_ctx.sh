#!/usr/bin/env bash
# Temp benchmark run INSIDE WSL: prefill speed of qwen3:8b vs num_thread.
API=http://127.0.0.1:11434/api/generate

UNIT=$(printf '\u5411\u91cf\u68c0\u7d22\u628a\u6587\u672c\u8f6c\u6362\u6210\u5411\u91cf\u540e\u6309\u76f8\u4f3c\u5ea6\u67e5\u627e\u3002')
LONG=""
for i in $(seq 1 120); do LONG="${LONG}${UNIT}"; done
PROMPT="${LONG} Summarize the above in one sentence."

# warm up the model so cold-load time is excluded
curl -s -m 900 -o /dev/null "$API" -H 'Content-Type: application/json' \
  --data-raw "{\"model\":\"qwen3:8b\",\"prompt\":\"hi\",\"stream\":false,\"think\":false,\"options\":{\"num_predict\":1}}"

run () {
  local nt="$1" opts
  if [ "$nt" = "0" ]; then opts='{"num_predict":16}'; else opts="{\"num_predict\":16,\"num_thread\":$nt}"; fi
  curl -s -m 1800 -o /tmp/bench.json "$API" -H 'Content-Type: application/json' \
    --data-raw "{\"model\":\"qwen3:8b\",\"prompt\":\"$PROMPT\",\"stream\":false,\"think\":false,\"options\":$opts}"
  python3 - "$nt" <<'PY'
import json, sys
nt = sys.argv[1]
d = json.load(open('/tmp/bench.json'))
pc, pd = d.get('prompt_eval_count', 0), d.get('prompt_eval_duration', 1)
ec, ed = d.get('eval_count', 0), d.get('eval_duration', 1)
label = 'default' if nt == '0' else f'num_thread={nt}'
print(f"{label:<16} in={pc}tok  prefill={pc/(pd/1e9):.1f}tok/s  wait={pd/1e9:.1f}s  gen={ec/(ed/1e9):.2f}tok/s")
PY
}

for nt in 0 6 10; do run "$nt"; done
