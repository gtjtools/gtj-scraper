"""
TrustScore Calculator Service with LLM Integration
Calculates TrustScore = 0.5 × FleetScore + 0.5 × TailScore
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class FleetScoreData:
    """Data required for FleetScore calculation"""

    operator_name: str
    operator_age_years: float
    ntsb_incidents: List[Dict[str, Any]]
    ucc_filings: List[Dict[str, Any]]
    argus_rating: Optional[str] = None
    wyvern_rating: Optional[str] = None
    bankruptcy_history: Optional[List[Dict[str, Any]]] = None
    faa_violations: Optional[List[Dict[str, Any]]] = None


@dataclass
class TailScoreData:
    """Data required for TailScore calculation"""

    aircraft_age_years: float
    operator_name: str
    registered_owner: str
    fractional_owner: bool
    ntsb_incidents: List[Dict[str, Any]]


@dataclass
class LLMRiskScore:
    """LLM-generated risk score result"""

    score: int  # 0-40
    reasoning: Optional[str] = None


class TrustScoreCalculator:
    """
    Main TrustScore calculation service
    TrustScore = 0.5 × FleetScore + 0.5 × TailScore
    """

    # Certification deduction tables
    ARGUS_DEDUCTIONS = {
        "Platinum Elite": 0,
        "Platinum": -2,
        "Gold Plus": -4,
        "Gold": -6,
        "None": -10,
    }

    WYVERN_DEDUCTIONS = {
        "Wingman PRO": -2,
        "Wingman": -4,
        "Registered Operator": -6,
        "None": -10,
    }

    # Aircraft age deductions
    AIRCRAFT_AGE_DEDUCTIONS = [
        (0, 2, -10),
        (2, 5, 0),
        (5, 8, -2),
        (8, 12, -4),
        (12, 16, -6),
        (16, 20, -8),
        (20, float("inf"), -10),
    ]

    # Injury level deductions
    INJURY_DEDUCTIONS = {
        "None": 0,
        "Minor": -10,
        "Serious": -20,
        "Fatal": -50,
    }

    def __init__(self, llm_client=None):
        """
        Initialize TrustScore Calculator

        Args:
            llm_client: Optional LLM client for risk scoring (e.g., OpenAI, Anthropic)
        """
        self.llm_client = llm_client

    async def calculate_trust_score(
        self, fleet_data: FleetScoreData, tail_data: TailScoreData
    ) -> Dict[str, Any]:
        """
        Calculate the complete TrustScore

        Args:
            fleet_data: Data for FleetScore calculation
            tail_data: Data for TailScore calculation

        Returns:
            Dictionary containing TrustScore, FleetScore, TailScore, and breakdowns
        """
        fleet_score, fleet_breakdown = await self.calculate_fleet_score(fleet_data)
        tail_score, tail_breakdown = self.calculate_tail_score(tail_data)

        trust_score = (0.5 * fleet_score) + (0.5 * tail_score)

        return {
            "trust_score": round(trust_score, 2),
            "fleet_score": round(fleet_score, 2),
            "tail_score": round(tail_score, 2),
            "fleet_breakdown": fleet_breakdown,
            "tail_breakdown": tail_breakdown,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def calculate_fleet_score(
        self, data: FleetScoreData
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate FleetScore (out of 100)

        Args:
            data: FleetScoreData object with all required information

        Returns:
            Tuple of (score, breakdown_dict)
        """
        initial_score = 100.0
        deductions = []

        # 1. LLM Financial Risk Score (0-40 points deduction)
        financial_risk = await self.calculate_financial_risk_score(
            ucc_filings=data.ucc_filings, bankruptcy_history=data.bankruptcy_history
        )
        initial_score -= financial_risk.score
        deductions.append(
            {
                "category": "Financial Risk (LLM)",
                "deduction": financial_risk.score,
                "reasoning": financial_risk.reasoning,
            }
        )

        # 2. LLM Legal Risk Score (0-40 points deduction)
        legal_risk = await self.calculate_legal_risk_score(
            ucc_filings=data.ucc_filings,
            bankruptcy_history=data.bankruptcy_history,
            ntsb_incidents=data.ntsb_incidents,
            faa_violations=data.faa_violations,
        )
        initial_score -= legal_risk.score
        deductions.append(
            {
                "category": "Legal Risk (LLM)",
                "deduction": legal_risk.score,
                "reasoning": legal_risk.reasoning,
            }
        )

        # 3. Age of Operator deduction: 2 × (Age - 10), minimum 0
        age_deduction = max(0, 2 * (data.operator_age_years - 10))
        initial_score -= age_deduction
        deductions.append(
            {
                "category": "Operator Age",
                "deduction": age_deduction,
                "details": f"Operator age: {data.operator_age_years} years",
            }
        )

        # 4. NTSB Accidents in last 5 years: 2 points each
        five_years_ago = datetime.now(timezone.utc) - timedelta(days=5 * 365)
        recent_accidents = [
            inc
            for inc in data.ntsb_incidents
            if inc.get("event_type", "").lower() == "accident"
            and self._parse_date(inc.get("event_date")) > five_years_ago
        ]
        accident_deduction = 2 * len(recent_accidents)
        initial_score -= accident_deduction
        deductions.append(
            {
                "category": "Recent NTSB Accidents",
                "deduction": accident_deduction,
                "details": f"{len(recent_accidents)} accidents in last 5 years",
            }
        )

        # 5. Certification deductions (ARGUS/WYVERN - use better of the two)
        cert_deduction = self._calculate_certification_deduction(
            data.argus_rating, data.wyvern_rating
        )
        initial_score += cert_deduction  # Note: cert_deduction is already negative
        deductions.append(
            {
                "category": "Certification Rating",
                "deduction": abs(cert_deduction),
                "details": f"ARGUS: {data.argus_rating or 'None'}, WYVERN: {data.wyvern_rating or 'None'}",
            }
        )

        # Ensure score doesn't fall below 0
        final_score = max(0.0, initial_score)

        breakdown = {
            "initial_score": 100.0,
            "final_score": final_score,
            "total_deductions": 100.0 - final_score,
            "deductions": deductions,
        }

        return final_score, breakdown

    def calculate_tail_score(self, data: TailScoreData) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate TailScore (out of 100)

        Args:
            data: TailScoreData object with all required information

        Returns:
            Tuple of (score, breakdown_dict)
        """
        initial_score = 100.0
        deductions = []

        # 1. Aircraft age deduction
        age_deduction = self._calculate_aircraft_age_deduction(data.aircraft_age_years)
        initial_score += age_deduction  # Note: age_deduction is already negative
        deductions.append(
            {
                "category": "Aircraft Age",
                "deduction": abs(age_deduction),
                "details": f"Aircraft age: {data.aircraft_age_years} years",
            }
        )

        # 2. Operator name vs Registered Owner mismatch: -10 points
        if data.operator_name.lower() != data.registered_owner.lower():
            initial_score -= 10
            deductions.append(
                {
                    "category": "Owner Mismatch",
                    "deduction": 10,
                    "details": f"Operator: {data.operator_name}, Owner: {data.registered_owner}",
                }
            )

        # 3. Fractional Owner: -5 points
        if data.fractional_owner:
            initial_score -= 5
            deductions.append(
                {
                    "category": "Fractional Ownership",
                    "deduction": 5,
                    "details": "Aircraft is fractionally owned",
                }
            )

        # 4. NTSB Incident deductions
        incident_deductions = self._calculate_ntsb_incident_deductions(
            data.ntsb_incidents
        )
        for inc_deduction in incident_deductions:
            initial_score -= inc_deduction["deduction"]
            deductions.append(inc_deduction)

        # Ensure score doesn't fall below 0
        final_score = max(0.0, initial_score)

        breakdown = {
            "initial_score": 100.0,
            "final_score": final_score,
            "total_deductions": 100.0 - final_score,
            "deductions": deductions,
        }

        return final_score, breakdown

    async def calculate_financial_risk_score(
        self,
        ucc_filings: List[Dict[str, Any]],
        bankruptcy_history: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMRiskScore:
        """
        Calculate financial risk score using LLM (0-40 points)

        Args:
            ucc_filings: List of UCC filing records
            bankruptcy_history: Optional list of bankruptcy records

        Returns:
            LLMRiskScore with score (0-40) and optional reasoning
        """
        if not self.llm_client:
            # Return default score if no LLM client configured
            return LLMRiskScore(
                score=0, reasoning="No LLM client configured - using default score"
            )

        prompt = self._build_financial_risk_prompt(ucc_filings, bankruptcy_history)

        try:
            # Call LLM (implementation depends on client)
            score, reasoning = await self._call_llm_for_scoring(prompt)
            return LLMRiskScore(score=score, reasoning=reasoning)
        except Exception as e:
            print(f"⚠️  Error calling LLM for financial risk scoring: {e}")
            return LLMRiskScore(score=0, reasoning=f"Error: {str(e)}")

    async def calculate_legal_risk_score(
        self,
        ucc_filings: List[Dict[str, Any]],
        bankruptcy_history: Optional[List[Dict[str, Any]]],
        ntsb_incidents: List[Dict[str, Any]],
        faa_violations: Optional[List[Dict[str, Any]]],
    ) -> LLMRiskScore:
        """
        Calculate legal risk score using LLM (0-40 points)

        Args:
            ucc_filings: List of UCC filing records
            bankruptcy_history: Optional list of bankruptcy records
            ntsb_incidents: List of NTSB incidents
            faa_violations: Optional list of FAA violations

        Returns:
            LLMRiskScore with score (0-40) and optional reasoning
        """
        if not self.llm_client:
            # Return default score if no LLM client configured
            return LLMRiskScore(
                score=0, reasoning="No LLM client configured - using default score"
            )

        prompt = self._build_legal_risk_prompt(
            ucc_filings, bankruptcy_history, ntsb_incidents, faa_violations
        )

        try:
            # Call LLM (implementation depends on client)
            score, reasoning = await self._call_llm_for_scoring(prompt)
            return LLMRiskScore(score=score, reasoning=reasoning)
        except Exception as e:
            print(f"⚠️  Error calling LLM for legal risk scoring: {e}")
            return LLMRiskScore(score=0, reasoning=f"Error: {str(e)}")

    def _build_financial_risk_prompt(
        self,
        ucc_filings: List[Dict[str, Any]],
        bankruptcy_history: Optional[List[Dict[str, Any]]],
    ) -> str:
        """Build the financial risk assessment prompt for LLM"""
        prompt = """You are a financial risk analyst specializing in the aviation industry. Your task is to provide a financial risk score for an aircraft operator based on the provided data. The score you provide will be deducted from a starting score of 100, so a higher risk score from you means a lower final score for the operator. Your output must be a single integer between 0 and 40. 0 signifies no identifiable financial risk. 40 signifies the highest level of financial risk.

