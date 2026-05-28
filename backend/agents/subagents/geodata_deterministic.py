import asyncio
import base64
import json
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.events.event_actions import EventActions

from agents.tools.sentinel_hub import scene_search_s2_l2a
from agents.tools.sentinelhub_process import process_png_ndvi, process_png_truecolor


class GeoDataDeterministicAgent(BaseAgent):
    name: str = "GeoDataDeterministicAgent"
    description: str = "Fetches Sentinel-2 evidence PNGs via Sentinel Hub (no LLM)."

    async def _run_async_impl(self, context: InvocationContext) -> AsyncGenerator[Event, None]:
        state = context.session.state
        analysis_spec_raw = state.get("analysis_spec")

        if not analysis_spec_raw:
            err = json.dumps({"error": "Missing analysis_spec in state. Intake step failed."})
            yield Event(author=self.name, actions=EventActions(state_delta={"geodata_result": err}))
            return

        # Normalize analysis_spec to JSON string + dict
        if isinstance(analysis_spec_raw, dict):
            analysis_spec_json = json.dumps(analysis_spec_raw)
            spec = analysis_spec_raw
        elif isinstance(analysis_spec_raw, str):
            analysis_spec_json = analysis_spec_raw
            try:
                spec = json.loads(analysis_spec_raw)
            except json.JSONDecodeError as e:
                err = json.dumps({"error": f"analysis_spec is not valid JSON: {str(e)}"})
                yield Event(author=self.name, actions=EventActions(state_delta={"geodata_result": err}))
                return
        else:
            err = json.dumps({"error": f"analysis_spec must be str or dict, got: {type(analysis_spec_raw).__name__}"})
            yield Event(author=self.name, actions=EventActions(state_delta={"geodata_result": err}))
            return

        # AOI can be dict or JSON string
        aoi_geojson = spec.get("aoi_geojson")
        if isinstance(aoi_geojson, str):
            try:
                aoi_geojson = json.loads(aoi_geojson)
            except json.JSONDecodeError as e:
                err = json.dumps({"error": f"aoi_geojson is not valid JSON: {str(e)}"})
                yield Event(author=self.name, actions=EventActions(state_delta={"geodata_result": err}))
                return
        elif not isinstance(aoi_geojson, dict):
            err = json.dumps({"error": f"aoi_geojson must be dict or JSON string, got: {type(aoi_geojson).__name__}"})
            yield Event(author=self.name, actions=EventActions(state_delta={"geodata_result": err}))
            return

        try:
            date_start = spec["date_start"]
            date_end = spec["date_end"]
        except KeyError as e:
            err = json.dumps({"error": f"Missing required key in analysis_spec: {str(e)}"})
            yield Event(author=self.name, actions=EventActions(state_delta={"geodata_result": err}))
            return

        # REAL Sentinel Hub scene selection (Catalog API)
        try:
            geodata_result_json = scene_search_s2_l2a(
                aoi_geojson=aoi_geojson,
                date_start=date_start,
                date_end=date_end,
                max_cloud_pct=15.0,
                limit=12,
                min_scenes=12,
                search_padding_days=15,
            )
        except Exception as e:
            err = json.dumps({"error": f"scene_search_s2_l2a failed: {str(e)}"})
            yield Event(author=self.name, actions=EventActions(state_delta={"geodata_result": err}))
            return

        # Evidence PNGs (still OK to keep as deterministic "before/after" visuals)
        tc_before = await asyncio.to_thread(process_png_truecolor, aoi_geojson, date_start, date_start)
        tc_after = await asyncio.to_thread(process_png_truecolor, aoi_geojson, date_end, date_end)
        ndvi_before = await asyncio.to_thread(process_png_ndvi, aoi_geojson, date_start, date_start)
        ndvi_after = await asyncio.to_thread(process_png_ndvi, aoi_geojson, date_end, date_end)

        evidence_images = {
            "tc_before_b64": base64.b64encode(tc_before).decode("utf-8"),
            "tc_after_b64": base64.b64encode(tc_after).decode("utf-8"),
            "ndvi_before_b64": base64.b64encode(ndvi_before).decode("utf-8"),
            "ndvi_after_b64": base64.b64encode(ndvi_after).decode("utf-8"),
        }

        yield Event(
            author=self.name,
            actions=EventActions(
                state_delta={
                    "analysis_spec": analysis_spec_json,
                    "evidence_images": json.dumps(evidence_images),
                    "geodata_result": geodata_result_json,
                }
            ),
        )


geodata_agent = GeoDataDeterministicAgent()
