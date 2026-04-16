#!/usr/bin/env python3
import os
import uvicorn


def main():
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("src.api:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
