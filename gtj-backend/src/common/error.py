from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from src.common.constants import HTTP_401_UNAUTHORIZED, HTTP_500_INTERNAL_SERVER_ERROR

class AuthError(HTTPException):
  def __init__(self, detail: str = "Authentication Error"):
    super().__init__(status_code=HTTP_401_UNAUTHORIZED, detail=detail)

class HTTPError(HTTPException):
  def __init__(self, detail: str = "Internal System Error"):
    message = self.args[0] if self and self.args else detail 
    super().__init__(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail=message)

async def exception_handler(request: Request, exc: Exception):
  detail = exc.args[0] if exc and exc.args else str(exc) 
  return JSONResponse(
      status_code=500,
      content={
          "message": f"An error has occurred: {type(exc).__name__}",
          "detail": detail,
          "path": request.url.path
      }
  )    