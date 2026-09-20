from backend.agents.manager import decide_agent
from backend.agents.marketing.copy import write_ad_copy


def test_manager_routes_marketing_request():
    decision = decide_agent(
        "Write 5 ad variations for Arizona homeowners for a free solar consultation."
    )

    assert decision["department"] == "marketing"
    assert decision["agent"] in {"ad_copywriting", "ad_scripting"}


def test_ad_copy_produces_copy():
    result = write_ad_copy(
        "Create an educational ad for Arizona homeowners about a free solar consultation."
    )

    assert isinstance(result, str)
    assert len(result) > 100
    assert "Arizona" in result or "homeowners" in result.lower()
