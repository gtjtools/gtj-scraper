"""
Image Analyzer Service
Reusable service for analyzing images with AI (Claude Vision via OpenRouter)
"""

import base64
import os
from typing import Dict, Any, Optional
from playwright.async_api import Page
import openai


class ImageAnalyzer:
    """
    Reusable service for analyzing images with AI using OpenRouter
    """

    def __init__(self):
        """Initialize the image analyzer with API credentials"""
        # Use OpenRouter API key
        self.api_key = os.getenv("OPENROUTER_API_KEY")

        if not self.api_key:
            print("⚠️  WARNING: OPENROUTER_API_KEY not set in environment")

        self.client = None
        if self.api_key:
            # Initialize OpenAI client with OpenRouter base URL
            self.client = openai.OpenAI(
                api_key=self.api_key,
                base_url="https://openrouter.ai/api/v1"
            )

    async def analyze_image_from_url(
        self,
        image_url: str,
        page: Page,
        prompt: str = "Analyze this image and extract all relevant information.",
        save_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Download an image from a URL and analyze it with Claude Vision

        Args:
            image_url: URL of the image to download and analyze
            page: Playwright page object for making requests
            prompt: Custom prompt for the AI analysis
            save_path: Optional path to save the downloaded image

        Returns:
            Dictionary containing:
                - image_url: Original image URL
                - image_path: Local path where image was saved (if save_path provided)
                - ai_analysis: AI analysis text
                - status: "success" or "failed"
                - error: Error message if failed
        """
        try:
            print(f"   📸 Downloading image from: {image_url}")

            # Download the image using Playwright
            response = await page.request.get(image_url)
            image_data = await response.body()

            print(f"   ✓ Image downloaded ({len(image_data)} bytes)")

            # Save image if path provided
            image_path = None
            if save_path:
                with open(save_path, "wb") as f:
                    f.write(image_data)
                image_path = save_path
                print(f"   ✓ Image saved to: {image_path}")
            else:
                # Default save to project temp directory
                # Get the backend root directory
                backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                temp_dir = os.path.join(backend_dir, "data", "temp")

                # Create temp directory if it doesn't exist
                os.makedirs(temp_dir, exist_ok=True)

                image_filename = f"image_{os.urandom(4).hex()}.png"
                image_path = os.path.join(temp_dir, image_filename)
                with open(image_path, "wb") as f:
                    f.write(image_data)
                print(f"   ✓ Image saved to: {image_path}")

            # Analyze the image
            analysis_result = await self.analyze_image_from_bytes(
                image_data=image_data,
                prompt=prompt
            )

            return {
                "image_url": image_url,
                "image_path": image_path,
                "ai_analysis": analysis_result.get("ai_analysis"),
                "status": analysis_result.get("status", "success"),
                "error": analysis_result.get("error")
            }

        except Exception as e:
            print(f"   ❌ Error downloading/analyzing image: {str(e)}")
            return {
                "error": str(e),
                "image_url": image_url,
                "status": "failed"
            }

    async def analyze_image_from_bytes(
        self,
        image_data: bytes,
        prompt: str = "Analyze this image and extract all relevant information.",
        media_type: str = "image/png"
    ) -> Dict[str, Any]:
        """
        Analyze image data with Claude Vision via OpenRouter

        Args:
            image_data: Raw image bytes
            prompt: Custom prompt for the AI analysis
            media_type: MIME type of the image (default: image/png)

        Returns:
            Dictionary containing:
                - ai_analysis: AI analysis text
                - status: "success" or "failed"
                - error: Error message if failed
        """
        try:
            if not self.client:
                return {
                    "error": "AI client not initialized. Check API key configuration.",
                    "status": "failed"
                }

            print("   🤖 Analyzing image with Claude Vision (via OpenRouter)...")

            # Encode image to base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')

            # Get model from environment or use default
            model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")

            # Call OpenRouter Vision API using OpenAI format
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{image_base64}"
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                max_tokens=2048,
                temperature=0.3
            )

            ai_response = response.choices[0].message.content

            print(f"   ✓ AI Analysis completed")
            print(f"\n--- AI Analysis ---")
            print(ai_response)
            print(f"--- End AI Analysis ---\n")

            return {
                "ai_analysis": ai_response,
                "status": "success"
            }

        except Exception as e:
            print(f"   ❌ Error during AI analysis: {str(e)}")
            return {
                "error": str(e),
                "status": "failed"
            }


# Convenience function to create analyzer instance
def create_image_analyzer() -> ImageAnalyzer:
    """
    Create an ImageAnalyzer instance

    Returns:
        Configured ImageAnalyzer instance
    """
    return ImageAnalyzer()
