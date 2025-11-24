# tests/gtj/test_organization_router.py
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.organization.schemas import OrganizationCreate, OrganizationUpdate
from tests.auth.test_auth_router import login
from uuid import uuid4
from faker import Faker
from datetime import datetime

client = TestClient(app)
fake = Faker()
test_token = None

def test_create_organization():
	global test_token
	if test_token is None:
		test_token = login()
		if test_token is None:
			pytest.fail("Failed to obtain a valid token")

	headers = {"Authorization": f"Bearer {test_token}"}

	organization_data = OrganizationCreate(
		name=fake.company(),
		type=fake.word(ext_word_list=["BROKER", "OPERATOR", "ENTERPRISE", "INTERNAL"]),
		subscription_tier=fake.word(ext_word_list=["STARTER", "PROFESSIONAL", "ENTERPRISE", "INTERNAL", "INACTIVE"]),
		billing_email=fake.email(),
		tax_id=fake.bothify(text="??-???????"),
		address={"street": fake.street_address(), "city": fake.city(), "state": fake.state(), "zip": fake.zipcode()},
		settings={"theme": "dark", "notifications": True}
	)
	response = client.post("/organizations", json=organization_data.dict(), headers=headers)
	assert response.status_code == 200
	assert "organization_id" in response.json()

def test_get_organization():
	global test_token
	if test_token is None:
		test_token = login()
		if test_token is None:
			pytest.fail("Failed to obtain a valid token")

	headers = {"Authorization": f"Bearer {test_token}"}

	organization_data = OrganizationCreate(
		name=fake.company(),
		type=fake.word(ext_word_list=["BROKER", "OPERATOR", "ENTERPRISE", "INTERNAL"]),
		subscription_tier=fake.word(ext_word_list=["STARTER", "PROFESSIONAL", "ENTERPRISE", "INTERNAL", "INACTIVE"]),
		billing_email=fake.email(),
		tax_id=fake.bothify(text="??-???????"),
		address={"street": fake.street_address(), "city": fake.city(), "state": fake.state(), "zip": fake.zipcode()},
		settings={"theme": "dark", "notifications": True}
	)
	response = client.post("/organizations", json=organization_data.dict(), headers=headers)
	assert response.status_code == 200
	organization_id = response.json()["organization_id"]

	response = client.get(f"/organizations/{organization_id}", headers=headers)
	assert response.status_code == 200
	assert response.json()["organization_id"] == organization_id

def test_get_organizations():
	global test_token
	if test_token is None:
		test_token = login()
		if test_token is None:
			pytest.fail("Failed to obtain a valid token")

	headers = {"Authorization": f"Bearer {test_token}"}

	response = client.get(f"/organizations", headers=headers)
	assert response.status_code == 200
	assert isinstance(response.json(), list)

def test_update_organization():
	global test_token
	if test_token is None:
		test_token = login()
		if test_token is None:
			pytest.fail("Failed to obtain a valid token")

	headers = {"Authorization": f"Bearer {test_token}"}

	organization_data = OrganizationCreate(
		name=fake.company(),
		type=fake.word(ext_word_list=["BROKER", "OPERATOR", "ENTERPRISE", "INTERNAL"]),
		subscription_tier=fake.word(ext_word_list=["STARTER", "PROFESSIONAL", "ENTERPRISE", "INTERNAL", "INACTIVE"]),
		billing_email=fake.email(),
		tax_id=fake.bothify(text="??-???????"),
		address={"street": fake.street_address(), "city": fake.city(), "state": fake.state(), "zip": fake.zipcode()},
		settings={"theme": "dark", "notifications": True}
	)
	response = client.post("/organizations", json=organization_data.dict(), headers=headers)
	assert response.status_code == 200
	organization_id = response.json()["organization_id"]

	update_data = OrganizationUpdate(
		name=fake.company(),
		type=fake.word(ext_word_list=["BROKER", "OPERATOR", "ENTERPRISE", "INTERNAL"]),
		subscription_tier=fake.word(ext_word_list=["STARTER", "PROFESSIONAL", "ENTERPRISE", "INTERNAL", "INACTIVE"]),
		billing_email=fake.email(),
		tax_id=fake.bothify(text="??-???????"),
		address={"street": fake.street_address(), "city": fake.city(), "state": fake.state(), "zip": fake.zipcode()},
		settings={"theme": "light", "notifications": False}
	)
	response = client.put(f"/organizations/{organization_id}", json=update_data.dict(), headers=headers)
	assert response.status_code == 200
	assert response.json()["name"] == update_data.name
	assert response.json()["type"] == update_data.type
	assert response.json()["subscription_tier"] == update_data.subscription_tier
	assert response.json()["billing_email"] == update_data.billing_email
	assert response.json()["tax_id"] == update_data.tax_id
	assert response.json()["address"] == update_data.address
	assert response.json()["settings"] == update_data.settings