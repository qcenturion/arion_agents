import os
import sys
from . import hello


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "api":
        try:
            import uvicorn  # type: ignore
        except ImportError as e:
            raise SystemExit("uvicorn not installed. Run: make install") from e
        reload_flag = os.getenv("UVICORN_RELOAD", "false").lower() in {"1", "true", "yes"}
        uvicorn.run(
            "arion_agents.api:app",
            host="0.0.0.0",
            port=8000,
            reload=reload_flag,
        )
    else:
        print(hello())


if __name__ == "__main__":
    main()
