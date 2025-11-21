# tests/gtj/test_operator_router.py
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.operator.schemas import OperatorCreate, OperatorUpdate
from tests.auth.test_auth_router import login
from uuid import uuid4
from faker import Faker
from decimal import Decimal
from datetime import datetime

client = TestClient(app)
fake = Faker()
test_token = None

def decimal_to_float(value, places=2):
  return float(round(value, places))

def datetime_to_string(value):
	if isinstance(value, datetime):
		return value.isoformat()
	return value

def test_create_operator():
	global test_token
	if test_token is None:
		test_token = login()
		if test_token is None:
			pytest.fail("Failed to obtain a valid token")

	headers = {"Authorization": f"Bearer {test_token}"}

	operator_data = OperatorCreate(
		name=fake.company(),
		dba_name=fake.company(),
		certificate_number=fake.bothify(text="???????"),
		ops_specs=fake.paragraph(),
		base_airport="KLAX",
		trust_score=decimal_to_float(fake.pydecimal(min_value=0.1, max_value=100, positive=True)),
		trust_score_updated_at=fake.past_datetime(),
		financial_health_score=decimal_to_float(fake.pydecimal(min_value=0.1, max_value=100, positive=True)),
		regulatory_status="COMPLIANT",
		is_verified=fake.boolean(),
	)
	response = client.post("/operators", json=operator_data.dict(), headers=headers)
	assert response.status_code == 200
	assert "operator_id" in response.json()

def test_get_operator():
	global test_token
	if test_token is None:
		test_token = login()
		if test_token is None:
			pytest.fail("Failed to obtain a valid token")

	headers = {"Authorization": f"Bearer {test_token}"}

	operator_data = OperatorCreate(
		name=fake.company(),
		dba_name=fake.company(),
		certificate_number=fake.bothify(text="???????"),
		ops_specs=fake.paragraph(),
		base_airport="KLAX",
		trust_score=decimal_to_float(fake.pydecimal(min_value=0.1, max_value=100, positive=True)),
		trust_score_updated_at=fake.past_datetime(),
		financial_health_score=decimal_to_float(fake.pydecimal(min_value=0.1, max_value=100, positive=True)),
		regulatory_status="COMPLIANT",
		is_verified=fake.boolean(),
	)
	response = client.post("/operators", json=operator_data.dict(), headers=headers)
	assert response.status_code == 200
	operator_id = response.json()["operator_id"]

	response = client.get(f"/operators/{operator_id}", headers=headers)
	assert response.status_code == 200
	assert response.json()["operator_id"] == operator_id

def test_get_operators():
	global test_token
	if test_token is None:
		test_token = login()
		if test_token is None:
			pytest.fail("Failed to obtain a valid token")

	headers = {"Authorization": f"Bearer {test_token}"}

	response = client.get(f"/operators", headers=headers)
	assert response.status_code == 200
	assert isinstance(response.json(), list)

def test_update_operator():
	global test_token
	if test_token is None:
		test_token = login()
		if test_token is None:
			pytest.fail("Failed to obtain a valid token")

	headers = {"Authorization": f"Bearer {test_token}"}

	operator_data = OperatorCreate(
		name=fake.company(),
		dba_name=fake.company(),
		certificate_number=fake.bothify(text="???????"),
		ops_specs=fake.paragraph(),
		base_airport="KLAX",
		trust_score=decimal_to_float(fake.pydecimal(min_value=0.1, max_value=100, positive=True)),
		trust_score_updated_at=fake.past_datetime(),
		financial_health_score=decimal_to_float(fake.pydecimal(min_value=0.1, max_value=100, positive=True)),
		regulatory_status="COMPLIANT",
		is_verified=fake.boolean(),
	)
	response = client.post("/operators", json=operator_data.dict(), headers=headers)
	assert response.status_code == 200
	operator_id = response.json()["operator_id"]

	update_data = OperatorUpdate(
		name=fake.company(),
		dba_name=fake.company(),
		certificate_number=fake.bothify(text="???????"),
		ops_specs=fake.paragraph(),
		base_airport="KLAX",
		trust_score=decimal_to_float(fake.pydecimal(min_value=0.1, max_value=100, positive=True)),
		trust_score_updated_at=fake.past_datetime(),
		financial_health_score=decimal_to_float(fake.pydecimal(min_value=0.1, max_value=100, positive=True)),
		regulatory_status="WARNING",
		is_verified=fake.boolean(),
	)
	response = client.put(f"/operators/{operator_id}", json=update_data.dict(), headers=headers)
	assert response.status_code == 200
	assert response.json()["name"] == update_data.name
	assert response.json()["dba_name"] == update_data.dba_name
	assert response.json()["certificate_number"] == update_data.certificate_number
	assert response.json()["ops_specs"] == update_data.ops_specs
	assert response.json()["base_airport"] == update_data.base_airport
	assert float(response.json()["trust_score"]) == float(update_data.trust_score)
	assert response.json()["trust_score_updated_at"] == datetime_to_string(update_data.trust_score_updated_at)
	assert float(response.json()["financial_health_score"]) == float(update_data.financial_health_score)
	assert response.json()["regulatory_status"] == update_data.regulatory_status
	assert response.json()["is_verified"] == update_data.is_verified