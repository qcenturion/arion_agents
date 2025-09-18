import os
import sys


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "api":
        try:
            import uvicorn  # type: ignore
        except ImportError as exc:
            raise SystemExit("uvicorn not installed. Run: make install") from exc
        reload_flag = os.getenv("UVICORN_RELOAD", "false").lower() in {"1", "true", "yes"}
        log_level = os.getenv("UVICORN_LOG_LEVEL", "info")
        access_log = os.getenv("UVICORN_ACCESS_LOG", "true").lower() in {"1", "true", "yes"}
        uvicorn.run(
            "arion_agents.api:app",
            host="0.0.0.0",
            port=8000,
            reload=reload_flag,
            log_level=log_level,
            access_log=access_log,
        )
    else:
        print("Usage: python -m arion_agents api")


if __name__ == "__main__":
    main()
