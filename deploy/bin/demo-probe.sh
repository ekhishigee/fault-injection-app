#!/bin/bash
# Optional custom metrics via AWS CLI. Missing credentials must not fail the unit.
set -euo pipefail

TARGET_URL="${DEMO_PROBE_URL:-http://127.0.0.1/}"
NAMESPACE="${DEMO_METRIC_NAMESPACE:-DemoApp}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"

health_url="${TARGET_URL%/}/health"
api_url="${TARGET_URL%/}/api/demo"

health_code="0"
health_ok=0
if health_out="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 "$health_url" 2>/dev/null || true)"; then
  health_code="${health_out:-0}"
fi
if [[ "$health_code" == "200" ]]; then
  health_ok=1
fi

api_code="0"
latency_ms=0
if api_out="$(curl -sS -o /dev/null -w "%{http_code} %{time_total}" --max-time 8 "$api_url" 2>/dev/null || true)"; then
  api_code="$(echo "$api_out" | awk '{print $1}')"
  latency_s="$(echo "$api_out" | awk '{print $2}')"
  latency_ms="$(python3 -c "print(int(round(float('${latency_s:-0}') * 1000)))" 2>/dev/null || echo 0)"
fi

http_5xx=0
if [[ "$api_code" == "500" || "$api_code" == "502" || "$api_code" == "503" || "$api_code" == "504" ]]; then
  http_5xx=1
fi

aws_args=(cloudwatch put-metric-data --namespace "$NAMESPACE" --metric-data
  "MetricName=HealthCheck,Value=${health_ok},Unit=None"
  "MetricName=Http5xx,Value=${http_5xx},Unit=None"
  "MetricName=LatencyMs,Value=${latency_ms},Unit=Milliseconds"
)
if [[ -n "$REGION" ]]; then
  aws_args+=(--region "$REGION")
fi

if command -v aws >/dev/null 2>&1; then
  aws "${aws_args[@]}" >/dev/null || echo "aws put-metric-data skipped (no credentials or IAM?)" >&2
fi

echo "health=${health_code} health_ok=${health_ok} api=${api_code} latency_ms=${latency_ms} http_5xx=${http_5xx}"