Analysis Instructions:
1. Review all the provided information.
2. Assess the operator's financial stability based on active UCC filings, any history of bankruptcy, and liens against the operator. Consider the quality of the debtors, considering the reputation of lending institutions used as debtors, the frequency of filings, and the likelihood that the company may be struggling with its debt.
3. Consider inactive and lapsed UCC filings as evidence of payment history. Treat these results as historical data that provide evidence as to the operator's history with paying its debts and its potential for maintaining good financial standing in the future.
4. Synthesize your findings into a single risk score between 0 and 40. Provide only the integer score as your output.

Here is the data for your evaluation. Assume that this data is comprehensive and complete.

"""

        # Add UCC filings data
        prompt += "\n=== UCC FILINGS ===\n"
        if ucc_filings:
            for i, filing in enumerate(ucc_filings, 1):
                # Validate required fields (all except secured_party and collateral)
                required_fields = ['file_number', 'status', 'filing_date', 'lapse_date', 'lien_type', 'debtor']
                missing_fields = []

                for field in required_fields:
                    value = filing.get(field, 'Unknown')
                    if not value or value == 'Unknown':
                        missing_fields.append(field)

                if missing_fields:
                    print(f"⚠️  WARNING: UCC filing {i} is missing required fields: {', '.join(missing_fields)}")

                prompt += f"\nFiling {i}:\n"
                prompt += f"  File Number: {filing.get('file_number', 'Unknown')}\n"
                prompt += f"  Status: {filing.get('status', 'Unknown')}\n"
                prompt += f"  Filing Date: {filing.get('filing_date', 'Unknown')}\n"
                prompt += f"  Lapse Date: {filing.get('lapse_date', 'Unknown')}\n"
                prompt += f"  Lien Type: {filing.get('lien_type', 'Unknown')}\n"
                prompt += f"  Debtor: {filing.get('debtor', 'Unknown')}\n"
                prompt += f"  Secured Party: {filing.get('secured_party', 'Not specified')}\n"
                prompt += f"  Collateral: {filing.get('collateral', 'Not specified')}\n"
        else:
            prompt += "No UCC filings found.\n"

        # Add bankruptcy history
        prompt += "\n=== BANKRUPTCY HISTORY ===\n"
        if bankruptcy_history:
            for i, record in enumerate(bankruptcy_history, 1):
                prompt += f"\nBankruptcy {i}:\n"
                prompt += f"  Date: {record.get('date', 'Unknown')}\n"
                prompt += f"  Type: {record.get('type', 'Unknown')}\n"
                prompt += f"  Status: {record.get('status', 'Unknown')}\n"
        else:
            prompt += "No bankruptcy history found.\n"

        return prompt

    def _build_legal_risk_prompt(
        self,
        ucc_filings: List[Dict[str, Any]],
        bankruptcy_history: Optional[List[Dict[str, Any]]],
        ntsb_incidents: List[Dict[str, Any]],
        faa_violations: Optional[List[Dict[str, Any]]],
    ) -> str:
        """Build the legal risk assessment prompt for LLM"""
        prompt = """You are a legal risk analyst with expertise in the aviation sector. Your role is to evaluate the legal risk associated with an aircraft operator based on the information provided below. The score you generate will be subtracted from a base score of 100. Your output must be a single integer between 0 and 40. 0 signifies no identifiable legal risk. 40 signifies the highest level of legal risk.

