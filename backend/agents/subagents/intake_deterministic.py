from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.events.event_actions import EventActions


def _get_user_text(ctx: InvocationContext) -> str:
    uc = getattr(ctx, "user_content", None)
    if uc and getattr(uc, "parts", None) and len(uc.parts) > 0:
        first = uc.parts[0]
        txt = getattr(first, "text", None)
        if isinstance(txt, str):
            return txt.strip()
    return ""


class IntakeDeterministicAgent(BaseAgent):
    name: str = "IntakeDeterministicAgent"
    description: str = "Deterministically builds analysis_spec JSON without calling an LLM."

    async def _run_async_impl(self, context: InvocationContext) -> AsyncGenerator[Event, None]:
        _get_user_text(context)

        # Default AOI and values (formerly in eo_mock)
        default_aoi = {
            "type": "Polygon",
            "coordinates": [[[88.20, 22.85], [88.45, 22.85], [88.45, 23.05], [88.20, 23.05], [88.20, 22.85]]],
        }

        # For MVP, we use these defaults if user input is empty or generic
        analysis_spec = {
            "objective": "claim",
            "hazard_type": "drought_stress",
            "aoi_geojson": default_aoi,
            "date_start": "2023-07-01",
            "date_end": "2023-09-01",
            "crop_type": "paddy",
            "region_label": "Hooghly (sample AOI)",
            "requested_outputs": ["ndvi_timeseries", "ndwi_timeseries", "anomaly_score", "evidence_pack"],
            "needs_clarification": False,
            "questions": [],
        }

        import json
        yield Event(
            author=self.name,
            actions=EventActions(state_delta={"analysis_spec": json.dumps(analysis_spec)}),
        )


intake_agent = IntakeDeterministicAgent()
