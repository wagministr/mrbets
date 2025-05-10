from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="MrBets.ai API",
    description="Backend API for MrBets.ai football prediction platform",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://mrbets.ai"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}

# Import and include routers
from app.routers import fixtures, predictions

app.include_router(fixtures.router, prefix="/fixtures", tags=["fixtures"])
app.include_router(predictions.router, prefix="/predictions", tags=["predictions"])

# Startup event
@app.on_event("startup")
async def startup_event():
    # Initialize connections
    pass

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    # Close connections
    pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 