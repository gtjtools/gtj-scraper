"""
TrustScore Calculator Service - Algorithm v3 Refined2
Calculates TrustScore = 50 + (0.5 * (0.6*OS + 0.4*TS)) * CS
FleetScore = 50 + (0.5 * OS * CS)
where:
  OS (Operator Score) = 100 - ORF + FSF - CSF
  TS (Tail Score) = 100 - MRT + OST - 5*IHT
  CS = Confidence Score

Score Tiers:
  90+ : Pinnacle
  80+ : Premier
  70+ : Benchmark
  <70 : Standard

NOTE: CSF uses INVERSE scoring - better certifications have LOWER values
  - Platinum Elite (ARGUS) = 0 points (best, no penalty)
  - None = 10 points (worst, maximum penalty)
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class FleetScoreData:
    """Data required for FleetScore calculation (Algorithm v3)"""

    operator_name: str
    operator_age_years: float  # Years since business registration
    fleet_size: int  # Total number of tails in operator's fleet
    fleet_events: List[Dict[str, Any]]  # All events across the fleet (NTSB, FAA)
    ucc_filings: List[Dict[str, Any]]  # UCC filings with status, dates
    argus_rating: Optional[str] = None
    wyvern_rating: Optional[str] = None
    bankruptcy_history: Optional[List[Dict[str, Any]]] = None


@dataclass
class TailScoreData:
    """Data required for TailScore calculation (Algorithm v3)"""

    aircraft_age_years: float  # Years since tail registration
    operator_name: str
    registered_owner: str
    tail_events: List[Dict[str, Any]]  # Events specific to this tail
    fractional_owner: bool  # True if fractional/partial ownership


class TrustScoreCalculator:
    """
    Main TrustScore calculation service - Algorithm v3 Refined2
    TrustScore = 50 + (0.5 * (0.6*OS + 0.4*TS)) * CS
    FleetScore = 50 + (0.5 * OS * CS)
    where:
      OS (Operator Score) = 100 - ORF + FSF - CSF
      TS (Tail Score) = 100 - MRT + OST - 5*IHT
      CS = Confidence Score

    Score Tiers:
      90+ : Pinnacle
      80+ : Premier
      70+ : Benchmark
      <70 : Standard

    NOTE: CSF uses INVERSE scoring (better cert = lower penalty)
    """

    # Certification penalty points (CSF Component)
    # INVERSE SCORING: Better certifications = LOWER values = LESS penalty
    # These values are SUBTRACTED from the Operator Score
    ARGUS_POINTS = {
        "Platinum Elite": 0,   # Best - no penalty
        "Platinum": 2,
        "Gold Plus": 4,
        "Gold": 6,
        "None": 10,           # Worst - maximum penalty
    }

    WYVERN_POINTS = {
        "Wingman PRO": 2,      # Equivalent to ARGUS Platinum
        "Wingman": 4,          # Equivalent to ARGUS Gold Plus
        "Registered Operator": 6,  # Equivalent to ARGUS Gold
        "None": 10,           # Worst - maximum penalty
    }

    # Time decay constant: k = ln(2) / 5
    TIME_DECAY_K = math.log(2) / 5

    # Score Tiers (Algorithm v3 Refined2)
    SCORE_TIERS = {
        "Pinnacle": 90,   # 90+
        "Premier": 80,    # 80+
        "Benchmark": 70,  # 70+
        "Standard": 0,    # <70
    }

    @staticmethod
    def get_score_tier(score: float) -> str:
        """
        Get the score tier based on the trust score.

        Args:
            score: The trust score (0-100)

        Returns:
            Tier name: "Pinnacle", "Premier", "Benchmark", or "Standard"
        """
        if score >= 90:
            return "Pinnacle"
        elif score >= 80:
            return "Premier"
        elif score >= 70:
            return "Benchmark"
        else:
            return "Standard"

    def __init__(self, llm_client=None):
        """
        Initialize TrustScore Calculator v3

        Args:
            llm_client: Optional LLM client for generating explanations and insights
        """
        self.llm_client = llm_client

    def calculate_confidence_score(self, operator_age_years: float) -> float:
        """
        Calculate Confidence Score (CS) - Algorithm v3 Refined
        CS = 1 - e^(-0.384y) where y = Years Since Operator Business Registration

        This penalizes youth and rewards experience, ensuring new operators
        cannot achieve scores near 100.

        Args:
            operator_age_years: Years since operator business registration

        Returns:
            Confidence score between 0 and 1
        """
        return 1 - math.exp(-0.384 * operator_age_years)

    async def calculate_trust_score(
        self, fleet_data: FleetScoreData, tail_data: TailScoreData
    ) -> Dict[str, Any]:
        """
        Calculate the complete TrustScore (Algorithm v3 - Refined2)
        TrustScore = 50 + (0.5 * (0.6*OS + 0.4*TS)) * CS
        FleetScore = 50 + (0.5 * OS * CS)

        Args:
            fleet_data: Data for FleetScore calculation
            tail_data: Data for TailScore calculation

        Returns:
            Dictionary containing TrustScore, FleetScore, TailScore, and breakdowns
        """
        operator_score, fleet_breakdown = await self.calculate_fleet_score(fleet_data)
        tail_score, tail_breakdown = await self.calculate_tail_score(tail_data)
        confidence_score = self.calculate_confidence_score(fleet_data.operator_age_years)

        # TrustScore = 50 + (0.5 * (0.6*OS + 0.4*TS)) * CS
        raw_combined = 0.6 * operator_score + 0.4 * tail_score
        trust_score = 50 + (0.5 * raw_combined) * confidence_score

        # FleetScore = 50 + (0.5 * OS * CS)
        fleet_score = 50 + (0.5 * operator_score * confidence_score)

        # Generate AI insights if LLM client is available
        ai_insights = None
        if self.llm_client:
            ai_insights = await self._generate_overall_insights(
                fleet_data, tail_data, trust_score, fleet_score, tail_score,
                confidence_score, fleet_breakdown, tail_breakdown
            )

        # Determine score tier
        score_tier = self.get_score_tier(trust_score)

        result = {
            "trust_score": round(trust_score, 2),
            "score_tier": score_tier,
            "fleet_score": round(fleet_score, 2),
            "operator_score": round(operator_score, 2),
            "tail_score": round(tail_score, 2),
            "confidence_score": round(confidence_score, 4),
            "raw_combined_score": round(raw_combined, 2),
            "fleet_breakdown": fleet_breakdown,
            "tail_breakdown": tail_breakdown,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

        if ai_insights:
            result["ai_insights"] = ai_insights

        return result

    async def calculate_fleet_score(
        self, data: FleetScoreData
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate FleetScore (out of 100) - Algorithm v3 Refined
        OS = 100 - ORF + FSF - CSF

        NOTE: CSF uses INVERSE scoring:
        - Better certifications = LOWER CSF value = LESS penalty = HIGHER score
        - No certification = CSF of 10 = maximum penalty = LOWER score

        Args:
            data: FleetScoreData object with all required information

        Returns:
            Tuple of (score, breakdown_dict)
        """
        components = {}

        # Component 1: Fleet Operational Risk (ORF)
        orf = self._calculate_fleet_operational_risk(
            data.fleet_events, data.fleet_size, data.operator_age_years
        )
        components["ORF"] = {
            "value": round(orf, 2),
            "description": "Fleet Operational Risk - higher values indicate more risk from incidents and accidents"
        }

        # Component 2: Fleet Financial Score (FSF)
        fsf = self._calculate_fleet_financial_score(
            data.ucc_filings, data.bankruptcy_history
        )
        components["FSF"] = {
            "value": round(fsf, 2),
            "description": "Fleet Financial Score - positive values indicate good financial standing, negative indicates risk"
        }

        # Component 3: Fleet Certification Status (CSF)
        csf = self._calculate_fleet_certification_score(
            data.argus_rating, data.wyvern_rating
        )
        cert_desc = f"{data.argus_rating or 'None'} ARGUS, {data.wyvern_rating or 'None'} WYVERN"
        components["CSF"] = {
            "value": csf,
            "description": f"Fleet Certification Penalty - {cert_desc} (lower is better, 0=best, 10=worst)"
        }

        # OS = 100 - ORF + FSF - CSF (CSF is SUBTRACTED as penalty)
        fleet_score = 100 - orf + fsf - csf

        # Clamp score between 0 and 100
        fleet_score = max(0.0, min(100.0, fleet_score))

        # Generate AI explanation if available
        explanation = None
        if self.llm_client:
            explanation = await self._generate_fleet_explanation(
                data, orf, fsf, csf, fleet_score
            )

        breakdown = {
            "final_score": round(fleet_score, 2),
            "components": components,
            "formula": "100 - ORF + FSF - CSF",
        }

        if explanation:
            breakdown["explanation"] = explanation

        return fleet_score, breakdown

    async def calculate_tail_score(self, data: TailScoreData) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate TailScore (out of 100) - Algorithm v3
        TS = 100 - MRT + OST - 5*IHT

        Args:
            data: TailScoreData object with all required information

        Returns:
            Tuple of (score, breakdown_dict)
        """
        components = {}

        # Component 4: Tail Maintenance Risk (MRT)
        mrt = self._calculate_tail_maintenance_risk(data.aircraft_age_years)
        components["MRT"] = {
            "value": round(mrt, 2),
            "description": f"Tail Maintenance Risk - aircraft age is {data.aircraft_age_years:.1f} years (ideal: 2-5 years)"
        }

        # Component 5: Tail Ownership Status (OST)
        ost = self._calculate_tail_ownership_status(
            data.operator_name, data.registered_owner, data.fractional_owner
        )
        ownership_desc = "full ownership" if ost == 10 else ("fractional ownership" if ost == 5 else "no ownership")
        components["OST"] = {
            "value": ost,
            "description": f"Tail Ownership Status - operator has {ownership_desc}"
        }

        # Component 6: Tail Incident History (IHT)
        iht = self._calculate_tail_incident_history(data.tail_events)
        components["IHT"] = {
            "value": round(iht, 2),
            "description": f"Tail Incident History - {len(data.tail_events)} incident(s) found for this aircraft"
        }

        # TS = 100 - MRT + OST - 5*IHT
        tail_score = 100 - mrt + ost - (5 * iht)

        # Clamp score between 0 and 100
        tail_score = max(0.0, min(100.0, tail_score))

        # Generate AI explanation if available
        explanation = None
        if self.llm_client:
            explanation = await self._generate_tail_explanation(
                data, mrt, ost, iht, tail_score
            )

        breakdown = {
            "final_score": round(tail_score, 2),
            "components": components,
            "formula": "100 - MRT + OST - 5*IHT",
        }

        if explanation:
            breakdown["explanation"] = explanation

        return tail_score, breakdown

    def _calculate_fleet_operational_risk(
        self, fleet_events: List[Dict[str, Any]], fleet_size: int, operator_age_years: float
    ) -> float:
        """
        Calculate Fleet Operational Risk (ORF)

        ORF = ∑ ((Severity / VF) * e^(-k*Δt))

        where:
        - k = ln(2) / 5
        - Δt = Time in years since the event
        - VF = Total Tails in Operator's Fleet * ln(Years Since Business Registration + 1)

        Args:
            fleet_events: List of all fleet events
            fleet_size: Total number of tails in fleet
            operator_age_years: Years since business registration

        Returns:
            Operational risk score
        """
        if not fleet_events:
            return 0.0

        # Calculate VF (Volatility Factor)
        vf = fleet_size * math.log(operator_age_years + 1)

        # Avoid division by zero
        if vf == 0:
            vf = 1

        current_date = datetime.now(timezone.utc)
        total_risk = 0.0

        for event in fleet_events:
            # Get severity
            severity = self._get_event_severity(event)

            # Get time since event
            event_date = self._parse_date(event.get("event_date"))
            if event_date:
                delta_t = (current_date - event_date).days / 365.25

                # Calculate time decay
                time_decay = math.exp(-self.TIME_DECAY_K * delta_t)

                # Add to total risk
                total_risk += (severity / vf) * time_decay

        return total_risk

    def _calculate_fleet_financial_score(
        self, ucc_filings: List[Dict[str, Any]], bankruptcy_history: Optional[List[Dict[str, Any]]]
    ) -> float:
        """
        Calculate Fleet Financial Score (FSF) - Algorithm v3 Refined

        If active Chapter 11/7 bankruptcy or filed within last 5 years: FSF = 0
        If no UCC data is available: FSF = 5

        Otherwise:
        FSF = ∑(e^(-0.15*Δr)) - ∑(5 * e^(-0.15*Δf))

        where:
        - Δr = time in years since resolution (for resolved liens)
        - Δf = time in years since filing (for unresolved liens)

        Args:
            ucc_filings: List of UCC filings
            bankruptcy_history: Optional list of bankruptcy records

        Returns:
            Financial score
        """
        # Check for recent bankruptcy
        if bankruptcy_history:
            five_years_ago = datetime.now(timezone.utc) - timedelta(days=5 * 365)
            for record in bankruptcy_history:
                status = (record.get("status") or "").lower()
                record_date = self._parse_date(record.get("date"))

                # If active or filed within last 5 years
                if status == "active" or (record_date and record_date > five_years_ago):
                    return 0.0

        # If no UCC data is available, return default score of 5
        if not ucc_filings:
            return 5.0

        current_date = datetime.now(timezone.utc)
        five_years_ago = current_date - timedelta(days=5 * 365)

        resolved_score = 0.0
        unresolved_penalty = 0.0

        for filing in ucc_filings:
            filing_date = self._parse_date(filing.get("filing_date"))

            # Only consider filings within last 5 years
            if not filing_date or filing_date < five_years_ago:
                continue

            status = (filing.get("status") or "").lower()

            # Check if resolved (satisfied, released, terminated)
            is_resolved = any(keyword in status for keyword in ["satisfied", "released", "terminated", "lapsed"])

            if is_resolved:
                # For resolved liens, use resolution date (lapse_date)
                resolution_date = self._parse_date(filing.get("lapse_date")) or filing_date
                delta_r = (current_date - resolution_date).days / 365.25
                resolved_score += math.exp(-0.15 * delta_r)
            else:
                # For unresolved liens
                delta_f = (current_date - filing_date).days / 365.25
                unresolved_penalty += 5 * math.exp(-0.15 * delta_f)

        return resolved_score - unresolved_penalty

    def _calculate_fleet_certification_score(
        self, argus_rating: Optional[str], wyvern_rating: Optional[str]
    ) -> int:
        """
        Calculate Fleet Certification Status (CSF)

        INVERSE SCORING: Better certifications have LOWER penalty values
        - Platinum Elite = 0 (no penalty, best score)
        - None = 10 (maximum penalty, worst score)

        Returns the MINIMUM penalty from ARGUS or WYVERN ratings
        (operator gets credit for their best certification)

        Args:
            argus_rating: ARGUS rating (e.g., "Platinum Elite", "No", "None")
            wyvern_rating: WYVERN rating (e.g., "Wingman PRO", "No", "None")

        Returns:
            Certification penalty points (0-10, lower is better)
        """
        # Default to maximum penalty (no certification)
        argus_points = 10
        wyvern_points = 10

        # Handle ARGUS rating
        if argus_rating:
            # Normalize "No" to "None"
            if argus_rating.lower() in ["no", ""]:
                argus_rating = "None"

            # Try exact match first
            if argus_rating in self.ARGUS_POINTS:
                argus_points = self.ARGUS_POINTS[argus_rating]
            else:
                # Try case-insensitive match
                argus_lower = argus_rating.lower()
                for key, value in self.ARGUS_POINTS.items():
                    if key.lower() == argus_lower:
                        argus_points = value
                        break

        # Handle WYVERN rating
        if wyvern_rating:
            # Normalize "No" to "None"
            if wyvern_rating.lower() in ["no", ""]:
                wyvern_rating = "None"

            # Try exact match first
            if wyvern_rating in self.WYVERN_POINTS:
                wyvern_points = self.WYVERN_POINTS[wyvern_rating]
            else:
                # Try case-insensitive and partial match
                wyvern_lower = wyvern_rating.lower()
                for key, value in self.WYVERN_POINTS.items():
                    if key.lower() == wyvern_lower or wyvern_lower in key.lower():
                        wyvern_points = value
                        break

        # Return the MINIMUM penalty (operators get credit for their BEST certification)
        return min(argus_points, wyvern_points)

    def _calculate_tail_maintenance_risk(self, aircraft_age_years: float) -> float:
        """
        Calculate Tail Maintenance Risk (MRT)

        MRT = 2 * (4.15 * e^(-2x) + 100 * (max(0, x-5)/25)^1.5)

        where x = Years Since Tail Registration Date

        The ideal tail age is 2-5 years, with penalties for both very new and old aircraft.

        Args:
            aircraft_age_years: Years since tail registration

        Returns:
            Maintenance risk score
        """
        x = aircraft_age_years

        # First term: penalty for new aircraft
        new_penalty = 4.15 * math.exp(-2 * x)

        # Second term: penalty for old aircraft
        old_penalty = 100 * (max(0, x - 5) / 25) ** 1.5

        mrt = 2 * (new_penalty + old_penalty)

        return mrt

    def _calculate_tail_ownership_status(
        self, operator_name: str, registered_owner: str, fractional_owner: bool
    ) -> int:
        """
        Calculate Tail Ownership Status (OST)

        - Full exclusive ownership: 10 points
        - Fractional/partial ownership: 5 points
        - No ownership: 0 points

        Args:
            operator_name: Name of the operator
            registered_owner: Name of the registered owner
            fractional_owner: Whether it's a fractional ownership

        Returns:
            Ownership status points (0, 5, or 10)
        """
        # Check if operator owns the tail
        # Handle None values defensively
        if not operator_name or not registered_owner:
            return 0

        operator_owns = operator_name.lower() in registered_owner.lower()

        if operator_owns and not fractional_owner:
            return 10
        elif operator_owns and fractional_owner:
            return 5
        else:
            return 0

    def _calculate_tail_incident_history(self, tail_events: List[Dict[str, Any]]) -> float:
        """
        Calculate Tail Incident History (IHT)

        IHT = ∑ (Severity * e^(-k*Δt))

        where:
        - k = ln(2) / 5
        - Δt = Time in years since the event

        Args:
            tail_events: List of events specific to this tail

        Returns:
            Incident history score
        """
        if not tail_events:
            return 0.0

        current_date = datetime.now(timezone.utc)
        total_risk = 0.0

        for event in tail_events:
            # Get severity
            severity = self._get_event_severity(event)

            # Get time since event
            event_date = self._parse_date(event.get("event_date"))
            if event_date:
                delta_t = (current_date - event_date).days / 365.25

                # Calculate time decay
                time_decay = math.exp(-self.TIME_DECAY_K * delta_t)

                # Add to total risk
                total_risk += severity * time_decay

        return total_risk

    def _get_event_severity(self, event: Dict[str, Any]) -> float:
        """
        Get severity score for an event based on type and injury level

        Severity values:
        - Fatal Accident: 50
        - Non-Fatal Accident: 25
        - Serious Incident: 15
        - Major FAA Enforcement Action: 10
        - Minor Incident/Enforcement: 5

        Args:
            event: Event dictionary containing event_type and injury_level

        Returns:
            Severity score
        """
        # Handle None values by using 'or ""' to ensure we have a string
        event_type = (event.get("event_type") or "").lower()
        injury_level = (event.get("injury_level") or "").lower()
        severity = (event.get("severity") or "").lower()

        # Determine severity based on event type and injury level
        if "accident" in event_type:
            if "fatal" in injury_level:
                return 50
            else:
                return 25
        elif "serious" in event_type or "serious" in injury_level:
            return 15
        elif "major" in event_type or "major" in severity:
            return 10
        else:
            return 5

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """
        Parse date string to timezone-aware datetime object

        Args:
            date_str: Date string in various formats

        Returns:
            Timezone-aware datetime object or None
        """
        if not date_str:
            return None

        try:
            # Try ISO format with timezone first
            if "T" in str(date_str):
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                # Simple YYYY-MM-DD format
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError, TypeError):
            try:
                # Last resort: try ISO format
                return datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
            except (ValueError, AttributeError, TypeError):
                return None

    async def _generate_fleet_explanation(
        self, data: FleetScoreData, orf: float, fsf: float, csf: int, fleet_score: float
    ) -> str:
        """Generate AI explanation for FleetScore components"""
        if not self.llm_client:
            return None

        prompt = f"""You are an aviation safety analyst. Provide a clear, professional explanation of why this operator received their Fleet Score.

