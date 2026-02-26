"""
Document Analyzer Service
Reads PDF/document files and uses AI (OpenRouter) to interpret and summarize their content.
Supports NTSB reports, UCC filings, and other aviation-related documents.
"""

import os
import base64
from typing import Dict, Any, List, Optional

import openai


# -- Constants --

# Maximum pages to extract text from before truncating
MAX_PDF_PAGES = 30

# Maximum characters of extracted text to send to the LLM
MAX_TEXT_LENGTH = 12_000

# System prompt tailored for aviation document interpretation
SYSTEM_PROMPT = (
    "You are an expert aviation safety and regulatory analyst. "
    "You will be given the contents of a document (NTSB accident report, UCC filing, "
    "FAA enforcement action, or other aviation-related record). "
    "Provide a concise, structured summary that includes:\n"
    "1. **Document Type** - What kind of document this is\n"
    "2. **Key Findings** - The most important facts (who, what, when, where)\n"
    "3. **Probable Cause** - If applicable (NTSB reports)\n"
    "4. **Risk Implications** - What this means for operator trust/safety scoring\n"
    "5. **Severity Assessment** - Rate as: Critical / High / Medium / Low\n\n"
    "Be factual and precise. Do not speculate beyond what the document states. "
    "Keep the summary under 500 words."
)


