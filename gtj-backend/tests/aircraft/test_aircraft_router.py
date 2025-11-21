# tests/aircraft/test_aircraft_router.py
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.aircraft.schemas import AircraftCreate, AircraftUpdate
from tests.auth.test_auth_router import login
from uuid import uuid4
from faker import Faker
from decimal import Decimal
from datetime import datetime

client = TestClient(app)
fake = Faker()
test_token = None
test_operator_id = None

def decimal_to_float(value, places=2):  
  return float(round(value, places))

def datetime_to_string(value):
	if isinstance(value, datetime):
		return value.isoformat()
	return value

def create_operator():
	global test_token, test_operator_id

	if test_operator_id is not None:
		return test_operator_id
	
	if test_token is None:
		test_token = login()
		if test_token is None:
			pytest.fail("Failed to obtain a valid token")

	headers = {"Authorization": f"Bearer {test_token}"}

	operator_data = {
		"name": fake.company(),
		"dba_name": fake.company(),
		"certificate_number": fake.bothify(text="???????"),
		"ops_specs": fake.paragraph(),
		"base_airport": "KLAX",
		"trust_score": decimal_to_float(fake.pydecimal(min_value=0.1, max_value=100, positive=True)),
		"trust_score_updated_at": datetime_to_string(fake.past_datetime()),
		"financial_health_score": decimal_to_float(fake.pydecimal(min_value=0.1, max_value=100, positive=True)),
		"regulatory_status": "COMPLIANT",
		"is_verified": fake.boolean(),
	}
	operator_response = client.post("/operators", json=operator_data, headers=headers)
	if operator_response.status_code != 200:
		pytest.fail(f"Failed to create operator: {operator_response.json()}")
	test_operator_id = operator_response.json()["operator_id"]
	return test_operator_id

def test_create_aircraft():
	global test_token
	if test_token is None:
		test_token = login()
		if test_token is None:
			pytest.fail("Failed to obtain a valid token")

	headers = {"Authorization": f"Bearer {test_token}"}

	operator_id = create_operator()

	aircraft_data = {
		"tail_number": fake.bothify(text="??-???"),
		"operator_id": operator_id,
		"make_model": fake.word(),
		"year": fake.year(),
		"serial_number": fake.bothify(text="???????"),
		"aircraft_type": fake.word(),
		"passenger_capacity": fake.random_int(min=1, max=50),
		"range_nautical_miles": fake.random_int(min=100, max=10000),
		"cruise_speed_knots": fake.random_int(min=100, max=1000),
		"current_status": "AVAILABLE",
		"last_maintenance": datetime_to_string(fake.past_datetime()),
		"next_maintenance_due": datetime_to_string(fake.future_datetime()),
		"insurance_expiry": datetime_to_string(fake.future_datetime()),
		"home_base": fake.bothify(text="???"),
		"hourly_rate": decimal_to_float(fake.pydecimal(min_value=0.1, max_value=1000, positive=True)),
	}
	response = client.post("/aircrafts", json=aircraft_data, headers=headers)
	assert response.status_code == 200
	assert "aircraft_id" in response.json()

def test_get_aircraft():
	global test_token
	if test_token is None:
		test_token = login()
		if test_token is None:
			pytest.fail("Failed to obtain a valid token")

	headers = {"Authorization": f"Bearer {test_token}"}

	operator_id = create_operator()

	aircraft_data = {
		"tail_number": fake.bothify(text="??-???"),
		"operator_id": operator_id,
		"make_model": fake.word(),
		"year": fake.year(),
		"serial_number": fake.bothify(text="???????"),
		"aircraft_type": fake.word(),
		"passenger_capacity": fake.random_int(min=1, max=50),
		"range_nautical_miles": fake.random_int(min=100, max=10000),
		"cruise_speed_knots": fake.random_int(min=100, max=1000),
		"current_status": "AVAILABLE",
		"last_maintenance": datetime_to_string(fake.past_datetime()),
		"next_maintenance_due": datetime_to_string(fake.future_datetime()),
		"insurance_expiry": datetime_to_string(fake.future_datetime()),
		"home_base": fake.bothify(text="???"),
		"hourly_rate": decimal_to_float(fake.pydecimal(min_value=0.1, max_value=1000, positive=True)),
	}
	response = client.post("/aircrafts", json=aircraft_data, headers=headers)
	assert response.status_code == 200
	aircraft_id = response.json()["aircraft_id"]

	response = client.get(f"/aircrafts/{aircraft_id}", headers=headers)
	assert response.status_code == 200
	assert response.json()["aircraft_id"] == aircraft_id

