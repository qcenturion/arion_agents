from __future__ import annotations

from typing import Any, Dict, Optional, Type

from .base import BaseTool, ToolConfig, ToolRunInput, ToolRunOutput


class EchoTool(BaseTool):
    """A built-in tool that echoes inputs. provider_type: 'builtin:echo'"""

    def run(self, payload: ToolRunInput) -> ToolRunOutput:
        return ToolRunOutput(ok=True, result={
            "echo": payload.params,
            "system": payload.system,
            "metadata": payload.metadata,
        })


class WorldTimeApiTool(BaseTool):
    """Fetch current UTC time from worldtimeapi and compute TAI.

    provider_type: 'http:worldtimeapi'
    agent params: timezone (optional, default 'Etc/UTC')
    """

    def run(self, payload: ToolRunInput) -> ToolRunOutput:
        import requests
        import datetime as dt

        tz = str(payload.params.get("timezone") or "Etc/UTC")
        url = f"https://worldtimeapi.org/api/timezone/{tz}"
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            utc_iso = data.get("datetime")
            if not utc_iso:
                return ToolRunOutput(ok=False, error="missing datetime in response")
            TAI_OFFSET_SECONDS = 37
            utc = dt.datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
            tai = utc + dt.timedelta(seconds=TAI_OFFSET_SECONDS)
            return ToolRunOutput(ok=True, result={
                "timezone": tz,
                "utc": utc.isoformat(),
                "tai": tai.isoformat(),
                "source": "worldtimeapi.org",
            })
        except Exception as e:
            return ToolRunOutput(ok=False, error=str(e))


class SunApiTool(BaseTool):
    """Fetch sunrise and sunset times from sunrise-sunset.org.

    provider_type: 'http:sunapi'
    agent params: lat, lng (optional, default to Malaga, Spain)
    """

    def run(self, payload: ToolRunInput) -> ToolRunOutput:
        import requests

        lat = payload.params.get("lat") or "36.7201600"
        lng = payload.params.get("lng") or "-4.4203400"
        url = f"https://api.sunrise-sunset.org/json?lat={lat}&lng={lng}"
        print(f"SunApiTool requesting URL: {url}", flush=True)
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            print(f"SunApiTool response: {data}", flush=True)
            return ToolRunOutput(ok=True, result=data.get("results"))
        except Exception as e:
            print(f"SunApiTool failed: {e}", flush=True)
            return ToolRunOutput(ok=False, error=str(e))


PROVIDERS: Dict[str, Type[BaseTool]] = {
    "builtin:echo": EchoTool,
    "http:worldtimeapi": WorldTimeApiTool,
    "http:sunapi": SunApiTool,
}


def instantiate_tool(cfg: ToolConfig, secret_value: Optional[str]) -> BaseTool:
    cls = PROVIDERS.get(cfg.provider_type)
    if not cls:
        raise ValueError(f"No provider for type '{cfg.provider_type}'")
    return cls(cfg, secret_value)
