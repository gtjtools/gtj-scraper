from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.organization.schemas import OrganizationCreate, OrganizationUpdate
from src.organization.service import get_organizations, get_organization, create_organization, update_organization
from src.common.dependencies import get_db
from src.auth.service import authentication
from uuid import UUID

organization_router = APIRouter()

@organization_router.get(
  "/organizations",
  summary="List all organizations",
  description="Retrieve a list of all organizations with pagination support.",
  response_description="A list of organizations",
  tags=["organizations"]
)
def read_organizations_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Retrieve a list of all organizations.

  - **skip**: Number of organizations to skip (for pagination).
  - **limit**: Maximum number of organizations to return (for pagination).

  Returns:
    list[Organization]: A list of organization objects.

  Raises:
    HTTPException: If no organizations are found.
  """
  organizations = get_organizations(db, skip=skip, limit=limit)
  return organizations

@organization_router.get(
  "/organizations/{organization_id}",
  summary="Get an organization by ID",
  description="Retrieve a specific organization by its unique ID.",
  response_description="The organization object",
  tags=["organizations"]
)
def read_organization_endpoint(organization_id: UUID, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Retrieve a specific organization by its unique ID.

  - **organization_id**: The unique ID of the organization.

  Returns:
    Organization: The organization object.

  Raises:
    HTTPException: If the organization is not found.
  """
  db_organization = get_organization(db, organization_id)
  if db_organization is None:
    raise HTTPException(status_code=404, detail="Organization not found")
  return db_organization

@organization_router.post(
  "/organizations",
  summary="Create a new organization",
  description="Create a new organization with the provided details.",
  response_description="The created organization object",
  tags=["organizations"]
)
def create_organization_endpoint(organization: OrganizationCreate, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Create a new organization with the provided details.

  - **organization**: The details of the organization to create.

  Returns:
    Organization: The created organization object.

  Raises:
    HTTPException: If the organization cannot be created.
  """
  return create_organization(db, organization)

@organization_router.put(
  "/organizations/{organization_id}",
  summary="Update an organization",
  description="Update an existing organization by its unique ID.",
  response_description="The updated organization object",
  tags=["organizations"]
)
def update_organization_endpoint(organization_id: UUID, organization: OrganizationUpdate, db: Session = Depends(get_db), auth = Depends(authentication)):
  """
  Update an existing organization by its unique ID.

  - **organization_id**: The unique ID of the organization.
  - **organization**: The updated details of the organization.

  Returns:
    Organization: The updated organization object.

  Raises:
    HTTPException: If the organization is not found or cannot be updated.
  """
  db_organization = update_organization(db, organization_id, organization)
  if db_organization is None:
    raise HTTPException(status_code=404, detail="Organization not found")
  return db_organization