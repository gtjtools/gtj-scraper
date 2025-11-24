# TrustScore Calculator

Comprehensive scoring system for aviation operators and aircraft based on financial risk, legal risk, safety records, and certifications.

## Overview

**TrustScore = 0.5 × FleetScore + 0.5 × TailScore**

- **FleetScore**: Evaluates the operator's overall standing (out of 100)
- **TailScore**: Evaluates a specific aircraft (out of 100)

## Installation

### Required Dependencies

```bash
# Core dependencies (already in requirements.txt)
pip install httpx pydantic sqlalchemy

# For LLM integration
pip install openai  # Used for OpenAI, OpenRouter, and other OpenAI-compatible APIs

# Optional: Only if using Anthropic directly
pip install anthropic
```

### Environment Variables

```bash
# OpenRouter (Recommended - access to multiple models)
export OPENROUTER_API_KEY="your-openrouter-api-key"
export LLM_PROVIDER="openrouter"  # This is the default

# Optional: Specify which model to use on OpenRouter
export OPENROUTER_MODEL="anthropic/claude-3.5-sonnet"  # Default, cost-effective

# Other options:
# export OPENROUTER_MODEL="anthropic/claude-3-opus"  # Most capable
# export OPENROUTER_MODEL="openai/gpt-4-turbo"
# export OPENROUTER_MODEL="google/gemini-pro-1.5"
# export OPENROUTER_MODEL="meta-llama/llama-3.1-70b-instruct"

# Alternative: Use Anthropic directly
# export ANTHROPIC_API_KEY="your-anthropic-api-key"
# export LLM_PROVIDER="anthropic"

# Alternative: Use OpenAI directly
# export OPENAI_API_KEY="your-openai-api-key"
# export LLM_PROVIDER="openai"
```

### Getting Your OpenRouter API Key

