"""
Example usage of TrustScore Calculator
"""
import asyncio
from datetime import datetime, timedelta
from src.trustscore.calculator import (
    TrustScoreCalculator,
    FleetScoreData,
    TailScoreData
)
from src.trustscore.llm_client import create_llm_client


async def example_trustscore_calculation():
    """
    Example showing how to calculate TrustScore with real data
    """

    # 1. Create LLM client (optional - calculator works without it but will return 0 for LLM scores)
    # Set OPENROUTER_API_KEY in environment first (or ANTHROPIC_API_KEY / OPENAI_API_KEY)
    try:
        # Defaults to OpenRouter
        llm_client = create_llm_client()

        # Or specify a provider explicitly:
        # llm_client = create_llm_client(provider="openrouter")
        # llm_client = create_llm_client(provider="anthropic")
        # llm_client = create_llm_client(provider="openai")
    except Exception as e:
        print(f"Warning: Could not initialize LLM client: {e}")
        llm_client = None

    # 2. Initialize calculator
    calculator = TrustScoreCalculator(llm_client=llm_client)

    # 3. Prepare FleetScore data
    fleet_data = FleetScoreData(
        operator_name="Example Aviation LLC",
        operator_age_years=15.5,

        # NTSB incidents
        ntsb_incidents=[
            {
                "event_id": "NYC12FA001",
                "event_date": (datetime.utcnow() - timedelta(days=2*365)).isoformat(),
                "event_type": "Accident",
                "injury_level": "None",
                "location": "New York, NY"
            },
            {
                "event_id": "LAX18IA042",
                "event_date": (datetime.utcnow() - timedelta(days=4*365)).isoformat(),
                "event_type": "Incident",
                "injury_level": "Minor",
                "location": "Los Angeles, CA"
            }
        ],

        # UCC filings from Browserbase scraping
        ucc_filings=[
            {
                "status": "Active",
                "filing_date": "2023-01-15",
                "debtor": "Example Aviation LLC",
                "secured_party": "Wells Fargo Bank",
                "collateral": "Aircraft N123AB"
            },
            {
                "status": "Lapsed",
                "filing_date": "2020-06-01",
                "debtor": "Example Aviation LLC",
                "secured_party": "Bank of America",
                "collateral": "Aircraft N456CD"
            }
        ],

        # Certifications
        argus_rating="Gold Plus",
        wyvern_rating="Wingman",

        # Optional: Bankruptcy history
        bankruptcy_history=None,

        # Optional: FAA violations
        faa_violations=None
    )

    # 4. Prepare TailScore data (for specific aircraft)
    tail_data = TailScoreData(
        aircraft_age_years=8.5,
        operator_name="Example Aviation LLC",
        registered_owner="Example Aviation LLC",
        fractional_owner=False,

        # NTSB incidents for this specific tail number
        ntsb_incidents=[
            {
                "event_id": "NYC12FA001",
                "event_date": (datetime.utcnow() - timedelta(days=2*365)).isoformat(),
                "event_type": "Accident",
                "injury_level": "None",
                "location": "New York, NY"
            }
        ]
    )

    # 5. Calculate TrustScore
    print("\n" + "="*80)
    print("CALCULATING TRUSTSCORE")
    print("="*80 + "\n")

    result = await calculator.calculate_trust_score(fleet_data, tail_data)

    # 6. Display results
    print(f"🎯 TRUSTSCORE: {result['trust_score']}/100")
    print(f"   Fleet Score: {result['fleet_score']}/100")
    print(f"   Tail Score: {result['tail_score']}/100")
    print(f"\nCalculated at: {result['calculated_at']}")

    print("\n" + "="*80)
    print("FLEET SCORE BREAKDOWN")
    print("="*80)
    fleet_breakdown = result['fleet_breakdown']
    print(f"Initial Score: {fleet_breakdown['initial_score']}")
    print(f"Final Score: {fleet_breakdown['final_score']}")
    print(f"Total Deductions: {fleet_breakdown['total_deductions']}")
    print("\nDeductions:")
    for deduction in fleet_breakdown['deductions']:
        print(f"  - {deduction['category']}: -{deduction['deduction']} points")
        if 'details' in deduction:
            print(f"    Details: {deduction['details']}")
        if 'reasoning' in deduction and deduction['reasoning']:
            print(f"    Reasoning: {deduction['reasoning'][:100]}...")

    print("\n" + "="*80)
    print("TAIL SCORE BREAKDOWN")
    print("="*80)
    tail_breakdown = result['tail_breakdown']
    print(f"Initial Score: {tail_breakdown['initial_score']}")
    print(f"Final Score: {tail_breakdown['final_score']}")
    print(f"Total Deductions: {tail_breakdown['total_deductions']}")
    print("\nDeductions:")
    for deduction in tail_breakdown['deductions']:
        print(f"  - {deduction['category']}: -{deduction['deduction']} points")
        if 'details' in deduction:
            print(f"    Details: {deduction['details']}")

    return result


async def example_fleet_score_only():
    """
    Example showing how to calculate just FleetScore
    """
    llm_client = None  # No LLM for this example
    calculator = TrustScoreCalculator(llm_client=llm_client)

    fleet_data = FleetScoreData(
        operator_name="Quick Example Air",
        operator_age_years=5.0,
        ntsb_incidents=[],
        ucc_filings=[],
        argus_rating="Platinum",
        wyvern_rating=None
    )

    score, breakdown = await calculator.calculate_fleet_score(fleet_data)

    print(f"\n✈️  Fleet Score: {score}/100")
    print(f"Total Deductions: {breakdown['total_deductions']}")


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
        ntsb_incidents=[]
    )

    score, breakdown = calculator.calculate_tail_score(tail_data)

    print(f"\n🛩️  Tail Score: {score}/100")
    print(f"Total Deductions: {breakdown['total_deductions']}")


if __name__ == "__main__":
    # Run full example
    asyncio.run(example_trustscore_calculation())

    # Or run individual examples:
    # asyncio.run(example_fleet_score_only())
    # asyncio.run(example_tail_score_only())
