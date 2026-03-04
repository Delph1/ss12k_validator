"""
Configuration settings for the SS12000 validator application.
"""

import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).parent
VERSIONS_DIR = BASE_DIR / "versions"

# API settings
API_TIMEOUT_SECONDS = 30
API_RETRIES = 1

# Validation limits
MIN_LIMIT = 1
MAX_LIMIT = 50
DEFAULT_LIMIT = 10

# Certificate settings
CERT_ALGORITHM = "RS256"  # RSA 256-bit signature (HS256 for HMAC alternative)
CERT_EXPIRY_DAYS = 365

# File paths
SCENARIOS_FILE = BASE_DIR / "scenarios.yaml"
OPENAPI_2020_FILE = VERSIONS_DIR / "2020" / "ss12000v2.yaml"
OPENAPI_2022_FILE = VERSIONS_DIR / "2022" / "openapi_ss12000_version2_1_0.yaml"

# Supported versions
SUPPORTED_VERSIONS = {
    "2020": str(OPENAPI_2020_FILE),
    "2022": str(OPENAPI_2022_FILE),
}

# CORS settings for web app (if needed)
CORS_ORIGINS = ["*"]

# Logging
DEBUG_MODE = os.getenv("DEBUG", "False").lower() == "true"
LOG_LEVEL = "DEBUG" if DEBUG_MODE else "INFO"

# Certificate secret (in production, load from environment)
CERT_SECRET_KEY = os.getenv("CERT_SECRET_KEY", "dev-secret-key-change-in-production")
