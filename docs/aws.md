# Optional AWS extras

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

Set `DEMO_CLOUDWATCH_LOGS=1` plus credentials (keys, profile, or instance role). The controller writes realistic app lines to `/fault-inject/app` (override with `DEMO_CW_LOG_GROUP` / `DEMO_CW_LOG_STREAM`). The dashboard panel is a separate flag: `DEMO_APP_LOGS=1`.

If the CloudWatch flag is on but credentials or boto3 fail, local/dashboard logs still work.

On systemd, add the flags to `/etc/demo-target/env` and restart `demo-controller`.

## Example SSM documents

`deploy/ssm/` contains optional Automation documents that start nginx, start the target, or stop resource faults. Tag the instance `App=demo-target` if you use the shipped target filters.
