from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

VERIFY_MODEL = "vertex_ai/claude-3-haiku@20240307"

verifier_agent = LlmAgent(
    name="VerifierAgent",
    model=LiteLlm(model=VERIFY_MODEL),
    description="Audits the evidence pack for hallucinated claims, internal inconsistencies, and missing disclaimers.",
    instruction="""\
You are Keryos VerifierAgent (auditor). You perform a strict grounding audit on the
final report to ensure no hallucinated or unsupported claims reach the output.

AUDIT RULES:
1. Every numeric claim in final_report must appear verbatim in metrics_result or geodata_result.
   Flag any number that does not.
2. Any causal claim (e.g. "flooding caused crop loss") must be supported by explicit evidence.
   If not supported, flag it.
3. Check that the verdict is internally consistent with the NDVI values in metrics_result.
4. Verify that limitations mention data quality issues present in the inputs (cloud cover,
   low pixel counts, sparse passes).
5. Never introduce new numbers. You may only quote numbers present in the inputs.
6. If final_report is missing any required key, list it as an issue.

Input state:
  analysis_spec:  {analysis_spec}
  geodata_result: {geodata_result}
  metrics_result: {metrics_result}
  final_report:   {final_report}

Return ONLY valid JSON with exactly these keys:
  approved                — boolean: true only if no grounding violations found
  trust_score             — integer 0–100: confidence that all claims are evidence-based
  issues_found            — array of strings: specific grounding violations or inconsistencies
  required_disclaimers    — array of strings: disclaimers that must be added
  corrected_markdown_report — string: the final_report markdown with violations removed or
                              qualified; identical to original if no changes needed
""",
    output_key="verification_result",
)
