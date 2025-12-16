"""
LLM Client for TrustScore Risk Assessment
Supports OpenAI and Anthropic (Claude)
"""
import os
import re
from typing import Tuple, Optional
from enum import Enum


class LLMProvider(Enum):
    """Supported LLM providers"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"


class LLMClient:
    """
    LLM Client for risk scoring with support for multiple providers
    """

    def __init__(self, provider: LLMProvider = LLMProvider.OPENROUTER):
        """
        Initialize LLM client

        Args:
            provider: LLM provider to use (OpenAI, Anthropic, or OpenRouter)
        """
        self.provider = provider
        self.client = None

        if provider == LLMProvider.OPENAI:
            self._init_openai()
        elif provider == LLMProvider.ANTHROPIC:
            self._init_anthropic()
        elif provider == LLMProvider.OPENROUTER:
            self._init_openrouter()
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def _init_openai(self):
        """Initialize OpenAI client"""
        try:
            import openai
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                print("⚠️  WARNING: OPENAI_API_KEY not set in environment")
                return
            self.client = openai.AsyncOpenAI(api_key=api_key)
            print("✓ OpenAI client initialized")
        except ImportError:
            print("⚠️  ERROR: openai package not installed. Run: pip install openai")
        except Exception as e:
            print(f"⚠️  ERROR initializing OpenAI client: {e}")

    def _init_anthropic(self):
        """Initialize Anthropic client"""
        try:
            import anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                print("⚠️  WARNING: ANTHROPIC_API_KEY not set in environment")
                return
            self.client = anthropic.AsyncAnthropic(api_key=api_key)
            print("✓ Anthropic client initialized")
        except ImportError:
            print("⚠️  ERROR: anthropic package not installed. Run: pip install anthropic")
        except Exception as e:
            print(f"⚠️  ERROR initializing Anthropic client: {e}")

    def _init_openrouter(self):
        """Initialize OpenRouter client (uses OpenAI SDK with custom base URL)"""
        try:
            import openai
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                print("⚠️  WARNING: OPENROUTER_API_KEY not set in environment")
                return

            self.client = openai.AsyncOpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1"
            )
            print("✓ OpenRouter client initialized")
        except ImportError:
            print("⚠️  ERROR: openai package not installed. Run: pip install openai")
        except Exception as e:
            print(f"⚠️  ERROR initializing OpenRouter client: {e}")

    async def get_completion(self, prompt: str) -> str:
        """
        Get text completion from LLM (for explanations and insights)

        Args:
            prompt: Complete prompt for the LLM

        Returns:
            Text response from the LLM

        Raises:
            Exception: If LLM call fails
        """
        if not self.client:
            raise Exception("LLM client not initialized. Check API key configuration.")

        if self.provider == LLMProvider.OPENAI:
            return await self._get_completion_openai(prompt)
        elif self.provider == LLMProvider.ANTHROPIC:
            return await self._get_completion_anthropic(prompt)
        elif self.provider == LLMProvider.OPENROUTER:
            return await self._get_completion_openrouter(prompt)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    async def get_risk_score(self, prompt: str) -> Tuple[int, str]:
        """
        Get risk score from LLM

        Args:
            prompt: Complete prompt for risk assessment

        Returns:
            Tuple of (score: int, reasoning: str)

        Raises:
            Exception: If LLM call fails
        """
        if not self.client:
            raise Exception("LLM client not initialized. Check API key configuration.")

        if self.provider == LLMProvider.OPENAI:
            return await self._get_score_openai(prompt)
        elif self.provider == LLMProvider.ANTHROPIC:
            return await self._get_score_anthropic(prompt)
        elif self.provider == LLMProvider.OPENROUTER:
            return await self._get_score_openrouter(prompt)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    async def _get_score_openai(self, prompt: str) -> Tuple[int, str]:
        """
        Get risk score from OpenAI

        Args:
            prompt: Complete prompt for risk assessment

        Returns:
            Tuple of (score, reasoning)
        """
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4",  # or "gpt-4-turbo-preview" for faster responses
                messages=[
                    {
                        "role": "system",
                        "content": "You are a financial and legal risk analyst. Provide only a single integer score between 0 and 40."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Lower temperature for more consistent scoring
                max_tokens=500,
            )

            content = response.choices[0].message.content.strip()

            # Extract score from response
            score = self._extract_score(content)

            # Validate score is in range
            if not (0 <= score <= 40):
                print(f"⚠️  Warning: LLM returned score {score} outside range 0-40. Clamping.")
                score = max(0, min(40, score))

            return score, content

        except Exception as e:
            raise Exception(f"OpenAI API call failed: {str(e)}")

    async def _get_score_anthropic(self, prompt: str) -> Tuple[int, str]:
        """
        Get risk score from Anthropic (Claude)

        Args:
            prompt: Complete prompt for risk assessment

        Returns:
            Tuple of (score, reasoning)
        """
        try:
            response = await self.client.messages.create(
                model="claude-3-5-sonnet-20241022",  # Latest Claude model
                max_tokens=1024,
                temperature=0.3,  # Lower temperature for more consistent scoring
                system="You are a financial and legal risk analyst. Provide only a single integer score between 0 and 40.",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            # Extract text from response
            content = response.content[0].text.strip()

            # Extract score from response
            score = self._extract_score(content)

            # Validate score is in range
            if not (0 <= score <= 40):
                print(f"⚠️  Warning: LLM returned score {score} outside range 0-40. Clamping.")
                score = max(0, min(40, score))

            return score, content

        except Exception as e:
            raise Exception(f"Anthropic API call failed: {str(e)}")

    async def _get_score_openrouter(self, prompt: str) -> Tuple[int, str]:
        """
        Get risk score from OpenRouter

        Args:
            prompt: Complete prompt for risk assessment

        Returns:
            Tuple of (score, reasoning)
        """
        # Get model preference from environment, default to Claude 3.5 Sonnet
        model = os.getenv(
            "OPENROUTER_MODEL",
            "anthropic/claude-3.5-sonnet"  # Cost-effective and high quality
        )

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a financial and legal risk analyst. Provide only a single integer score between 0 and 40."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Lower temperature for more consistent scoring
                max_tokens=500,
                # OpenRouter-specific headers can be added via extra_headers if needed
                # extra_headers={
                #     "HTTP-Referer": "https://gotrustjet.com",
                #     "X-Title": "GoTrustJet Risk Scoring"
                # }
            )

            content = response.choices[0].message.content.strip()

            # Extract score from response
            score = self._extract_score(content)

            # Validate score is in range
            if not (0 <= score <= 40):
                print(f"⚠️  Warning: LLM returned score {score} outside range 0-40. Clamping.")
                score = max(0, min(40, score))

            return score, content

        except Exception as e:
            raise Exception(f"OpenRouter API call failed: {str(e)}")

    async def _get_completion_openai(self, prompt: str) -> str:
        """Get text completion from OpenAI"""
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": "You are an aviation safety analyst providing clear, professional insights."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise Exception(f"OpenAI API call failed: {str(e)}")

    async def _get_completion_anthropic(self, prompt: str) -> str:
        """Get text completion from Anthropic"""
        try:
            response = await self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                temperature=0.7,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.content[0].text.strip()
        except Exception as e:
            raise Exception(f"Anthropic API call failed: {str(e)}")

    async def _get_completion_openrouter(self, prompt: str) -> str:
        """Get text completion from OpenRouter"""
        try:
            response = await self.client.chat.completions.create(
                model="anthropic/claude-3.5-sonnet",
                messages=[
                    {"role": "system", "content": "You are an aviation safety analyst providing clear, professional insights."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise Exception(f"OpenRouter API call failed: {str(e)}")

    def _extract_score(self, text: str) -> int:
        """
        Extract integer score from LLM response text

        Args:
            text: LLM response text

        Returns:
            Integer score

        Raises:
            ValueError: If no valid score found
        """
        # Try to find a number in the text
        # Look for standalone numbers first (most common case)
        standalone_match = re.search(r'^\s*(\d+)\s*$', text, re.MULTILINE)
        if standalone_match:
            return int(standalone_match.group(1))

        # Look for "Score: X" or "Risk Score: X" patterns
        score_pattern = re.search(r'(?:score|risk|rating):\s*(\d+)', text, re.IGNORECASE)
        if score_pattern:
            return int(score_pattern.group(1))

        # Look for any number between 0 and 40
        numbers = re.findall(r'\b(\d+)\b', text)
        for num_str in numbers:
            num = int(num_str)
            if 0 <= num <= 40:
                return num

        # If we get here, try the first number found
        if numbers:
            return int(numbers[0])

        raise ValueError(f"Could not extract valid score from LLM response: {text}")


# Convenience function to create default client
def create_llm_client(provider: Optional[str] = None) -> LLMClient:
    """
    Create LLM client with default or specified provider

    Args:
        provider: Optional provider name ("openai", "anthropic", or "openrouter")
                 If not specified, uses OPENROUTER by default

    Returns:
        Configured LLMClient instance
    """
    if provider:
        provider_enum = LLMProvider(provider.lower())
    else:
        # Check environment variable for provider preference
        provider_str = os.getenv("LLM_PROVIDER", "openrouter").lower()
        provider_enum = LLMProvider(provider_str)

    return LLMClient(provider=provider_enum)
