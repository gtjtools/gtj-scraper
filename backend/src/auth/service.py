# src.auth.service
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.common.error import AuthError
from src.common.utils import get_supabase_client
from jose import JWTError

class SupabaseJWTBearer(HTTPBearer):
  def __init__(self, auto_error: bool = True):
    super(SupabaseJWTBearer, self).__init__(auto_error=auto_error)

  async def __call__(self, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    token = credentials.credentials
    try:
      supabase = get_supabase_client()
      response = supabase.auth.get_user(token)
      print('supabase.auth.get_user', response)
      if response and response.user:
        user_data = response.user.__dict__
        return {
          **user_data,
          "token": token,
        }
      else:
        raise AuthError(detail="Unauthorized")
    except Exception as ex:
      raise AuthError(detail="Invalid or expired token!")

authentication = SupabaseJWTBearer()
