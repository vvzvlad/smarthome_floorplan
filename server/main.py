#!/usr/bin/env python3
import os
import sys
import uvicorn


def main():
    if not os.getenv("AUTH_PASSWORD"):
        print("ERROR: AUTH_PASSWORD environment variable is required", file=sys.stderr)
        sys.exit(1)

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("src.api:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
