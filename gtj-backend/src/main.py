from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from src.auth.router import auth_router
from src.aircraft.router import aircraft_router
from src.organization.router import organization_router
from src.operator.router import operator_router
from src.trustscore.router import trustscore_router
from src.user.router import user_router
from src.scoring.router import scoring_router
from src.common.error import AuthError, HTTPError, exception_handler

app = FastAPI()

# Set all CORS enabled origins
app.add_middleware(
  CORSMiddleware,
  allow_origins=['*'],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError):
  return JSONResponse(
    status_code=exc.status_code,
    content={"message": exc.detail, "code": "AUTH_FAILED", "status_code": exc.status_code}
  )

@app.exception_handler(HTTPError)
async def http_error_handler(request: Request, exc: HTTPError):
  return JSONResponse(
    status_code=400,
    content={"message": exc.detail or str(exc), "code": "500", "status_code": 400}
  )

@app.exception_handler(Exception)
async def http_exception_handler(request: Request, exc: Exception):
  return await exception_handler(request, exc)

app.include_router(organization_router, tags=["organization"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(user_router, prefix="/users", tags=["user"])
app.include_router(operator_router, tags=["operator"])
app.include_router(aircraft_router, tags=["aircraft"])
app.include_router(trustscore_router, tags=["trust-score"])
app.include_router(scoring_router, tags=["scoring"])


if __name__ == "__main__":
  import uvicorn
  uvicorn.run(app, host="0.0.0.0", port=8000)
