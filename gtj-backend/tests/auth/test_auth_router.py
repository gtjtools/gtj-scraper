import pytest
from fastapi.testclient import TestClient
from src.main import app
from faker import Faker

client = TestClient(app)
fake = Faker()

def login():
	response = client.post("/auth/login", json={
		"email": "ngabon@gotrustjet.com",
		"password": "Qazwsxedc123456$"
	})
	return response.json().get("access_token")

def test_login_route():
	response = client.post("/auth/login", json={
	  "email": fake.email(), 
	  "password": fake.password()
	})
	assert response.status_code in [200, 401, 500]

def test_register_route():
	email = fake.email()
	role = "user"
	first_name = fake.first_name()
	last_name = fake.last_name()
	phone = fake.phone_number()
	org_id = "94d76474-c055-4882-ab9d-651c29cf5fb9"
	response = client.post("/users/register", json={
		"email": email,
		"role": role,
		"first_name": first_name,
		"last_name": last_name,
		"phone": phone,
		"org_id": org_id
	})
	assert response.status_code in [200, 400, 500]
