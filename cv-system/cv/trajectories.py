"""Center-point history for persistent track IDs."""

from collections import deque

import cv2


class TrajectoryStore:
    """Keep the most recent center points for each track."""

    def __init__(self, max_length: int = 20):
        self.max_length = max_length
        self._points: dict[int, deque[tuple[int, int]]] = {}

    def update(self, track_id: int, center: tuple[int, int]) -> None:
        trail = self._points.get(track_id)
        if trail is None:
            trail = deque(maxlen=self.max_length)
            self._points[track_id] = trail
        trail.append(center)

    def points(self, track_id: int) -> list[tuple[int, int]]:
        trail = self._points.get(track_id)
        if trail is None:
            return []
        return list(trail)


def draw_trail(frame, points: list[tuple[int, int]], color: tuple[int, int, int]) -> None:
    """Draw a short trail. Newer segments are brighter and thicker."""
    count = len(points)
    if count < 2:
        return

    for index in range(1, count):
        strength = index / (count - 1)
        faded = tuple(int(channel * (0.25 + 0.75 * strength)) for channel in color)
        thickness = 2 if strength >= 0.5 else 1
        cv2.line(frame, points[index - 1], points[index], faded, thickness, cv2.LINE_AA)
