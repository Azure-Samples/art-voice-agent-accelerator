from statistics import mean
from typing import Dict, List


class LatencyTracker:
    """
    Tracks latency for different stages in the session.
    """

    def __init__(self) -> None:
        self._bucket: Dict[str, List[Dict[str, float]]] = {}

    def note(self, stage: str, start_t: float, end_t: float) -> None:
        self._bucket.setdefault(stage, []).append(
            {"start": start_t, "end": end_t, "dur": end_t - start_t}
        )

    def summary(self) -> Dict[str, Dict[str, float]]:
        """
        Calculate a summary of all latencies collected so far.

        Returns a dictionary with stage names as keys and a sub-dictionary
        with the following keys:

        - "count": The number of samples collected for this stage.
        - "avg": The average duration in seconds.
        - "min": The shortest duration in seconds.
        - "max": The longest duration in seconds.

        If no samples have been collected for a stage, all values are 0.0.
        """
        out: Dict[str, Dict[str, float]] = {}
        for stage, samples in self._bucket.items():
            durations = [s["dur"] for s in samples]
            out[stage] = {
                "count": len(durations),
                "avg": mean(durations) if durations else 0.0,
                "min": min(durations) if durations else 0.0,
                "max": max(durations) if durations else 0.0,
            }
        return out
