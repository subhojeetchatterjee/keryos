try:
    from google.adk.agents import SequentialAgent

    from agents.subagents.analytics_deterministic import analytics_agent
    from agents.subagents.geodata_deterministic import geodata_agent
    from agents.subagents.intake_deterministic import intake_agent
    from agents.subagents.report_llm import report_agent
    from agents.subagents.verifier_llm import verifier_agent

    root_agent = SequentialAgent(
        name="KeryosTrustPipeline",
        description="Deterministic EO pipeline + Vertex AI writer + Vertex AI verifier.",
        sub_agents=[
            intake_agent,
            geodata_agent,
            analytics_agent,
            report_agent,
            verifier_agent,
        ],
    )
except ImportError:
    root_agent = None
