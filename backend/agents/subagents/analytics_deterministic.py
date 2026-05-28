import json
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.events.event_actions import EventActions

from agents.tools.sentinelhub_stats import ndvi_stats_range


class AnalyticsDeterministicAgent(BaseAgent):
    name: str = "AnalyticsDeterministicAgent"
    description: str = "Deterministically computes metrics (mock), no LLM."

    async def _run_async_impl(self, context: InvocationContext) -> AsyncGenerator[Event, None]:
        state = context.session.state
        analysis_spec_raw = state.get("analysis_spec")
        # geodata_result is used for metadata/notes in real flow
        state.get("geodata_result")

        if not analysis_spec_raw:
            err = json.dumps({"error": "Missing analysis_spec in state."})
            yield Event(author=self.name, actions=EventActions(state_delta={"metrics_result": err}))
            return

        # Parse analysis_spec
        if isinstance(analysis_spec_raw, str):
            spec = json.loads(analysis_spec_raw)
        else:
            spec = analysis_spec_raw

        aoi = spec["aoi_geojson"]
        d_start = spec["date_start"]
        d_end = spec["date_end"]

        try:
            # REAL calculation instead of mock_compute_timeseries
            stats = ndvi_stats_range(aoi, d_start, d_end)

            # Extract relevant stats for the report agent
            # Note: Statistics API response is nested
            stats.get("data", [])

            # Simple aggregation for the narrative agent
            metrics = {
                "source": "Sentinel Hub Statistics API",
                "stats": stats,
                "interpretation": "Real-time NDVI statistics computed over the selected AOI and time range."
            }

            metrics_result_json = json.dumps(metrics)
        except Exception as e:
            err = json.dumps({"error": f"NDVI stats calculation failed: {str(e)}"})
            yield Event(author=self.name, actions=EventActions(state_delta={"metrics_result": err}))
            return

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={"metrics_result": metrics_result_json}),
        )


analytics_agent = AnalyticsDeterministicAgent()
