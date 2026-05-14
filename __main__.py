import asyncio
import sys

from bootstrap.settings import Settings
from app import Application


def main() -> None:
    settings = Settings()
    app = Application(settings)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
