# tests/gtj/test_router.py
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.trustscore.schemas import TrustScoreCreate, TrustScoreUpdate
from tests.auth.test_auth_router import login
from uuid import uuid4
from datetime import datetime
from decimal import Decimal
from faker import Faker

client = TestClient(app)

# Generate random data using Faker
fake = Faker()

def decimal_to_float(value):	
	return float(round(value,2))

def generate_simple_json():
	# Generate a simple JSON object with random key-value pairs
	return {fake.word(): fake.word() for _ in range(fake.random_int(min=1, max=5))}	

test_token = None

test_operator_id = None
def create_operator():
	global test_token, test_operator_id

	if test_operator_id is not None:
		return test_operator_id

	if test_token is None:
		test_token = login()
	#headers
	headers={"Authorization": f"Bearer {test_token}"}

	operator_response = client.post("/operators", json={
		"name": fake.company(),
		"dba_name": fake.company(),
		"certificate_number": fake.bothify(text="???????"),
		"ops_specs": fake.paragraph(),
		"base_airport": "KLAX",
		"trust_score": decimal_to_float(fake.pydecimal(min_value=0.1, max_value=100, positive=True)),
		"trust_score_updated_at": fake.past_datetime().isoformat(),
		"financial_health_score" :decimal_to_float(fake.pydecimal(min_value=0.1, max_value=100, positive=True)),
		"regulatory_status": "COMPLIANT",
		"is_verified": fake.boolean(),
	}, headers=headers)
	test_operator_id = operator_response.json()["operator_id"]
	return test_operator_id

def test_create_trust_score():
	global test_token
	if test_token is None:
		test_token = login()
	#headers
	headers={"Authorization": f"Bearer {test_token}"}
	print("headers:", headers)
	#create operator
	operator_id = create_operator()
	#create trust score
	trust_score_data = TrustScoreCreate(
	  operator_id=str(operator_id),  # Convert UUID to string
	  overall_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  safety_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  financial_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  regulatory_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  aog_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  factors=generate_simple_json(),
	  version=fake.word(),
	  expires_at=fake.future_datetime(),
	  confidence_level=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=1, positive=True))
	)
	response = client.post("/trust-scores", json=trust_score_data.dict(), headers=headers)
	assert response.status_code == 200
	assert "trust_score_id" in response.json()

def test_get_trust_scores():
	global test_token
	if test_token is None:
		test_token = login()
	#headers
	headers={"Authorization": f"Bearer {test_token}"}

	#create operator
	operator_id = create_operator()
	#create trust score
	trust_score_data = TrustScoreCreate(
	  operator_id=str(operator_id),  # Convert UUID to string
	  overall_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  safety_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  financial_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  regulatory_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  aog_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  factors=generate_simple_json(),
	  version=fake.word(),
	  expires_at=fake.future_datetime(),
	  confidence_level=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=1, positive=True))
	)
	response = client.post("/trust-scores", json=trust_score_data.dict(), headers=headers)
	assert response.status_code == 200
	trust_score_id = response.json()["trust_score_id"]

  # Now, get all trust scores
	response = client.get("/trust-scores", headers=headers)
	assert response.status_code == 200
	assert isinstance(response.json(), list)

def test_get_trust_score():
	global test_token
	if test_token is None:
		test_token = login()
	#headers
	headers={"Authorization": f"Bearer {test_token}"}

	#create operator
	operator_id = create_operator()
	#create trust score
	trust_score_data = TrustScoreCreate(
	  operator_id=str(operator_id),  # Convert UUID to string
	  overall_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  safety_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  financial_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  regulatory_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  aog_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
	  factors=generate_simple_json(),
	  version=fake.word(),
	  expires_at=fake.future_datetime(),
	  confidence_level=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=1, positive=True))
	)
	response = client.post("/trust-scores", json=trust_score_data.dict(), headers=headers)
	assert response.status_code == 200
	trust_score_id = response.json()["trust_score_id"]

  # Now, get the trust score by ID
	response = client.get(f"/trust-scores/{trust_score_id}", headers=headers)
	assert response.status_code == 200
	assert response.json()["trust_score_id"] == trust_score_id

def test_update_trust_score():
	global test_token
	if test_token is None:
		test_token = login()
	#headers
	headers={"Authorization": f"Bearer {test_token}"}

	#create operator
	operator_id = create_operator()
	#create trust score
	trust_score_data = TrustScoreCreate(
		operator_id=str(operator_id),  # Convert UUID to string
		overall_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
		safety_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
		financial_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
		regulatory_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
		aog_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
		factors=generate_simple_json(),
		version=fake.word(),
		expires_at=fake.future_datetime(),
		confidence_level=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=1, positive=True))
	)
	response = client.post("/trust-scores", json=trust_score_data.dict(), headers=headers)
	assert response.status_code == 200
	trust_score_id = response.json()["trust_score_id"]

  # Now, update the trust score
	trust_score_update = TrustScoreUpdate(
		operator_id=str(operator_id),  # Convert UUID to string
		overall_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
		safety_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
		financial_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
		regulatory_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
		aog_score=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=100, positive=True)),
		factors=generate_simple_json(),
		version=fake.word(),
		expires_at=fake.future_datetime(),
		confidence_level=decimal_to_float(fake.pyfloat(min_value=0.1, max_value=1, positive=True))
	)

	response = client.put(f"/trust-scores/{trust_score_id}", json=trust_score_update.dict(), headers=headers)
	assert response.status_code == 200
	assert response.json()["overall_score"] == trust_score_update.overall_score
	assert response.json()["safety_score"] == trust_score_update.safety_score
	assert response.json()["financial_score"] == trust_score_update.financial_score
	assert response.json()["regulatory_score"] == trust_score_update.regulatory_score
	assert response.json()["aog_score"] == trust_score_update.aog_score
	assert response.json()["factors"] == trust_score_update.factors
	assert response.json()["version"] == trust_score_update.version
	assert response.json()["expires_at"] == trust_score_update.expires_at.isoformat()
	assert response.json()["confidence_level"] == trust_score_update.confidence_level