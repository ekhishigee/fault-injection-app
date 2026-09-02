"""Kept for old systemd units. Faults no longer auto-expire."""


def main() -> int:
    print("expired:none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
