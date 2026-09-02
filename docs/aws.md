# Optional AWS extras

EC2 install and `/etc/demo-target/env`: [ec2.md](ec2.md).

The app works without AWS. These files are only if you want host metrics or example alarms on EC2.

## CloudWatch Agent

Instance role needs `CloudWatchAgentServerPolicy` and `cloudwatch:PutMetricData` if you also run the probe timer.

```bash
sudo ./deploy/cloudwatch/install-agent.sh
```

Config: `deploy/cloudwatch/amazon-cloudwatch-agent.json`

- `mem_used_percent`
- `disk_used_percent` on `/mnt/demo-disk` only
- `procstat` for `demo-target` and nginx

`AWS/EC2` `CPUUtilization` does not need the agent. Application metrics (`HealthCheck`, `Http5xx`, `LatencyMs`) come from `demo-probe.timer` via the AWS CLI (namespace `DemoApp` by default). The probe is a no-op if credentials are missing.

## Example alarms

After a quiet boot, measure idle memory, then:

```bash
grep -E 'MemTotal|MemAvailable' /proc/meminfo
aws cloudformation deploy \
  --template-file deploy/cloudwatch/alarms.cfn.yaml \
  --stack-name fault-inject-alarms \
  --parameter-overrides InstanceId=i-xxxxxxxx MemoryUsedPercentThreshold=70
```

Set the memory threshold to **idle used percent + about 8**, not 80–90.

## Application logs

The app writes JSONL to **`/var/lib/demo-faults/app.log`**. It does not call CloudWatch.

Ship that file with the CloudWatch Agent. The example config already includes:

```text
file_path: /var/lib/demo-faults/app.log
log_group_name: /fault-inject/app
```

`DEMO_APP_LOGS=1` only shows the same lines on the dashboard.

## Example SSM documents

`deploy/ssm/` contains optional Automation documents that start nginx, start the target, or stop resource faults. Tag the instance `App=demo-target` if you use the shipped target filters.
