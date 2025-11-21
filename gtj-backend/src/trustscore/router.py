# src/gtj/router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.trustscore.schemas import TrustScoreCreate, TrustScoreUpdate, TrustScore, CalculatedTrustScore
from src.trustscore.service import create_trust_score, get_trust_scores, get_trust_score, update_trust_score
# calculate_fleet_score, calculate_tail_score
from src.common.dependencies import get_db
from src.auth.service import authentication
from uuid import UUID

trustscore_router = APIRouter()

@trustscore_router.post(
	"/trust-scores",
	response_model=TrustScore,
	summary="Create a new trust score",
	description="Create a new trust score with the provided details.",
	tags=["trust_scores"]
)
def post_trust_score(trust_score: TrustScoreCreate, db: Session = Depends(get_db), auth=Depends(authentication)):
	"""
	Create a new trust score.

	- **trust_score**: TrustScoreCreate - The trust score data to be created.
	- **db**: Session - The database session (injected by Depends(get_db)).
	- **auth**: Authentication - The authentication details (injected by Depends(authentication)).

	Returns:
		TrustScore: The newly created trust score.

	Raises:
			HTTPException: If the trust score cannot be created.
	"""
	db_trust_score = create_trust_score(db, trust_score)
	return db_trust_score

@trustscore_router.get(
	"/trust-scores",
	response_model=list[TrustScore],
	summary="Get all trust scores",
	description="Retrieve a list of all trust scores with pagination support.",
	tags=["trust_scores"]
)
def get_trust_scores_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), auth=Depends(authentication)):
	"""
	Retrieve a list of all trust scores.

	- **skip**: int - Number of trust scores to skip (for pagination).
	- **limit**: int - Maximum number of trust scores to return (for pagination).
	- **db**: Session - The database session (injected by Depends(get_db)).
	- **auth**: Authentication - The authentication details (injected by Depends(authentication)).

	Returns:
		list[TrustScore]: A list of trust score objects.

	Raises:
		HTTPException: If no trust scores are found.
	"""
	trust_scores = get_trust_scores(db, skip=skip, limit=limit)
	return trust_scores

@trustscore_router.get(
	"/trust-scores/{trust_score_id}",
	response_model=TrustScore,
	summary="Get a trust score by ID",
	description="Retrieve a trust score by its unique ID.",
	tags=["trust_scores"]
)
def get_trust_score_endpoint(trust_score_id: str, db: Session = Depends(get_db), auth=Depends(authentication)):
	"""
	Retrieve a trust score by its unique ID.

	- **trust_score_id**: str - The unique ID of the trust score.
	- **db**: Session - The database session (injected by Depends(get_db)).
	- **auth**: Authentication - The authentication details (injected by Depends(authentication)).

	Returns:
		TrustScore: The trust score object.

	Raises:
		HTTPException: If the trust score is not found.
	"""
	db_trust_score = get_trust_score(db, trust_score_id)
	if not db_trust_score:
		raise HTTPException(status_code=404, detail="Trust score not found")
	return db_trust_score

@trustscore_router.put(
	"/trust-scores/{trust_score_id}",
	response_model=TrustScore,
	summary="Update a trust score",
	description="Update an existing trust score by its unique ID.",
	tags=["trust_scores"]
)
def put_trust_score(trust_score_id: str, trust_score_update: TrustScoreUpdate, db: Session = Depends(get_db), auth=Depends(authentication)):
	"""
	Update an existing trust score by its unique ID.

	- **trust_score_id**: str - The unique ID of the trust score.
	- **trust_score_update**: TrustScoreUpdate - The updated trust score data.
	- **db**: Session - The database session (injected by Depends(get_db)).
	- **auth**: Authentication - The authentication details (injected by Depends(authentication)).

	Returns:
		TrustScore: The updated trust score object.

	Raises:
		HTTPException: If the trust score is not found or cannot be updated.
	"""

	db_trust_score = update_trust_score(db, trust_score_id, trust_score_update)
	if not db_trust_score:
		raise HTTPException(status_code=404, detail="Trust score not found")
	return db_trust_score

# @trustscore_router.post(
# 	"/operators/{operator_id}/trust-scores", 
# 	response_model=CalculatedTrustScore
# )
# def calculate_trust_score(operator_id: UUID, db: Session = Depends(get_db)):
# 	operator = db.query(Operator).filter(Operator.operator_id == operator_id).first()
# 	if not operator:
# 		raise HTTPException(status_code=404, detail="Operator not found")

# 	# Retrieve all aircraft associated with the operator
# 	aircraft_list = db.query(Aircraft).filter(Aircraft.operator_id == operator_id).all()

# 	if not aircraft_list:
# 		raise HTTPException(status_code=404, detail="No aircraft found for the operator")

# 	# Calculate fleet score
# 	fleet_score = calculate_fleet_score(operator)

# 	# Calculate tail scores for each aircraft and average them
# 	tail_scores = [calculate_tail_score(aircraft) for aircraft in aircraft_list]
# 	average_tail_score = sum(tail_scores) / len(tail_scores)

# 	# Calculate overall trust score
# 	trust_score = 0.5 * fleet_score + 0.5 * average_tail_score
# 	return { "trust_score": trust_score }