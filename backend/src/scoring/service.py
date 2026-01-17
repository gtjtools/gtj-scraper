# src/scoring/service.py
import httpx
import os
import sys
import requests
import math
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from pydantic import UUID4
from sqlalchemy.orm import Session
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from src.common.models import Operator
from src.scoring.schemas import (
    NTSBIncident,
    NTSBQueryResponse,
    ScoreCalculationResponse,
)
from src.common.error import HTTPError

# NTSB API Configuration
NTSB_API_URL = "https://data.ntsb.gov/carol-main-public/api/Query/Main"
NTSB_TIMEOUT = 30.0  # seconds


class NTSBService:
    """Service for interacting with NTSB API"""

    @staticmethod
    def download_ntsb_pdf(
        accident_number: str, output_folder: str, operator_name: str
    ) -> bool:
        """
        Download NTSB accident report PDF.

        Note: The NTSB API generates reports on-demand, which can take
        30 seconds to several minutes.

        Args:
            accident_number: The NTSB accident number (Mkey value)
            output_folder: Folder path where PDF will be saved
            operator_name: Name of the operator for logging

        Returns:
            True if download successful, False otherwise
        """
        url = f"https://data.ntsb.gov/carol-repgen/api/Aviation/ReportMain/GenerateNewestReport/{accident_number}/pdf"

        # Create output folder if it doesn't exist
        os.makedirs(output_folder, exist_ok=True)

        output_filename = os.path.join(
            output_folder, f"ntsb_report_{accident_number}.pdf"
        )

        print(f"Downloading PDF from: {url}")
        print(f"Saving to: {output_filename}")
        print(
            f"Note: The NTSB server generates reports on-demand. This may take 30 seconds to several minutes."
        )

        # Configure session with retries
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        try:
            # Use a longer timeout - 5 minutes should be enough
            # timeout = (connect_timeout, read_timeout)
            response = session.get(url, timeout=(30, 300), stream=True)
            response.raise_for_status()

            # Write to file with progress indicator
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(output_filename, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size:
                            percent = (downloaded / total_size) * 100
                            sys.stdout.write(
                                f"\rProgress: {percent:.1f}% ({downloaded:,} / {total_size:,} bytes)"
                            )
                            sys.stdout.flush()
                        else:
                            sys.stdout.write(f"\rDownloaded: {downloaded:,} bytes")
                            sys.stdout.flush()

            file_size = os.path.getsize(output_filename)
            print(f"\n\nDownload complete! File size: {file_size:,} bytes")
            print(f"Saved to: {output_filename}")
            return True

        except requests.exceptions.Timeout:
            print(
                f"\nError: Request timed out. The NTSB server may be overloaded or the report is very large."
            )
            return False
        except requests.exceptions.RequestException as e:
            print(f"\nError downloading PDF: {e}")
            return False

    @staticmethod
    def _download_incident_pdfs(raw_data: Dict[str, Any], operator_name: str) -> None:
        """
        Download PDFs for all incidents in the NTSB response.

        Args:
            raw_data: Raw response from NTSB API
            operator_name: Name of the operator
        """
        if not isinstance(raw_data, dict) or "Results" not in raw_data:
            return

        # Create folder name with format: YYYYMMDD/operator_name
        timestamp = datetime.now().strftime("%Y%m%d")
        safe_operator_name = "".join(c if c.isalnum() else "_" for c in operator_name)
        folder_name = f"{timestamp}/{safe_operator_name}"

        # Get the project root directory and create temp folder path
        # Assuming the backend/src/scoring directory structure
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, "../../../"))
        temp_folder = os.path.join(project_root, "backend/data/temp", folder_name)

        print(f"\nDownloading NTSB PDFs to: {temp_folder}")

        # Extract Mkey (accident number) from each result
        for result in raw_data.get("Results", []):
            fields = result.get("Fields", [])

            # Find the Mkey field
            for field in fields:
                if field.get("FieldName") == "Mkey":
                    values = field.get("Values", [])
                    if values:
                        accident_number = values[0]
                        print(f"\nProcessing accident number: {accident_number}")
                        NTSBService.download_ntsb_pdf(
                            accident_number, temp_folder, operator_name
                        )

    @staticmethod
    async def query_ntsb_incidents(operator_name: str) -> Dict[str, Any]:
        """
        Query NTSB database for incidents related to an operator.

        Args:
            operator_name: The name of the operator to search for

        Returns:
            Dict containing the NTSB API response

        Raises:
            HTTPError: If the NTSB API request fails
        """
        print("FROM query_ntsb_incidents")
        payload = {
            "ResultSetSize": 50,
            "ResultSetOffset": 0,
            "QueryGroups": [
                {
                    "QueryRules": [
                        {
                            "RuleType": "Simple",
                            "Values": [operator_name],
                            "Columns": ["AviationOperation.OperatorName"],
                            # "Operator": "contains",
                            "Operator": "is",
                            "overrideColumn": "",
                            "selectedOption": {
                                "FieldName": "OperatorName",
                                "DisplayText": "Operator name",
                                "Columns": ["AviationOperation.OperatorName"],
                                "Selectable": True,
                                "InputType": "Text",
                                "RuleType": 0,
                                "Options": None,
                                "TargetCollection": "cases",
                                "UnderDevelopment": False,
                            },
                        }
                    ],
                    "AndOr": "and",
                    "inLastSearch": False,
                    "editedSinceLastSearch": False,
                }
            ],
            "AndOr": "and",
            "SortColumn": None,
            "SortDescending": True,
            "TargetCollection": "cases",
            "SessionId": 1171,
        }

        try:
            async with httpx.AsyncClient(timeout=NTSB_TIMEOUT) as client:
                response = await client.post(NTSB_API_URL, json=payload)
                response.raise_for_status()
                raw_data = response.json()

                # Download PDFs for each incident
                NTSBService._download_incident_pdfs(raw_data, operator_name)

                return raw_data
        except httpx.TimeoutException:
            raise HTTPError(
                detail=f"NTSB API request timed out after {NTSB_TIMEOUT} seconds"
            )
        except httpx.HTTPStatusError as e:
            raise HTTPError(detail=f"NTSB API returned error: {e.response.status_code}")
        except Exception as e:
            raise HTTPError(detail=f"Error querying NTSB API: {str(e)}")

    @staticmethod
    def _extract_field_value(fields: List[Dict], field_name: str) -> Optional[str]:
        """
        Extract a field value from NTSB Fields array.

        Args:
            fields: List of field dictionaries from NTSB response
            field_name: Name of the field to extract

        Returns:
            First value from the Values array, or None
        """
        for field in fields:
            if field.get("FieldName") == field_name:
                values = field.get("Values", [])
                return values[0] if values else None
        return None

    @staticmethod
    def parse_ntsb_response(raw_data: Dict[str, Any]) -> List[NTSBIncident]:
        """
        Parse NTSB API response into structured incident data.

        Args:
            raw_data: Raw response from NTSB API

        Returns:
            List of NTSBIncident objects
        """
        incidents = []

        # Extract incidents from NTSB response structure
        # Response format: { "Results": [ { "Fields": [...] } ] }
        if isinstance(raw_data, dict) and "Results" in raw_data:
            for result in raw_data.get("Results", []):
                fields = result.get("Fields", [])

                # Extract relevant fields
                event_id = NTSBService._extract_field_value(fields, "NtsbNo")
                event_date = NTSBService._extract_field_value(fields, "EventDate")
                event_type = NTSBService._extract_field_value(fields, "EventType")
                injury_level = NTSBService._extract_field_value(
                    fields, "HighestInjuryLevel"
                )
                city = NTSBService._extract_field_value(fields, "City")
                state = NTSBService._extract_field_value(fields, "State")
                country = NTSBService._extract_field_value(fields, "Country")

                # Build location string
                location_parts = [p for p in [city, state, country] if p]
                location = ", ".join(location_parts) if location_parts else None

                # Create incident object
                incident = NTSBIncident(
                    event_id=event_id,
                    event_date=event_date,
                    location=location,
                    aircraft_damage=None,  # Not in this response format
                    injury_level=injury_level,
                    investigation_type=None,  # Not directly available
                    event_type=event_type,
                )
                incidents.append(incident)

        return incidents

    @staticmethod
    def calculate_ntsb_score(incidents: List[NTSBIncident]) -> float:
        """
        Calculate NTSB score based on incident history.

        Args:
            incidents: List of NTSB incidents

        Returns:
            Score between 0-100 (100 being best, 0 being worst)
        """
        if not incidents:
            return 100.0  # Perfect score if no incidents

        # Simple scoring algorithm - can be enhanced later
        # Deduct points based on number and severity of incidents
        base_score = 100.0
        incident_count = len(incidents)

        # Deduct 5 points per incident
        score = base_score - (incident_count * 5)

        # Additional deductions for severe incidents
        for incident in incidents:
            if incident.aircraft_damage and incident.aircraft_damage.lower() in [
                "destroyed",
                "substantial",
            ]:
                score -= 10
            if incident.injury_level and incident.injury_level.lower() in [
                "fatal",
                "serious",
            ]:
                score -= 15

        # Ensure score doesn't go below 0
        return max(0.0, score)


