from fastapi import APIRouter, Depends, HTTPException
from pydantic import UUID4
from sqlalchemy.orm import Session
from src.auth.service import authentication
from src.common.models import UserProfile, UserRole
from src.user.schemas import UserCreate, UserUpdate, UserInDB, UserRoleCreate, UserRoleUpdate, UserRoleInDB
from src.user.service import create_user, get_user, update_user as edit_user, create_user_role, get_user_roles, get_user_role, update_user_role
from src.common.dependencies import get_db
from src.common.constants import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND
from src.common.error import HTTPError
from src.common.utils import get_supabase_client

# Create an instance of FastAPI's APIRouter to define the user routes
user_router = APIRouter()

@user_router.post(
  "/register",
  response_model=UserInDB,
  summary="Register a new user",
  description="Create a new user with the provided details. If the email is already registered, an error will be returned."
)
async def register_user(user: UserCreate, db: Session = Depends(get_db)):
  """
  Register a new user.

  - **user**: UserCreate - The user data to be registered.
  - **db**: Session - The database session (injected by Depends(get_db)).

  Returns:
    UserInDB: The newly created user.

  Raises:
    HTTPException: If the email is already registered.
  """

  db_user = create_user(db, user)
  if not db_user:
    raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Email already registered")
  return db_user


@user_router.get(
  "/{user_id}",
  response_model=UserInDB,
  summary="Get user by ID",
  description="Retrieve a user by their unique ID. If the user is not found, an error will be returned."
)
async def read_user(user_id: str, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Retrieve a user by their unique ID.

  - **user_id**: str - The ID of the user to retrieve.
  - **db**: Session - The database session (injected by Depends(get_db)).

  Returns:
    UserInDB: The user data.

  Raises:
    HTTPException: If the user is not found.
  """
  db_user = get_user(db, user_id)
  if not db_user:
    raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found")
  return db_user

@user_router.put(
  "/{user_id}",
  response_model=UserInDB,
  summary="Update user by ID",
  description="Update a user by their unique ID. If the user is not found, an error will be returned."
)
async def update_user(user_id: str, user_update: UserUpdate, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Update a user by their unique ID.

  - **user_id**: str - The ID of the user to update.
  - **user_update**: UserUpdate - The updated user data.
  - **db**: Session - The database session (injected by Depends(get_db)).

  Returns:
    UserInDB: The updated user data.

  Raises:
    HTTPException: If the user is not found.
  """
  db_user = edit_user(db, user_id, user_update)
  if not db_user:
    raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found")
  return db_user

@user_router.post(
  "/user-roles",
  response_model=UserRoleInDB,
  summary="Create a new user role",
  description="Create a new user role with the provided details.",
  tags=["user_roles"]
)
def create_user_role_endpoint(user_role: UserRoleCreate, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Create a new user role.

  - **user_role**: UserRoleCreate - The user role data to be created.
  - **db**: Session - The database session (injected by Depends(get_db)).

  Returns:
      UserRole: The newly created user role.

  Raises:
      HTTPException: If the user role cannot be created.
  """
  db_user_role = create_user_role(db, user_role)
  return db_user_role

@user_router.get(
  "/user-roles",
  response_model=list[UserRoleInDB],
  summary="Get all user roles",
  description="Retrieve a list of all user roles with pagination support.",
  tags=["user_roles"]
)
def get_user_roles_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), auth = Depends(authentication)):
    """
    Retrieve a list of all user roles.

    - **skip**: int - Number of user roles to skip (for pagination).
    - **limit**: int - Maximum number of user roles to return (for pagination).
    - **db**: Session - The database session (injected by Depends(get_db)).

    Returns:
        list[UserRole]: A list of user role objects.

    Raises:
        HTTPException: If no user roles are found.
    """
    user_roles = get_user_roles(db, skip=skip, limit=limit)
    return user_roles

@user_router.get(
  "/user-roles/{user_role_id}",
  response_model=UserRoleInDB,
  summary="Get a user role by ID",
  description="Retrieve a user role by its unique ID.",
  tags=["user_roles"]
)
def get_user_role_endpoint(user_role_id: UUID4, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Retrieve a user role by its unique ID.

  - **user_role_id**: UUID - The unique ID of the user role.
  - **db**: Session - The database session (injected by Depends(get_db)).

  Returns:
      UserRole: The user role object.

  Raises:
      HTTPException: If the user role is not found.
  """
  db_user_role = get_user_role(db, user_role_id)
  if not db_user_role:
      raise HTTPException(status_code=404, detail="User role not found")
  return db_user_role

@user_router.put(
  "/user-roles/{user_role_id}",
  response_model=UserRoleInDB,
  summary="Update a user role",
  description="Update an existing user role by its unique ID.",
  tags=["user_roles"]
)
def update_user_role_endpoint(user_role_id: UUID4, user_role_update: UserRoleUpdate, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Update an existing user role by its unique ID.

  - **user_role_id**: UUID - The unique ID of the user role.
  - **user_role_update**: UserRoleUpdate - The updated user role data.
  - **db**: Session - The database session (injected by Depends(get_db)).

  Returns:
      UserRole: The updated user role object.

  Raises:
      HTTPException: If the user role is not found or cannot be updated.
  """
  db_user_role = update_user_role(db, user_role_id, user_role_update)
  if not db_user_role:
      raise HTTPException(status_code=404, detail="User role not found")
  return db_user_role