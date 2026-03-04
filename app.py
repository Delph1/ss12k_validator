import logging
import yaml
import json
import tempfile
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl, field_validator

from config import SCENARIOS_FILE, CORS_ORIGINS, SUPPORTED_VERSIONS, DEBUG_MODE, LOG_LEVEL
from validators import ScenarioRunner, CertificateManager, get_schema_loader

# Configure logging
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================================
# Lifespan Event Handler
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("SS12000 API Validator starting up...")
    logger.info(f"Debug mode: {DEBUG_MODE}")
    logger.info(f"Log level: {LOG_LEVEL}")

    try:
        schema_loader = get_schema_loader()
        logger.info(f"Schema versions available: {list(schema_loader.schemas.keys())}")
    except Exception as e:
        logger.warning(f"Error initializing schema loader: {e}")

    scenarios = load_scenarios()
    logger.info(f"Scenarios available: {list(scenarios.keys())}")

    yield  # App runs here

    # Shutdown
    logger.info("SS12000 API Validator shutting down")


# FastAPI app initialization
app = FastAPI(
    title="SS12000 API Validator",
    description="Validate SS12000 API compliance and generate compliance certificates",
    version="1.0.0",
    debug=DEBUG_MODE,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ============================================================================
# Pydantic Models
# ============================================================================


class Header(BaseModel):
    """HTTP header key-value pair."""

    key: str
    value: str

    @field_validator("key")
    @classmethod
    def key_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Header key cannot be empty")
        return v.strip()


class ValidationRequest(BaseModel):
    """Request model for API validation."""

    api_url: HttpUrl
    version: str = "2022"
    scenarios: List[str]  # List of scenario IDs to run
    headers: List[Header] = []
    limit: int = 10

    @field_validator("version")
    @classmethod
    def version_must_be_supported(cls, v):
        if v not in SUPPORTED_VERSIONS:
            raise ValueError(f"Unsupported version: {v}. Supported: {list(SUPPORTED_VERSIONS.keys())}")
        return v

    @field_validator("limit")
    @classmethod
    def limit_in_range(cls, v):
        if not (1 <= v <= 50):
            raise ValueError("Limit must be between 1 and 50")
        return v


class CertificateVerificationResponse(BaseModel):
    """Response model for certificate verification."""

    valid: bool
    api_url: Optional[str] = None
    ss12000_version: Optional[str] = None
    overall_status: Optional[str] = None
    issued_at: Optional[str] = None
    expires_at: Optional[str] = None
    scenarios_tested: Optional[List[str]] = None
    message: Optional[str] = None


# ============================================================================
# Helper Functions
# ============================================================================


def load_scenarios() -> Dict[str, Dict]:
    """
    Load scenarios from YAML file.

    Returns:
        Dict mapping scenario_id -> scenario_definition
    """
    if not SCENARIOS_FILE.exists():
        logger.warning(f"Scenarios file not found: {SCENARIOS_FILE}")
        return {}

    try:
        with open(SCENARIOS_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        scenarios = data.get("scenarios", {})
        logger.info(f"Loaded {len(scenarios)} scenarios from {SCENARIOS_FILE}")
        return scenarios

    except Exception as e:
        logger.error(f"Error loading scenarios: {e}")
        return {}


def get_scenario_list_for_response() -> List[Dict]:
    """
    Format scenarios for API response.

    Returns:
        List of scenario summaries for dropdown/selection
    """
    scenarios = load_scenarios()
    return [
        {
            "id": scenario_id,
            "name": scenario_def.get("name", scenario_id),
            "description": scenario_def.get("description", ""),
        }
        for scenario_id, scenario_def in scenarios.items()
    ]


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/")
async def root():
    """Serve the main HTML form."""
    html_file = templates_dir / "index.html"
    if html_file.exists():
        return FileResponse(str(html_file), media_type="text/html")
    return {"message": "Welcome to SS12000 API Validator"}


@app.get("/api/scenarios")
async def get_scenarios():
    """Get list of available scenarios for the form dropdown."""
    return {"scenarios": get_scenario_list_for_response()}


@app.get("/api/versions")
async def get_versions():
    """Get list of supported SS12000 versions."""
    return {"versions": list(SUPPORTED_VERSIONS.keys())}


@app.post("/api/validate")
async def validate_api(request: ValidationRequest):
    """
    Execute validation scenarios against the provided API.

    Args:
        request: ValidationRequest containing API URL, scenarios to run, headers, and limit

    Returns:
        JSON response with test results and certificate (if all tests pass)
    """
    try:
        logger.info(f"Starting validation for {request.api_url}")

        # Load all scenarios and filter to requested ones
        all_scenarios = load_scenarios()
        if not all_scenarios:
            raise HTTPException(status_code=400, detail="No scenarios defined")

        scenarios_to_run = []
        missing_scenarios = []

        for scenario_id in request.scenarios:
            if scenario_id in all_scenarios:
                scenario_def = all_scenarios[scenario_id].copy()
                scenario_def["id"] = scenario_id
                scenarios_to_run.append(scenario_def)
            else:
                missing_scenarios.append(scenario_id)

        if missing_scenarios:
            raise HTTPException(
                status_code=400,
                detail=f"Scenarios not found: {missing_scenarios}",
            )

        if not scenarios_to_run:
            raise HTTPException(status_code=400, detail="No valid scenarios to run")

        # Convert headers to dict
        headers_dict = {header.key: header.value for header in request.headers}
        if request.limit:
            headers_dict["Limit"] = str(request.limit)

        # Run scenarios
        runner = ScenarioRunner(
            api_base_url=str(request.api_url),
            version=request.version,
            custom_headers=headers_dict,
        )

        test_results = runner.run_scenarios(scenarios_to_run)
        logger.info(f"Validation completed with status: {test_results['overall_status']}")

        # Generate certificate if all tests pass
        certificate = None
        if test_results["overall_status"] == "pass":
            cert_manager = CertificateManager()
            certificate = cert_manager.sign_certificate(
                test_results=test_results,
                api_url=str(request.api_url),
                version=request.version,
            )
            logger.info("Certificate generated for passing validation")

        return {
            "status": test_results["overall_status"],
            "test_results": test_results,
            "certificate": certificate,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during validation: {e}")
        raise HTTPException(status_code=500, detail=f"Validation error: {str(e)}")


@app.post("/api/verify-certificate")
async def verify_certificate(file: UploadFile = File(...)):
    """
    Upload and verify a compliance certificate.

    Args:
        file: Certificate file (JSON)

    Returns:
        Verification result with certificate details
    """
    try:
        logger.info(f"Verifying certificate from file: {file.filename}")

        # Read uploaded file
        content = await file.read()
        certificate = json.loads(content.decode("utf-8"))

        # Verify certificate
        cert_manager = CertificateManager()
        is_valid, details = cert_manager.verify_certificate(certificate)

        response = CertificateVerificationResponse(
            valid=is_valid,
            api_url=details.get("api_url"),
            ss12000_version=details.get("ss12000_version"),
            overall_status=details.get("overall_status"),
            issued_at=details.get("issued_at"),
            expires_at=details.get("expires_at"),
            scenarios_tested=details.get("scenarios_tested"),
            message=details.get("message") or details.get("error"),
        )

        logger.info(f"Certificate verification result: {is_valid}")
        return response

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid certificate format (must be valid JSON)")
    except Exception as e:
        logger.error(f"Error verifying certificate: {e}")
        raise HTTPException(status_code=500, detail=f"Verification error: {str(e)}")


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8088,
        reload=DEBUG_MODE,
        log_level=LOG_LEVEL.lower(),
    )
