#!/usr/bin/env python3
import logging

import uvicorn

from src.settings import settings


def main() -> None:
    # Importing settings above already fails fast (pydantic ValidationError) when a
    # required variable such as AUTH_PASSWORD or MQTT_HOST is missing.
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run("src.api:app", host="0.0.0.0", port=settings.port, reload=False)


if __name__ == "__main__":
    main()
