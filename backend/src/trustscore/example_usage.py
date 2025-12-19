"""
Example usage of TrustScore Calculator - Algorithm v3
"""
import asyncio
from datetime import datetime, timedelta, timezone
from src.trustscore.calculator import (
    TrustScoreCalculator,
    FleetScoreData,
    TailScoreData
)
from src.trustscore.llm_client import LLMClient, LLMProvider


async def example_trustscore_calculation():
    """
    Example showing how to calculate TrustScore with real data (Algorithm v3)
    """

    # 1. Initialize calculator with optional LLM for AI insights
    try:
        llm_client = LLMClient(provider=LLMProvider.OPENROUTER)
        calculator = TrustScoreCalculator(llm_client=llm_client)
        print("✓ Using LLM for AI insights and explanations")
    except Exception as e:
        print(f"⚠️  LLM unavailable: {e}")
        calculator = TrustScoreCalculator(llm_client=None)
        print("✓ Using calculator without AI insights")

    # 2. Prepare FleetScore data
    fleet_data = FleetScoreData(
        operator_name="Example Aviation LLC",
        operator_age_years=15.5,
        fleet_size=12,  # Total number of aircraft in the fleet

        # Fleet-wide events (NTSB incidents and FAA enforcement actions)
        fleet_events=[
            {
                "event_id": "NYC12FA001",
                "event_date": (datetime.now(timezone.utc) - timedelta(days=2*365)).isoformat(),
                "event_type": "Accident",
                "injury_level": "None",
                "location": "New York, NY"
            },
            {
                "event_id": "LAX18IA042",
                "event_date": (datetime.now(timezone.utc) - timedelta(days=4*365)).isoformat(),
                "event_type": "Incident",
                "injury_level": "Minor",
                "location": "Los Angeles, CA"
            },
            {
                "event_id": "FAA-2022-001",
                "event_date": (datetime.now(timezone.utc) - timedelta(days=365)).isoformat(),
                "event_type": "FAA Enforcement",
                "severity": "Minor",
                "location": "Dallas, TX"
            }
        ],

        # UCC filings
        ucc_filings=[
            {
                "file_number": "20230115001",
                "status": "Active",
                "filing_date": "2023-01-15",
                "lapse_date": "2028-01-15",
                "lien_type": "Security Agreement",
                "debtor": "Example Aviation LLC",
                "secured_party": "Wells Fargo Bank",
                "collateral": "Aircraft N123AB"
            },
            {
                "file_number": "20200601001",
                "status": "Lapsed",
                "filing_date": "2020-06-01",
                "lapse_date": "2023-06-01",
                "lien_type": "Security Agreement",
                "debtor": "Example Aviation LLC",
                "secured_party": "Bank of America",
                "collateral": "Aircraft N456CD"
            }
        ],

        # Certifications
        argus_rating="Gold Plus",
        wyvern_rating="Wingman",

        # Optional: Bankruptcy history
        bankruptcy_history=None
    )

    # 3. Prepare TailScore data (for specific aircraft)
    tail_data = TailScoreData(
        aircraft_age_years=8.5,
        operator_name="Example Aviation LLC",
        registered_owner="Example Aviation LLC",
        fractional_owner=False,

        # Events specific to this tail number
        tail_events=[
            {
                "event_id": "NYC12FA001",
                "event_date": (datetime.now(timezone.utc) - timedelta(days=2*365)).isoformat(),
                "event_type": "Accident",
                "injury_level": "None",
                "location": "New York, NY"
            }
        ]
    )

    # 4. Calculate TrustScore
    print("\n" + "="*80)
    print("CALCULATING TRUSTSCORE (Algorithm v3)")
    print("="*80 + "\n")

    result = await calculator.calculate_trust_score(fleet_data, tail_data)

    # 5. Display results
    print(f"🎯 TRUSTSCORE: {result['trust_score']}/100")
    print(f"   Raw Score: {result['raw_score']}/100")
    print(f"   Confidence Score: {result['confidence_score']:.4f}")
    print(f"   Fleet Score: {result['fleet_score']}/100")
    print(f"   Tail Score: {result['tail_score']}/100")
    print(f"\nFormula: TrustScore = (0.6 × FleetScore + 0.4 × TailScore) × Confidence Score")
    print(f"Calculated at: {result['calculated_at']}")

    print("\n" + "="*80)
    print("FLEET SCORE BREAKDOWN")
    print("="*80)
    fleet_breakdown = result['fleet_breakdown']
    print(f"Final Score: {fleet_breakdown['final_score']}/100")
    print(f"Formula: {fleet_breakdown['formula']}")
    print("\nComponents:")
    for component, data in fleet_breakdown['components'].items():
        if isinstance(data, dict):
            print(f"  - {component}: {data['value']}")
            print(f"    └─ {data['description']}")
        else:
            print(f"  - {component}: {data}")

    if 'explanation' in fleet_breakdown:
        print("\n💡 AI Explanation:")
        print(f"   {fleet_breakdown['explanation']}")

    print("\n" + "="*80)
    print("TAIL SCORE BREAKDOWN")
    print("="*80)
    tail_breakdown = result['tail_breakdown']
    print(f"Final Score: {tail_breakdown['final_score']}/100")
    print(f"Formula: {tail_breakdown['formula']}")
    print("\nComponents:")
    for component, data in tail_breakdown['components'].items():
        if isinstance(data, dict):
            print(f"  - {component}: {data['value']}")
            print(f"    └─ {data['description']}")
        else:
            print(f"  - {component}: {data}")

    if 'explanation' in tail_breakdown:
        print("\n💡 AI Explanation:")
        print(f"   {tail_breakdown['explanation']}")

    # Show AI insights if available
    if 'ai_insights' in result:
        print("\n" + "="*80)
        print("AI INSIGHTS & RECOMMENDATIONS")
        print("="*80)
        print(result['ai_insights'])

    return result


async def example_fleet_score_only():
    """
    Example showing how to calculate just FleetScore
    """
    calculator = TrustScoreCalculator()

    fleet_data = FleetScoreData(
        operator_name="Quick Example Air",
        operator_age_years=5.0,
        fleet_size=8,
        fleet_events=[],
        ucc_filings=[],
        argus_rating="Platinum",
        wyvern_rating=None
    )

    score, breakdown = await calculator.calculate_fleet_score(fleet_data)

    print(f"\n✈️  Fleet Score: {score}/100")
    print(f"Components: {breakdown['components']}")


async def example_tail_score_only():
    """
    Example showing how to calculate just TailScore
    """
    calculator = TrustScoreCalculator()

    tail_data = TailScoreData(
        aircraft_age_years=3.5,
        operator_name="Quick Example Air",
        registered_owner="Quick Example Air",
        fractional_owner=False,
        tail_events=[]
    )

    score, breakdown = await calculator.calculate_tail_score(tail_data)

    print(f"\n🛩️  Tail Score: {score}/100")
    print(f"Components: {breakdown['components']}")


if __name__ == "__main__":
    # Run full example
    asyncio.run(example_trustscore_calculation())

    # Or run individual examples:
    # asyncio.run(example_fleet_score_only())
    # asyncio.run(example_tail_score_only())