Operator: {data.operator_name}
Operator Age: {data.operator_age_years:.1f} years
Fleet Size: {data.fleet_size} aircraft
Fleet Score: {fleet_score:.2f}/100

Components:
- Operational Risk (ORF): {orf:.2f} - Events across fleet with time decay
- Financial Score (FSF): {fsf:.2f} - Based on UCC filings and bankruptcy history
- Certification Score (CSF): {csf} - ARGUS: {data.argus_rating or 'None'}, WYVERN: {data.wyvern_rating or 'None'}

Fleet Events: {len(data.fleet_events)} total
UCC Filings: {len(data.ucc_filings)} total
Bankruptcy History: {'Yes' if data.bankruptcy_history else 'None'}

Provide a 2-3 sentence explanation of:
1. What are the main factors affecting this score?
2. Are there any concerning patterns or positive indicators?
3. What does this score mean for operator reliability?

Keep it concise and focused on actionable insights."""

        try:
            response = await self.llm_client.get_completion(prompt)
            return response
        except Exception as e:
            print(f"⚠️  Error generating fleet explanation: {e}")
            return None

    async def _generate_tail_explanation(
        self, data: TailScoreData, mrt: float, ost: int, iht: float, tail_score: float
    ) -> str:
        """Generate AI explanation for TailScore components"""
        if not self.llm_client:
            return None

        prompt = f"""You are an aviation safety analyst. Provide a clear, professional explanation of why this aircraft received its Tail Score.

