import logging
import httpx
from typing import Optional
from .config import settings

logger = logging.getLogger("aiops.loki")


class LokiClient:
    def __init__(self, base_url: str = settings.LOKI_URL):
        self.base_url = base_url.rstrip("/")

    async def query_logs(self, namespace: str, pod_name: str, limit: int = 100) -> Optional[str]:
        """Queries Grafana Loki REST API for recent container logs."""
        query = f'{{namespace="{namespace}", pod=~"{pod_name}.*"}}'
        url = f"{self.base_url}/loki/api/v1/query_range"
        params = {"query": query, "limit": limit}

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(url, params=params)
                if res.status_code == 200:
                    data = res.json()
                    streams = data.get("data", {}).get("result", [])
                    log_lines = []
                    for stream in streams:
                        for entry in stream.get("values", []):
                            # entry is [timestamp_str, log_message_str]
                            log_lines.append(entry[1])
                    if log_lines:
                        logger.info(f"Retrieved {len(log_lines)} log entries from Loki for {pod_name}")
                        return "\n".join(log_lines[-limit:])
        except Exception as exc:
            logger.debug(f"Loki query skipped/failed ({exc}). Will fall back directly to Kubernetes API.")
        return None