class DocumentAnalyzer:
    """
    Service for reading documents (PDF, text) and generating AI-powered summaries
    using OpenRouter (OpenAI-compatible API).
    """

    def __init__(self) -> None:
        self.api_key: Optional[str] = os.getenv("OPENROUTER_API_KEY")
        self.model: str = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
        self.client: Optional[openai.OpenAI] = None

        if not self.api_key:
            print("WARNING: OPENROUTER_API_KEY not set -- DocumentAnalyzer disabled")
            return

        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    # -- Public API --

    async def analyze_pdf(
        self,
        pdf_path: str,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Read a PDF file and return an AI-generated interpretation.

        Args:
            pdf_path: Absolute path to the PDF file on disk.
            context: Optional extra context to include in the prompt
                     (e.g. operator name, accident number).

        Returns:
            Dict with keys:
                - file_path: str
                - file_name: str
                - status: "success" | "failed"
                - summary: str (AI-generated summary, or None on failure)
                - text_length: int (characters of extracted text)
                - page_count: int
                - error: str | None
        """
        file_name = os.path.basename(pdf_path)

        if not os.path.isfile(pdf_path):
            return self._error_result(file_name, pdf_path, f"File not found: {pdf_path}")

        # Step 1: Try text extraction first (faster, cheaper)
        text, page_count = self._extract_pdf_text(pdf_path)

        if text and len(text.strip()) > 100:
            # Sufficient text extracted -- use text-based analysis
            return await self._analyze_text(
                text=text,
                page_count=page_count,
                file_name=file_name,
                file_path=pdf_path,
                context=context,
            )

        # Step 2: Fallback to vision-based analysis for scanned/image PDFs
        print(f"  Text extraction yielded minimal content ({len(text)} chars), "
              f"falling back to vision-based analysis for {file_name}")
        return await self._analyze_pdf_as_image(
            pdf_path=pdf_path,
            file_name=file_name,
            context=context,
        )

    async def analyze_documents_in_folder(
        self,
        folder_path: str,
        context: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Analyze all PDF files in a given folder.

        Args:
            folder_path: Path to the folder containing documents.
            context: Optional context string for prompts.

        Returns:
            List of analysis result dicts (one per document).
        """
        if not os.path.isdir(folder_path):
            print(f"  WARNING: Folder not found: {folder_path}")
            return []

        results: List[Dict[str, Any]] = []

        for file_name in sorted(os.listdir(folder_path)):
            if not file_name.lower().endswith(".pdf"):
                continue

            file_path = os.path.join(folder_path, file_name)
            print(f"  Analyzing document: {file_name}")
            result = await self.analyze_pdf(file_path, context=context)
            results.append(result)

        return results

    # -- Private helpers --

    def _extract_pdf_text(self, pdf_path: str) -> tuple[str, int]:
        """
        Extract text content from a PDF file using pypdf.

        Returns:
            Tuple of (extracted_text, page_count).
            On failure returns ("", 0).
        """
        try:
            from pypdf import PdfReader

            reader = PdfReader(pdf_path)
            page_count = len(reader.pages)
            pages_to_read = min(page_count, MAX_PDF_PAGES)

            text_parts: List[str] = []
            for i in range(pages_to_read):
                page_text = reader.pages[i].extract_text() or ""
                text_parts.append(page_text)

            full_text = "\n\n".join(text_parts)

            # Truncate to avoid exceeding LLM context limits
            if len(full_text) > MAX_TEXT_LENGTH:
                full_text = full_text[:MAX_TEXT_LENGTH] + "\n\n[... text truncated ...]"

            return full_text, page_count

        except ImportError:
            print("  WARNING: pypdf not installed. Run: pip install pypdf")
            return "", 0
        except Exception as e:
            print(f"  WARNING: PDF text extraction failed for {pdf_path}: {e}")
            return "", 0

    async def _analyze_text(
        self,
        text: str,
        page_count: int,
        file_name: str,
        file_path: str,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send extracted text to LLM for interpretation."""
        if not self.client:
            return self._error_result(
                file_name, file_path, "AI client not initialized (missing API key)"
            )

        prompt_parts = ["Analyze the following document content:\n"]
        if context:
            prompt_parts.append(f"Context: {context}\n")
        prompt_parts.append(f"Document: {file_name}\n")
        prompt_parts.append(f"Pages: {page_count}\n\n")
        prompt_parts.append("--- DOCUMENT CONTENT ---\n")
        prompt_parts.append(text)
        prompt_parts.append("\n--- END DOCUMENT CONTENT ---")

        user_prompt = "".join(prompt_parts)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=1024,
            )

            summary = response.choices[0].message.content.strip()
            print(f"  AI analysis complete for {file_name}")

            return {
                "file_path": file_path,
                "file_name": file_name,
                "status": "success",
                "summary": summary,
                "text_length": len(text),
                "page_count": page_count,
                "analysis_method": "text_extraction",
                "error": None,
            }

        except Exception as e:
            return self._error_result(file_name, file_path, f"LLM call failed: {e}")

    async def _analyze_pdf_as_image(
        self,
        pdf_path: str,
        file_name: str,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fallback: encode the raw PDF as base64 and send to a vision-capable model.
        NOTE: OpenRouter vision models accept PDF as base64 data URIs.
        If the model does not support PDF input, this will gracefully fail.
        """
        if not self.client:
            return self._error_result(
                file_name, pdf_path, "AI client not initialized (missing API key)"
            )

        try:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            # NOTE: Some models on OpenRouter support PDF as a document type via
            # the file content block. We use the standard image_url approach with
            # application/pdf MIME type, which Claude models support.
            pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

            prompt_text = "Analyze this document thoroughly."
            if context:
                prompt_text += f"\nContext: {context}"

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:application/pdf;base64,{pdf_base64}"
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt_text,
                            },
                        ],
                    },
                ],
                temperature=0.3,
                max_tokens=1024,
            )

            summary = response.choices[0].message.content.strip()
            print(f"  AI vision analysis complete for {file_name}")

            return {
                "file_path": pdf_path,
                "file_name": file_name,
                "status": "success",
                "summary": summary,
                "text_length": 0,
                "page_count": 0,
                "analysis_method": "vision",
                "error": None,
            }

        except Exception as e:
            return self._error_result(
                file_name, pdf_path, f"Vision analysis failed: {e}"
            )

    def _error_result(
        self, file_name: str, file_path: str, error_msg: str
    ) -> Dict[str, Any]:
        """Build a standardized error result dict."""
        print(f"  ERROR analyzing {file_name}: {error_msg}")
        return {
            "file_path": file_path,
            "file_name": file_name,
            "status": "failed",
            "summary": None,
            "text_length": 0,
            "page_count": 0,
            "analysis_method": None,
            "error": error_msg,
        }


def create_document_analyzer() -> DocumentAnalyzer:
    """Factory function -- creates and returns a DocumentAnalyzer instance."""
    return DocumentAnalyzer()
