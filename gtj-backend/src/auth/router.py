from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.auth.service import authentication
from src.auth.schemas import UserSignup, UserLogin, PasswordResetRequest, PasswordUpdateRequest
from src.common.dependencies import get_db
from src.common.constants import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND
from src.common.error import AuthError, HTTPError
from src.common.utils import get_supabase_client
import os

# Create an instance of FastAPI's APIRouter to define the authentication routes
auth_router = APIRouter()

@auth_router.post(
    "/signup",
    summary="Sign Up a New User",
    description="Registers a new user with the provided email and password. If the email is already registered, an error will be returned.",
    response_description="User signed up successfully",
    tags=["auth"]
)
async def signup(user: UserSignup):
  """
  Sign up a new user.

  - **email**: The email address of the user.
  - **password**: The password for the user.

  Returns:
    dict: A success message indicating that the user has been signed up.

  Raises:
    HTTPException: If the email is already registered.
  """  
  supabase = get_supabase_client()
  response = supabase.auth.sign_up({"email": user.email, "password": user.password})
  if response and response.user:
    return {"message": f"User signed up successfully. {'Confirmation email sent. You need to confirm to log in.' if response.session is None else ''}"}
  else:
    raise HTTPError(detail=response.error.message)

@auth_router.post(
    "/login",
    summary="Log In a User",
    description="Logs in a user with the provided email and password. If the credentials are invalid, an error will be returned.",
    response_description="User logged in successfully",
    tags=["auth"]
)
async def login(user: UserLogin):
  """
  Log in a user.

  - **email**: The email address of the user.
  - **password**: The password for the user.

  Returns:
    dict: A success message and the user session data.

  Raises:
    HTTPException: If the credentials are invalid.
  """
  try:
    supabase = get_supabase_client()
    response = supabase.auth.sign_in_with_password({"email": user.email, "password": user.password})
    if response and response.session:
      return response.session
    else:
      raise AuthError(detail=response.error.message)
  except Exception as e:
    raise AuthError(detail=str(e))

@auth_router.post(
  "/request-password-reset",
  summary="Request Password Reset",
  description="Sends a password reset email to the specified user's email address. The user will receive an email with a link to reset their password.",
  response_description="Password reset email sent successfully",
  tags=["auth"]  
)
async def request_password_reset(request: PasswordResetRequest):
  """
  Send a password reset request to the specified email address.

  - **email**: The email address of the user requesting a password reset.

  Returns:
    dict: A success message indicating that the password reset email has been sent.

  Raises:
    HTTPException: If the email is invalid or another error occurs.
  """
  supabase = get_supabase_client()
  response = supabase.auth.reset_password_for_email(request.email, {
    "redirect_to": f"https://{os.getenv('APP_URL')}/auth/update-password",
  })
  print('response', response)
  # Check if error is not None
  if response and response.error:
    raise HTTPError(detail=response.error.message)
  
  return {"message": "Password reset email sent successfully"}

@auth_router.post(
  "/update-password",
  summary="Update user password",
  description="Allows an authenticated user to update their password by providing the current and new password.",
  tags=["auth"]
)
async def update_password(request: PasswordUpdateRequest, auth = Depends(authentication)):
  """
  Update the user's password.

  - **current_password**: The user's current password.
  - **new_password**: The user's new password.

  Returns:
    dict: A success message indicating that the password has been updated.

  Raises:
    HTTPException: If the current password is incorrect or another error occurs.
  """
  supabase = get_supabase_client()
  # print('supabase.auth', supabase.auth)
  # Update user password
  response = supabase.auth.update_user(
    {
      "password": request.new_password,
    }
  )
  # Check if error is not None
  if response and response.error:
    raise AuthError(detail=response.error.message)
  
  return {"message": "Password updated successfully"}
