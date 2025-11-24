# src/gtj/service.py
from sqlalchemy.orm import Session
from src.common.models import TrustScore
from src.trustscore.schemas import TrustScoreCreate, TrustScoreUpdate

def create_trust_score(db: Session, trust_score: TrustScoreCreate):
  """
  Create a new trust score.

  :param db: SQLAlchemy session
  :param trust_score: TrustScoreCreate - The trust score data to be created
  :return: TrustScore - The newly created trust score
  """
  db_trust_score = TrustScore(**trust_score.dict())
  db.add(db_trust_score)
  db.commit()
  db.refresh(db_trust_score)
  return db_trust_score

def get_trust_scores(db: Session, skip: int = 0, limit: int = 100):
  """
  Retrieve a list of all trust scores with pagination support.

  :param db: SQLAlchemy session
  :param skip: int - Number of trust scores to skip (for pagination)
  :param limit: int - Maximum number of trust scores to return (for pagination)
  :return: list[TrustScore] - A list of trust score objects
  """
  return db.query(TrustScore).offset(skip).limit(limit).all()

def get_trust_score(db: Session, trust_score_id: str):
  """
  Retrieve a trust score by its unique ID.

  :param db: SQLAlchemy session
  :param trust_score_id: str - The unique ID of the trust score
  :return: TrustScore - The trust score object if found, otherwise None
  """
  return db.query(TrustScore).filter(TrustScore.trust_score_id == trust_score_id).first()

def update_trust_score(db: Session, trust_score_id: str, trust_score_update: TrustScoreUpdate):
  """
  Update an existing trust score by its unique ID.

  :param db: SQLAlchemy session
  :param trust_score_id: str - The unique ID of the trust score
  :param trust_score_update: TrustScoreUpdate - The updated trust score data
  :return: TrustScore - The updated trust score object if found, otherwise None
  """
  db_trust_score = db.query(TrustScore).filter(TrustScore.trust_score_id == trust_score_id).first()
  if not db_trust_score:
    return None
  for key, value in trust_score_update.dict(exclude_unset=True).items():
    setattr(db_trust_score, key, value)
  db.commit()
  db.refresh(db_trust_score)
  return db_trust_score

# def calculate_fleet_score(operator: Operator):
#   initial_score = 100
#   financial_risk_score = 0  # Placeholder for LLM financial risk score
#   legal_risk_score = 0  # Placeholder for LLM legal risk score

#   # Deduct points based on financial and legal risk scores
#   initial_score -= financial_risk_score
#   initial_score -= legal_risk_score

#   # Deduct points based on age of operator
#   age_of_operator = (datetime.utcnow() - operator.created_at).days // 365
#   initial_score -= max(0, 2 * (age_of_operator - 10))

#   # Deduct points for each NTSB filing with ACCIDENT event type in the last 5 years
#   # Placeholder for actual NTSB filings
#   ntsb_accident_filings = 0
#   initial_score -= 2 * ntsb_accident_filings

#   # Deduct points based on ARGUS and WYVERN ratings
#   # Placeholder for actual ratings
#   argus_rating = "Platinum Elite"
#   wyvern_rating = "Wingman PRO"
#   ratings_points = {
#     "Platinum Elite": 0,
#     "Platinum": -2,
#     "Gold Plus": -4,
#     "Gold": -6,
#     "Registered Operator": -10,
#     "None": -10
#   }
#   initial_score += max(ratings_points[argus_rating], ratings_points[wyvern_rating])

#   return max(0, initial_score)

# def calculate_tail_score(aircraft: Aircraft):
#   initial_score = 100

#   # Deduct points based on age of aircraft
#   age_of_aircraft = (datetime.utcnow() - aircraft.created_at).days // 365
#   age_points = {
#     (2, 5): 0,
#     (5, 8): -2,
#     (8, 12): -4,
#     (12, 16): -6,
#     (16, 20): -8,
#     (20, float('inf')): -10,
#     (0, 2): -10
#   }
#   for age_range, points in age_points.items():
#     if age_range[0] <= age_of_aircraft < age_range[1]:
#       initial_score += points
#       break

#   # Deduct points if operator name does not match registered owner
#   if operator.name != aircraft.registered_owner:
#     initial_score -= 10

#   # Deduct points if fractional owner is true
#   if aircraft.fractional_owner:
#     initial_score -= 5

#   # Deduct points for each NTSB incident
#   # Placeholder for actual NTSB incidents
#   ntsb_incidents = []
#   for incident in ntsb_incidents:
#     if incident.event_type == "Accident":
#       initial_score -= 2 * max(0, incident.age - 10)
#     initial_score -= incident.injury_points

#   return max(0, initial_score)