Aircraft Age: {data.aircraft_age_years:.1f} years
Operator: {data.operator_name}
Registered Owner: {data.registered_owner}
Tail Score: {tail_score:.2f}/100

Components:
- Maintenance Risk (MRT): {mrt:.2f} - Based on aircraft age (ideal: 2-5 years)
- Ownership Status (OST): {ost} - {'Full ownership' if ost == 10 else ('Fractional' if ost == 5 else 'No ownership')}
- Incident History (IHT): {iht:.2f} - Tail-specific incidents

Tail Events: {len(data.tail_events)} incident(s) found

Provide a 2-3 sentence explanation of:
1. What are the main factors affecting this score?
2. Is the aircraft age appropriate, and how does ownership impact the score?
3. What does this score indicate about this specific aircraft's reliability?

Keep it concise and focused on actionable insights."""

        try:
            response = await self.llm_client.get_completion(prompt)
            return response
        except Exception as e:
            print(f"⚠️  Error generating tail explanation: {e}")
            return None

    async def _generate_overall_insights(
        self,
        fleet_data: FleetScoreData,
        tail_data: TailScoreData,
        trust_score: float,
        fleet_score: float,
        tail_score: float,
        confidence_score: float,
        fleet_breakdown: Dict[str, Any],
        tail_breakdown: Dict[str, Any]
    ) -> str:
        """Generate overall AI insights about the TrustScore"""
        if not self.llm_client:
            return None

        prompt = f"""You are an aviation safety analyst providing executive summary insights for a TrustScore assessment.

