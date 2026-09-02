#!/bin/bash
# Install and start a minimal CloudWatch Agent config on Amazon Linux 2023.
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "run as root" >&2
  exit 1
fi

CONFIG="${1:-/opt/demo-target/deploy/cloudwatch/amazon-cloudwatch-agent.json}"

dnf install -y amazon-cloudwatch-agent
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -s \
  -c "file:${CONFIG}"

systemctl enable amazon-cloudwatch-agent
echo "CloudWatch Agent running with ${CONFIG}"