def test_get_aircrafts():
	global test_token
	if test_token is None:
		test_token = login()
		if test_token is None:
			pytest.fail("Failed to obtain a valid token")

	headers = {"Authorization": f"Bearer {test_token}"}

	response = client.get(f"/aircrafts", headers=headers)
	assert response.status_code == 200
	assert isinstance(response.json(), list)

def test_update_aircraft():
	global test_token
	if test_token is None:
		test_token = login()
		if test_token is None:
			pytest.fail("Failed to obtain a valid token")

	headers = {"Authorization": f"Bearer {test_token}"}

	operator_id = create_operator()

	aircraft_data = {
		"tail_number": fake.bothify(text="??-???"),
		"operator_id": operator_id,
		"make_model": fake.word(),
		"year": fake.year(),
		"serial_number": fake.bothify(text="???????"),
		"aircraft_type": fake.word(),
		"passenger_capacity": fake.random_int(min=1, max=50),
		"range_nautical_miles": fake.random_int(min=100, max=10000),
		"cruise_speed_knots": fake.random_int(min=100, max=1000),
		"current_status": "AVAILABLE",
		"last_maintenance": datetime_to_string(fake.past_datetime()),
		"next_maintenance_due": datetime_to_string(fake.future_datetime()),
		"insurance_expiry": datetime_to_string(fake.future_datetime()),
		"home_base": fake.bothify(text="???"),
		"hourly_rate": decimal_to_float(fake.pydecimal(min_value=0.1, max_value=1000, positive=True)),
	}
	response = client.post("/aircrafts", json=aircraft_data, headers=headers)
	assert response.status_code == 200
	aircraft_id = response.json()["aircraft_id"]

	update_data = {
		"operator_id": operator_id,
		"make_model": fake.word(),
		"year": fake.year(),
		"serial_number": fake.bothify(text="???????"),
		"aircraft_type": fake.word(),
		"passenger_capacity": fake.random_int(min=1, max=50),
		"range_nautical_miles": fake.random_int(min=100, max=10000),
		"cruise_speed_knots": fake.random_int(min=100, max=1000),
		"current_status": "MAINTENANCE",
		"last_maintenance": datetime_to_string(fake.past_datetime()),
		"next_maintenance_due": datetime_to_string(fake.future_datetime()),
		"insurance_expiry": datetime_to_string(fake.future_datetime()),
		"home_base": fake.bothify(text="???"),
		"hourly_rate": decimal_to_float(fake.pydecimal(min_value=0.1, max_value=1000, positive=True)),
	}
	response = client.put(f"/aircrafts/{aircraft_id}", json=update_data, headers=headers)
	assert response.status_code == 200
	assert response.json()["make_model"] == update_data["make_model"]
	assert int(response.json()["year"]) == int(update_data["year"])
	assert response.json()["serial_number"] == update_data["serial_number"]
	assert response.json()["aircraft_type"] == update_data["aircraft_type"]
	assert response.json()["passenger_capacity"] == update_data["passenger_capacity"]
	assert response.json()["range_nautical_miles"] == update_data["range_nautical_miles"]
	assert response.json()["cruise_speed_knots"] == update_data["cruise_speed_knots"]
	assert response.json()["current_status"] == update_data["current_status"]
	assert response.json