OVERALL RESULTS:
TrustScore: {trust_score:.2f}/100
Raw Score: {(0.6 * fleet_score + 0.4 * tail_score):.2f}/100
Confidence Score: {confidence_score:.4f} (based on {fleet_data.operator_age_years:.1f} years in business)

Fleet Score: {fleet_score:.2f}/100
Tail Score: {tail_score:.2f}/100

OPERATOR PROFILE:
- Name: {fleet_data.operator_name}
- Age: {fleet_data.operator_age_years:.1f} years
- Fleet Size: {fleet_data.fleet_size} aircraft
- Certifications: ARGUS {fleet_data.argus_rating or 'None'}, WYVERN {fleet_data.wyvern_rating or 'None'}

RISK INDICATORS:
- Fleet Events: {len(fleet_data.fleet_events)}
- UCC Filings: {len(fleet_data.ucc_filings)}
- Tail-Specific Events: {len(tail_data.tail_events)}
- Aircraft Age: {tail_data.aircraft_age_years:.1f} years

Provide a professional executive summary (4-6 sentences) covering:
1. Overall assessment: Is this operator trustworthy? What's the confidence level?
2. Key strengths and weaknesses identified in the scoring
3. Primary risk factors that charter brokers should be aware of
4. Recommendation: Would you recommend this operator for charter bookings? Under what conditions?

Be direct, professional, and focus on actionable business intelligence."""

        try:
            response = await self.llm_client.get_completion(prompt)
            return response
        except Exception as e:
            print(f"⚠️  Error generating overall insights: {e}")
            return None
