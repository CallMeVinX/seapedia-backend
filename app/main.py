from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import time

from app.core.config import settings
from app.api.routers import level3_auth, level4_core, level5_dashboards, level6_admin
from app.core.exceptions import http_exception_handler, validation_exception_handler, generic_exception_handler

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://seapedia-frontend.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Standard Response Middleware (calculates and injects request process time)
@app.middleware("http")
async def add_process_time_header(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Register Global Exception Handlers
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Include Routers with /api prefix
app.include_router(level3_auth.router, prefix=settings.API_V1_STR)
app.include_router(level4_core.router, prefix=settings.API_V1_STR)
app.include_router(level5_dashboards.router, prefix=settings.API_V1_STR)
app.include_router(level6_admin.router, prefix=settings.API_V1_STR)

@app.get("/")
async def read_root():
    return {"message": "Seapedia Backend is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

