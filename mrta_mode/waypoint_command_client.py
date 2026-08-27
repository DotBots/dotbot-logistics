"""Write-path REST client: PUT /controller/dotbots/{address}/0/waypoints.

Arrival is not this class's concern -- see LivePositionStore. The WS status
channel is a broadcast-only, read side: commanding a bot to move still
requires this PUT regardless of how arrival is detected.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


class WaypointCommandClient:
    def __init__(self, base_url: str, threshold: int):
        self.base_url = base_url
        self.threshold = threshold

    def send(self, address: str, waypoints_mm: list[tuple[float, float]]) -> None:
        payload = {
            "threshold": self.threshold,
            "waypoints": [{"x": float(x), "y": float(y)} for x, y in waypoints_mm],
        }
        r = requests.put(
            f"{self.base_url}/controller/dotbots/{address}/0/waypoints",
            json=payload,
            timeout=5,
        )
        r.raise_for_status()

    def send_all_parallel(self, moved_mm: dict[str, tuple[float, float]]) -> None:
        if not moved_mm:
            return
        with ThreadPoolExecutor(max_workers=len(moved_mm)) as executor:
            futures = {
                executor.submit(self.send, addr, [wp_mm]): addr
                for addr, wp_mm in moved_mm.items()
            }
            for future in as_completed(futures):
                addr = futures[future]
                try:
                    future.result()
                except requests.RequestException as e:
                    print(f"    -> Send error {addr[:8]}...: {e}")
