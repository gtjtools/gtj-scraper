# OpenRouter Setup Guide for TrustScore

This guide will help you set up OpenRouter for TrustScore calculations.

## Why OpenRouter?

OpenRouter provides:
- ✅ Access to **multiple AI models** through one API
- ✅ **Lower costs** than direct provider APIs
- ✅ **Flexibility** to switch models without code changes
- ✅ **No vendor lock-in** - try different models easily
- ✅ **Built-in rate limiting** and error handling

## Step 1: Get Your API Key

1. Visit [OpenRouter.ai](https://openrouter.ai/)
2. Click **"Sign In"** or **"Sign Up"**
3. After logging in, go to [Keys](https://openrouter.ai/keys)
4. Click **"Create Key"**
5. Give it a name (e.g., "GoTrustJet Production")
6. Copy the API key (starts with `sk-or-...`)

⚠️ **Important**: Save this key securely! You won't be able to see it again.

## Step 2: Set Environment Variables

### For Development (Local)

Add to your `.env` file or shell profile:

```bash
# OpenRouter API Key (required)
export OPENROUTER_API_KEY="sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# LLM Provider (defaults to openrouter if not set)
export LLM_PROVIDER="openrouter"

# Model Selection (optional - defaults to claude-3.5-sonnet)
export OPENROUTER_MODEL="anthropic/claude-3.5-sonnet"
```

### For Production (Docker/Server)

Add to your `.env` file:

```env
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_PROVIDER=openrouter
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
```

## Step 3: Install Dependencies

```bash
pip install openai
```

That's it! The OpenRouter API is OpenAI-compatible, so we use the `openai` package.

## Step 4: Test Your Setup

Create a test script:

```python
import asyncio
import os
from src.trustscore.llm_client import create_llm_client

async def test_openrouter():
    # Check if API key is set
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ OPENROUTER_API_KEY not set!")
        return

    print(f"✓ API Key found: {api_key[:20]}...")

    # Create client
    try:
        client = create_llm_client(provider="openrouter")
        print("✓ OpenRouter client initialized")
    except Exception as e:
        print(f"❌ Failed to create client: {e}")
        return

    # Test with a simple prompt
    test_prompt = """You are a financial risk analyst. Score this scenario from 0-40:

    A company has 1 active UCC filing with a reputable bank from 2 years ago.
    No bankruptcy history. No late payments.

    Provide only an integer score between 0 and 40."""

    try:
        score, reasoning = await client.get_risk_score(test_prompt)
        print(f"\n✓ Test successful!")
        print(f"   Score: {score}")
        print(f"   Reasoning: {reasoning[:100]}...")
    except Exception as e:
        print(f"❌ API call failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_openrouter())
```

Run it:
```bash
python test_openrouter.py
```

Expected output:
```
✓ API Key found: sk-or-v1-xxx...
✓ OpenRouter client initialized
✓ Test successful!
   Score: 5
   Reasoning: Based on the provided information, this company demonstrates strong financial...
```

## Model Selection Guide

### Recommended Models for Risk Scoring

| Model | Cost/1M Tokens | Speed | Accuracy | Use Case |
|-------|----------------|-------|----------|----------|
| **anthropic/claude-3.5-sonnet** | $3 / $15 | ⚡⚡⚡ | ⭐⭐⭐⭐⭐ | **Default** - Best overall |
| anthropic/claude-3-opus | $15 / $75 | ⚡⚡ | ⭐⭐⭐⭐⭐ | Maximum accuracy |
| openai/gpt-4-turbo | $10 / $30 | ⚡⚡⚡ | ⭐⭐⭐⭐ | OpenAI preference |
| google/gemini-pro-1.5 | $0.13 / $0.38 | ⚡⚡⚡⚡ | ⭐⭐⭐⭐ | Budget option |
| meta-llama/llama-3.1-70b-instruct | $0.35 / $0.40 | ⚡⚡⚡⚡ | ⭐⭐⭐ | Open source |

*Pricing as of Nov 2024 - check [OpenRouter pricing](https://openrouter.ai/models) for current rates*

### How to Switch Models

Just change the environment variable:

```bash
# For production quality
export OPENROUTER_MODEL="anthropic/claude-3.5-sonnet"

# For maximum accuracy (more expensive)
export OPENROUTER_MODEL="anthropic/claude-3-opus"

# For budget-friendly (good quality)
export OPENROUTER_MODEL="google/gemini-pro-1.5"
```

No code changes needed! Restart your application to use the new model.

## Usage in Code

```python
from src.trustscore.calculator import TrustScoreCalculator, FleetScoreData, TailScoreData
from src.trustscore.llm_client import create_llm_client

async def calculate_trustscore():
    # Initialize OpenRouter client (automatic if env vars are set)
    llm_client = create_llm_client()

    # Create calculator
    calculator = TrustScoreCalculator(llm_client=llm_client)

    # Prepare your data
    fleet_data = FleetScoreData(
        operator_name="Example Aviation",
        operator_age_years=12.5,
        ntsb_incidents=[...],
        ucc_filings=[...],  # From UCC verification
        argus_rating="Gold",
        wyvern_rating="Wingman"
    )

    tail_data = TailScoreData(...)

    # Calculate - LLM will be called for financial and legal risk scoring
    result = await calculator.calculate_trust_score(fleet_data, tail_data)

    print(f"TrustScore: {result['trust_score']}/100")
```

## Monitoring Costs

OpenRouter provides cost tracking:

1. Visit [OpenRouter Activity](https://openrouter.ai/activity)
2. View your API usage and costs
3. Set up spending limits if needed

## Troubleshooting

### "OPENROUTER_API_KEY not set in environment"

**Solution**: Make sure you've exported the environment variable:
```bash
export OPENROUTER_API_KEY="your-key-here"
```

### "OpenRouter API call failed: 401 Unauthorized"

**Causes**:
- Invalid API key
- API key has been revoked
- Insufficient credits on OpenRouter account

**Solution**:
1. Check your API key at [OpenRouter Keys](https://openrouter.ai/keys)
2. Verify you have credits in your account
3. Generate a new key if needed

### "Rate limit exceeded"

**Solution**:
- OpenRouter has built-in rate limiting
- Wait a moment and retry
- Consider upgrading your OpenRouter tier

### "Model not found"

**Solution**:
- Check the model name at [OpenRouter Models](https://openrouter.ai/models)
- Model names are case-sensitive
- Use format: `provider/model-name` (e.g., `anthropic/claude-3.5-sonnet`)

## Cost Estimation

For a typical TrustScore calculation:
- 2 LLM calls per calculation (financial + legal risk)
- ~1,500 tokens per call (1,000 input + 500 output)
- Total: ~3,000 tokens per TrustScore

### Cost per 1,000 TrustScores:

| Model | Cost |
|-------|------|
| Claude 3.5 Sonnet | ~$54 |
| Claude 3 Opus | ~$270 |
| GPT-4 Turbo | ~$120 |
| Gemini Pro 1.5 | ~$2 |
| Llama 3.1 70B | ~$1.50 |

## Best Practices

1. **Start with Claude 3.5 Sonnet** - It's the default for a reason
2. **Monitor your usage** - Check OpenRouter activity dashboard
3. **Set spending limits** - Use OpenRouter's budget controls
4. **Cache results** - Don't recalculate scores unnecessarily
5. **Test thoroughly** - Validate scoring accuracy with your data

## Support

- **OpenRouter Docs**: https://openrouter.ai/docs
- **OpenRouter Discord**: https://discord.gg/openrouter
- **Model Comparisons**: https://openrouter.ai/models

## Next Steps

After setup:
1. ✅ Test your OpenRouter connection
2. ✅ Run a sample TrustScore calculation
3. ✅ Integrate with your UCC verification flow
4. ✅ Monitor costs and adjust model as needed