class ScoringService:
    """Main service for operator scoring operations"""

    def __init__(self, db: Session):
        self.db = db
        self.ntsb_service = NTSBService()

    def get_operator_by_id(self, operator_id: UUID4) -> Operator:
        """
        Retrieve operator from database.

        Args:
            operator_id: UUID of the operator

        Returns:
            Operator model instance

        Raises:
            HTTPError: If operator not found
        """
        operator = (
            self.db.query(Operator).filter(Operator.operator_id == operator_id).first()
        )
        if not operator:
            raise HTTPError(detail=f"Operator with ID {operator_id} not found")
        return operator

    async def run_score_calculation(
        self, operator_id: UUID4
    ) -> ScoreCalculationResponse:
        """
        Run complete score calculation for an operator.

        Args:
            operator_id: UUID of the operator

        Returns:
            ScoreCalculationResponse with calculated score and incidents
        """
        # Get operator from database
        operator = self.get_operator_by_id(operator_id)

        # Query NTSB for incidents
        raw_ntsb_data = await self.ntsb_service.query_ntsb_incidents(operator.name)

        # Parse incidents
        incidents = self.ntsb_service.parse_ntsb_response(raw_ntsb_data)

        # Calculate score
        ntsb_score = self.ntsb_service.calculate_ntsb_score(incidents)

        # Return response
        return ScoreCalculationResponse(
            operator_id=operator.operator_id,
            operator_name=operator.name,
            ntsb_score=ntsb_score,
            total_incidents=len(incidents),
            incidents=incidents,
            calculated_at=datetime.utcnow(),
        )