1. Go to [OpenRouter.ai](https://openrouter.ai/)
2. Sign up or log in to your account
3. Navigate to [Keys](https://openrouter.ai/keys)
4. Create a new API key
5. Copy the key and set it as `OPENROUTER_API_KEY`

### Choosing a Model on OpenRouter

OpenRouter gives you access to many models. Recommended options for risk scoring:

| Model | Cost | Speed | Quality | Best For |
|-------|------|-------|---------|----------|
| `anthropic/claude-3.5-sonnet` | $$ | Fast | Excellent | **Default** - Best balance |
| `anthropic/claude-3-opus` | $$$ | Medium | Outstanding | Maximum accuracy |
| `openai/gpt-4-turbo` | $$$ | Fast | Excellent | OpenAI ecosystem |
| `google/gemini-pro-1.5` | $ | Very Fast | Good | Budget-friendly |
| `meta-llama/llama-3.1-70b-instruct` | $ | Fast | Good | Open source option |

Set your choice via:
```bash
export OPENROUTER_MODEL="anthropic/claude-3.5-sonnet"
```

See all available models at [OpenRouter Models](https://openrouter.ai/models)

## Quick Start

```python
import asyncio
from src.trustscore.calculator import TrustScoreCalculator, FleetScoreData, TailScoreData
from src.trustscore.llm_client import create_llm_client

async def calculate_score():
    # Initialize with LLM client (defaults to OpenRouter)
    llm_client = create_llm_client()

    # Or specify a provider explicitly:
    # llm_client = create_llm_client(provider="openrouter")
    # llm_client = create_llm_client(provider="anthropic")
    # llm_client = create_llm_client(provider="openai")

    calculator = TrustScoreCalculator(llm_client=llm_client)

    # Prepare data
    fleet_data = FleetScoreData(
        operator_name="Example Aviation",
        operator_age_years=12.5,
        ntsb_incidents=[...],
        ucc_filings=[...],
        argus_rating="Gold",
        wyvern_rating="Wingman"
    )

    tail_data = TailScoreData(
        aircraft_age_years=8.0,
        operator_name="Example Aviation",
        registered_owner="Example Aviation",
        fractional_owner=False,
        ntsb_incidents=[...]
    )

    # Calculate
    result = await calculator.calculate_trust_score(fleet_data, tail_data)

    print(f"TrustScore: {result['trust_score']}/100")
    print(f"Fleet Score: {result['fleet_score']}/100")
    print(f"Tail Score: {result['tail_score']}/100")

asyncio.run(calculate_score())
```

## FleetScore Calculation

**Initial Score: 100 points**

### Deductions

1. **Financial Risk (0-40 points)** - LLM Analysis
   - Based on UCC filings, bankruptcy history, liens
   - Considers debtor quality and payment history

2. **Legal Risk (0-40 points)** - LLM Analysis
   - Based on UCC filings, bankruptcy, NTSB incidents, FAA violations
   - Evaluates severity and frequency of legal issues

3. **Operator Age**
   - Deduct: `2 × (Age in Years - 10)` (minimum 0)
   - Example: 15-year-old operator = 2 × (15 - 10) = 10 points

4. **Recent NTSB Accidents**
   - Deduct 2 points per ACCIDENT event type in last 5 years

5. **Certifications** (use better of ARGUS/WYVERN)

   | Certification | ARGUS | WYVERN | Deduction |
   |--------------|-------|--------|-----------|
   | Top Tier | Platinum Elite | - | 0 |
   | Premium | Platinum | Wingman PRO | -2 |
   | Standard | Gold Plus | Wingman | -4 |
   | Basic | Gold | Registered Operator | -6 |
   | None | None | None | -10 |

## TailScore Calculation

**Initial Score: 100 points**

### Deductions

1. **Aircraft Age**

   | Age Range | Deduction |
   |-----------|-----------|
   | 2-5 years | 0 |
   | 5-8 years | -2 |
   | 8-12 years | -4 |
   | 12-16 years | -6 |
   | 16-20 years | -8 |
   | 20+ years | -10 |
   | < 2 years | -10 |

2. **Owner Mismatch**
   - Deduct 10 points if Operator Name ≠ Registered Owner

3. **Fractional Ownership**
   - Deduct 5 points if fractional_owner = TRUE

4. **NTSB Incidents**

   **Age-based deduction:**
   - `2 × (Age of Event in Years - 10)` (minimum 0)

   **Injury level deduction:**

   | Injury Level | Deduction |
   |--------------|-----------|
   | None | 0 |
   | Minor | -10 |
   | Serious | -20 |
   | Fatal | -50 |

   **Multiplier:** All values ×2 if EVENT TYPE = "Accident"

## LLM Integration

### Financial Risk Prompt

The LLM evaluates financial stability based on:
- Active UCC filings
- Bankruptcy history
- Lien quality and frequency
- Payment history (from lapsed filings)

Returns: Integer 0-40

### Legal Risk Prompt

The LLM evaluates legal risk based on:
- Active UCC filings
- Bankruptcy history
- NTSB incidents and potential legal issues
- FAA violations
- Age and severity of incidents

Returns: Integer 0-40

### Supported LLM Providers

1. **OpenRouter** - Recommended ⭐
   - Access to multiple models through one API
   - Default model: `anthropic/claude-3.5-sonnet`
   - Cost-effective with flexible model selection
   - No vendor lock-in
   - [Get API key](https://openrouter.ai/)

2. **Anthropic (Claude Direct)**
   - Model: `claude-3-5-sonnet-20241022`
   - Direct access to Claude
   - Good for dedicated Claude usage

3. **OpenAI (GPT-4 Direct)**
   - Model: `gpt-4`
   - Direct access to GPT-4
   - Alternative option

## Data Structures

### FleetScoreData

```python
@dataclass
class FleetScoreData:
    operator_name: str
    operator_age_years: float
    ntsb_incidents: List[Dict[str, Any]]
    ucc_filings: List[Dict[str, Any]]
    argus_rating: Optional[str] = None
    wyvern_rating: Optional[str] = None
    bankruptcy_history: Optional[List[Dict[str, Any]]] = None
    faa_violations: Optional[List[Dict[str, Any]]] = None
```

### TailScoreData

```python
@dataclass
class TailScoreData:
    aircraft_age_years: float
    operator_name: str
    registered_owner: str
    fractional_owner: bool
    ntsb_incidents: List[Dict[str, Any]]
```

### NTSB Incident Format

```python
{
    "event_id": "NYC12FA001",
    "event_date": "2023-01-15T10:30:00Z",
    "event_type": "Accident",  # or "Incident"
    "injury_level": "None",    # or "Minor", "Serious", "Fatal"
    "location": "New York, NY"
}
```

### UCC Filing Format

```python
{
    "status": "Active",  # or "Lapsed", "Terminated"
    "filing_date": "2023-01-15",
    "debtor": "Example Aviation LLC",
    "secured_party": "Wells Fargo Bank",
    "collateral": "Aircraft N123AB"
}
```

## API Response Format

```json
{
  "trust_score": 78.5,
  "fleet_score": 82.0,
  "tail_score": 75.0,
  "fleet_breakdown": {
    "initial_score": 100.0,
    "final_score": 82.0,
    "total_deductions": 18.0,
    "deductions": [
      {
        "category": "Financial Risk (LLM)",
        "deduction": 5,
        "reasoning": "Active UCC filings with reputable lenders..."
      },
      {
        "category": "Legal Risk (LLM)",
        "deduction": 3,
        "reasoning": "Minor FAA violation from 3 years ago..."
      },
      {
        "category": "Operator Age",
        "deduction": 10,
        "details": "Operator age: 15.0 years"
      }
    ]
  },
  "tail_breakdown": {
    "initial_score": 100.0,
    "final_score": 75.0,
    "total_deductions": 25.0,
    "deductions": [
      {
        "category": "Aircraft Age",
        "deduction": 4,
        "details": "Aircraft age: 9.5 years"
      }
    ]
  },
  "calculated_at": "2025-11-03T10:30:00.000Z"
}
```

## Integration with UCC Service

The TrustScore calculator is designed to work seamlessly with UCC filing data from the Browserbase scraping service:

```python
from src.scoring.ucc_service import UCCVerificationService
from src.trustscore.calculator import TrustScoreCalculator, FleetScoreData

# Get UCC filings
ucc_service = UCCVerificationService()
ucc_result = await ucc_service.verify_ucc_filings(operator_name)

# Extract UCC filings from result
ucc_filings = []
for state in ucc_result.get('visited_states', []):
    if state.get('flow_result'):
        ucc_filings.extend(state['flow_result'].get('filings', []))

# Calculate TrustScore
fleet_data = FleetScoreData(
    operator_name=operator_name,
    operator_age_years=calculate_age(operator),
    ntsb_incidents=ntsb_incidents,
    ucc_filings=ucc_filings,  # From UCC service
    argus_rating=operator.argus_rating,
    wyvern_rating=operator.wyvern_rating
)

calculator = TrustScoreCalculator(llm_client=llm_client)
result = await calculator.calculate_trust_score(fleet_data, tail_data)
```

## Error Handling

The calculator includes robust error handling:

- **No LLM client**: Returns 0 for LLM-based scores with reasoning explaining no client configured
- **LLM API failure**: Returns 0 for that score with error message in reasoning
- **Invalid scores**: Clamps scores to valid range (0-40 for LLM, 0-100 for final scores)
- **Missing data**: Gracefully handles missing optional fields

## Testing

Run the example:

```bash
cd /home/marc/projects/weyobe/gotrustjet/backend
python -m src.trustscore.example_usage
```

## Notes

- All scores are clamped to minimum of 0
- Weights (0.5/0.5) may be adjusted in future
- All deduction values are subject to change
- LLM scoring is optional but recommended for accuracy

## Files

- `calculator.py` - Main TrustScore calculation engine
- `llm_client.py` - LLM integration (OpenAI/Anthropic)
- `example_usage.py` - Usage examples
- `service.py` - Database CRUD operations
- `schemas.py` - Pydantic schemas
- `README.md` - This file
