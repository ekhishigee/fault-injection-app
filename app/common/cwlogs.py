"""CloudWatch Logs sink. Imported only when DEMO_CLOUDWATCH_LOGS is on."""

from __future__ import annotations

import os
import socket
from typing import Any


def credentials_available() -> bool:
    if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        return True
    if os.environ.get("AWS_PROFILE"):
        return True
    try:
        import boto3

        creds = boto3.Session().get_credentials()
        return creds is not None
    except Exception:
        return False


def credential_status() -> dict[str, Any]:
    if credentials_available():
        return {"ok": True, "credentials": True, "error": ""}
    return {
        "ok": False,
        "credentials": False,
        "error": (
            "CloudWatch credentials are missing. Set AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY in env, or AWS_PROFILE / an instance role."
        ),
    }


def probe_access(sink: CloudWatchSink | None = None) -> dict[str, Any]:
    status = credential_status()
    if not status["ok"]:
        return status
    try:
        sink = sink or CloudWatchSink()
        sink._ensure_stream(sink._get_client())
        return {
            "ok": True,
            "credentials": True,
            "error": "",
            "group": sink.group,
            "stream": sink.stream,
            "region": sink.region,
        }
    except Exception as exc:
        return {
            "ok": False,
            "credentials": True,
            "error": humanize_aws_error(exc),
        }


def humanize_aws_error(exc: Exception) -> str:
    name = type(exc).__name__
    message = str(exc)
    lowered = f"{name} {message}".lower()
    if "nocredentials" in lowered or "unable to locate credentials" in lowered:
        return (
            "CloudWatch credentials are missing. Set AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY in env, or AWS_PROFILE / an instance role."
        )
    if "expiredtoken" in lowered or "token has expired" in lowered:
        return "CloudWatch credentials expired. Refresh the keys or instance role."
    if "accessdenied" in lowered or "unauthorized" in lowered or "not authorized" in lowered:
        return (
            "No CloudWatch Logs access. The credentials need logs:CreateLogGroup, "
            "logs:CreateLogStream, and logs:PutLogEvents."
        )
    return f"CloudWatch access failed: {message.splitlines()[0][:240]}"


class CloudWatchSink:
    def __init__(
        self,
        group: str | None = None,
        stream: str | None = None,
        region: str | None = None,
        client: Any = None,
    ) -> None:
        self.group = group or os.environ.get("DEMO_CW_LOG_GROUP", "/fault-inject/app")
        self.stream = stream or os.environ.get("DEMO_CW_LOG_STREAM") or socket.gethostname()
        self.region = (
            region
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        self._client = client
        self._token: str | None = None
        self._ready = False

    def __call__(self, entry: dict[str, Any]) -> None:
        self.put(entry)

    def put(self, entry: dict[str, Any]) -> None:
        client = self._get_client()
        self._ensure_stream(client)
        event = {
            "timestamp": int(float(entry.get("ts", 0)) * 1000),
            "message": str(entry.get("line") or entry.get("msg") or ""),
        }
        kwargs: dict[str, Any] = {
            "logGroupName": self.group,
            "logStreamName": self.stream,
            "logEvents": [event],
        }
        if self._token:
            kwargs["sequenceToken"] = self._token
        try:
            response = client.put_log_events(**kwargs)
        except Exception as exc:
            token = _sequence_token_from_error(exc)
            if token:
                self._token = token
                response = client.put_log_events(
                    logGroupName=self.group,
                    logStreamName=self.stream,
                    logEvents=[event],
                    sequenceToken=token,
                )
            else:
                raise
        self._token = response.get("nextSequenceToken") or self._token

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("logs", region_name=self.region)
        return self._client

    def _ensure_stream(self, client: Any) -> None:
        if self._ready:
            return
        _ignore_exists(lambda: client.create_log_group(logGroupName=self.group))
        _ignore_exists(
            lambda: client.create_log_stream(
                logGroupName=self.group, logStreamName=self.stream
            )
        )
        self._ready = True


def _ignore_exists(action: Any) -> None:
    try:
        action()
    except Exception as exc:
        name = type(exc).__name__
        message = str(exc)
        if "ResourceAlreadyExistsException" in name or "ResourceAlreadyExists" in message:
            return
        raise


def _sequence_token_from_error(exc: Exception) -> str | None:
    expected = getattr(exc, "response", {}).get("expectedSequenceToken")
    if expected:
        return str(expected)
    message = str(exc)
    marker = "The next expected sequenceToken is: "
    if marker in message:
        return message.split(marker, 1)[1].strip().split()[0]
    return None
