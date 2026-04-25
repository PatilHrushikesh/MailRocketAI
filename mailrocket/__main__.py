"""Allow `python -m mailrocket ...`."""
from mailrocket.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
