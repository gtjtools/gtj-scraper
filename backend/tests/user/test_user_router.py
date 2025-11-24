import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.user.schemas import UserCreate, UserUpdate
from tests.auth.test_auth_router import login
from faker import Faker

client = TestClient(app)
fake = Faker()

def test_read_user():	

	token = login()

	#headers
	headers={"Authorization": f"Bearer {token}"}

	response = client.post("/users/register", json={
		"email": fake.ascii_email(),
		"role": "user",
		"first_name": fake.first_name(),
		"last_name": fake.last_name(),
		"phone": fake.phone_number(),
		"org_id": "94d76474-c055-4882-ab9d-651c29cf5fb9"
	}, headers=headers)
	assert response.status_code == 200
	user_id = response.json()["user_id"]

	# Now, read the user
	response = client.get(f"/users/{user_id}", headers=headers)
	assert response.status_code == 200
	assert response.json()["user_id"] == user_id

def test_update_user():
	
	token = login()

	#headers
	headers={"Authorization": f"Bearer {token}"}

	response = client.post("/users/register", json={
		"email": fake.ascii_email(),
		"role": "user",
		"first_name": fake.first_name(),
		"last_name": fake.last_name(),
		"phone": fake.phone_number(),
		"org_id": "94d76474-c055-4882-ab9d-651c29cf5fb9"		
	}, headers=headers)
	assert response.status_code == 200
	user_id = response.json()["user_id"]

	# Now, update the user
	firstName = fake.first_name()
	lastName = fake.last_name()
	phone = fake.phone_number()
	response = client.put(f"/users/{user_id}", json={
			"first_name": firstName,
			"last_name": lastName,
			"phone": phone
	}, headers=headers)
	assert response.status_code == 200
	assert response.json()["first_name"] == firstName
	assert response.json()["last_name"] == lastName
	assert response.json()["phone"] == phone
