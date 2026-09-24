"""Start the FastAPI service with the configured number of Uvicorn workers."""

import os

import uvicorn


def main() -> None:
    """Run the ASGI app; set WEB_CONCURRENCY for the container's CPU allocation."""
    workers = int(os.getenv("WEB_CONCURRENCY", "1"))
    if workers < 1:
        raise ValueError("WEB_CONCURRENCY must be at least 1")

    uvicorn.run(
        "src.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        workers=workers,
        access_log=False,
    )


if __name__ == "__main__":
    main()