Analysis Instructions:
1. Review all the provided information.
2. Assess the operator's legal standing based on active UCC filings, any history of bankruptcy, NTSB filings, and any potential legal trouble associated with them, and FAA violations and any legal trouble that might be considered there. Do not consider financial or operational risks, only legal risks should be considered. The age of each report should also be considered in terms of how it affects the current risk of doing business with this operator.
3. Evaluate the severity and frequency of any legal issues found. For example, the possibility of a single, minor lawsuit is less of a risk than multiple, serious FAA enforcement actions.
4. Formulate a comprehensive legal risk assessment.
5. Translate your assessment into a single integer score between 0 and 40. Your output should be only the integer.

Here is the data for your evaluation. Assume that this data is comprehensive and complete.

"""

        # Add UCC filings data
        prompt += "\n=== UCC FILINGS ===\n"
        if ucc_filings:
            for i, filing in enumerate(ucc_filings, 1):
                # Validate required fields (all except secured_party and collateral)
                required_fields = ['file_number', 'status', 'filing_date', 'lapse_date', 'lien_type', 'debtor']
                missing_fields = []

                for field in required_fields:
                    value = filing.get(field, 'Unknown')
                    if not value or value == 'Unknown':
                        missing_fields.append(field)

                if missing_fields:
                    print(f"⚠️  WARNING: UCC filing {i} is missing required fields: {', '.join(missing_fields)}")

                prompt += f"\nFiling {i}:\n"
                prompt += f"  File Number: {filing.get('file_number', 'Unknown')}\n"
                prompt += f"  Status: {filing.get('status', 'Unknown')}\n"
                prompt += f"  Filing Date: {filing.get('filing_date', 'Unknown')}\n"
                prompt += f"  Lapse Date: {filing.get('lapse_date', 'Unknown')}\n"
                prompt += f"  Lien Type: {filing.get('lien_type', 'Unknown')}\n"
                prompt += f"  Debtor: {filing.get('debtor', 'Unknown')}\n"
                prompt += f"  Secured Party: {filing.get('secured_party', 'Not specified')}\n"
        else:
            prompt += "No UCC filings found.\n"

        # Add bankruptcy history
        prompt += "\n=== BANKRUPTCY HISTORY ===\n"
        if bankruptcy_history:
            for i, record in enumerate(bankruptcy_history, 1):
                prompt += f"\nBankruptcy {i}:\n"
                prompt += f"  Date: {record.get('date', 'Unknown')}\n"
                prompt += f"  Type: {record.get('type', 'Unknown')}\n"
                prompt += f"  Status: {record.get('status', 'Unknown')}\n"
        else:
            prompt += "No bankruptcy history found.\n"

        # Add NTSB incidents
        prompt += "\n=== NTSB INCIDENTS ===\n"
        if ntsb_incidents:
            for i, incident in enumerate(ntsb_incidents, 1):
                prompt += f"\nIncident {i}:\n"
                prompt += f"  Event ID: {incident.get('event_id', 'Unknown')}\n"
                prompt += f"  Date: {incident.get('event_date', 'Unknown')}\n"
                prompt += f"  Type: {incident.get('event_type', 'Unknown')}\n"
                prompt += f"  Injury Level: {incident.get('injury_level', 'Unknown')}\n"
                prompt += f"  Location: {incident.get('location', 'Unknown')}\n"
        else:
            prompt += "No NTSB incidents found.\n"

        # Add FAA violations
        prompt += "\n=== FAA VIOLATIONS ===\n"
        if faa_violations:
            for i, violation in enumerate(faa_violations, 1):
                prompt += f"\nViolation {i}:\n"
                prompt += f"  Date: {violation.get('date', 'Unknown')}\n"
                prompt += f"  Type: {violation.get('type', 'Unknown')}\n"
                prompt += f"  Severity: {violation.get('severity', 'Unknown')}\n"
                prompt += f"  Status: {violation.get('status', 'Unknown')}\n"
        else:
            prompt += "No FAA violations found.\n"

        return prompt

    async def _call_llm_for_scoring(self, prompt: str) -> Tuple[int, str]:
        """
        Call LLM to get risk score

        Args:
            prompt: The complete prompt for LLM

        Returns:
            Tuple of (score, reasoning)
        """
        if not self.llm_client:
            return (0, "No LLM client configured")

        try:
            score, reasoning = await self.llm_client.get_risk_score(prompt)
            return (score, reasoning)
        except Exception as e:
            print(f"⚠️  Error in LLM scoring: {e}")
            return (0, f"Error: {str(e)}")

    def _calculate_certification_deduction(
        self, argus_rating: Optional[str], wyvern_rating: Optional[str]
    ) -> int:
        """
        Calculate certification deduction based on ARGUS and WYVERN ratings
        Returns the better (less negative) of the two
        """
        argus_deduction = self.ARGUS_DEDUCTIONS.get(argus_rating or "None", -10)
        wyvern_deduction = self.WYVERN_DEDUCTIONS.get(wyvern_rating or "None", -10)

        # Return the better score (less negative = better)
        return max(argus_deduction, wyvern_deduction)

    def _calculate_aircraft_age_deduction(self, age_years: float) -> int:
        """Calculate deduction based on aircraft age"""
        for min_age, max_age, deduction in self.AIRCRAFT_AGE_DEDUCTIONS:
            if min_age <= age_years < max_age:
                return deduction
        return -10  # Default for very old aircraft

    def _calculate_ntsb_incident_deductions(
        self, incidents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Calculate deductions for NTSB incidents

        Rules:
        - Multiply all values by 2 if event_type = "Accident"
        - Deduct 2 × (Age of Event in Years - 10), minimum 0
        - Deduct points based on injury level
        """
        deductions = []
        current_date = datetime.now(timezone.utc)

        for incident in incidents:
            event_type = incident.get("event_type", "").lower()
            is_accident = event_type == "accident"
            multiplier = 2 if is_accident else 1

            # Calculate age deduction
            event_date = self._parse_date(incident.get("event_date"))
            if event_date:
                age_years = (current_date - event_date).days / 365.25
                age_deduction = max(0, 2 * (age_years - 10))
            else:
                age_deduction = 0

            # Calculate injury deduction
            injury_level = incident.get("injury_level", "None")
            injury_deduction = abs(self.INJURY_DEDUCTIONS.get(injury_level, 0))

            # Apply multiplier
            total_deduction = (age_deduction + injury_deduction) * multiplier

            if total_deduction > 0:
                deductions.append(
                    {
                        "category": f"NTSB Incident - {incident.get('event_id', 'Unknown')}",
                        "deduction": total_deduction,
                        "details": f"Type: {event_type}, Injury: {injury_level}, Age: {age_years:.1f} years",
                    }
                )

        return deductions

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to timezone-aware datetime object"""
        if not date_str:
            return None

        try:
            # Try ISO format first
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            try:
                # Try common date formats and make timezone-aware
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                return None
