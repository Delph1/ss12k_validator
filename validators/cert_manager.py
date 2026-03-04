"""
Certificate manager for signing and verifying compliance certificates.
"""

import json
import logging
import hmac
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import os

from config import CERT_SECRET_KEY, CERT_EXPIRY_DAYS

logger = logging.getLogger(__name__)


class CertificateManager:
    """Manage SSL certificate generation, signing, and verification."""

    def __init__(self, secret_key: str = CERT_SECRET_KEY):
        """
        Initialize certificate manager.

        Args:
            secret_key: Secret key for HMAC signing
        """
        self.secret_key = secret_key.encode() if isinstance(secret_key, str) else secret_key

    def sign_certificate(self, test_results: Dict[str, Any], api_url: str, version: str) -> Dict[str, Any]:
        """
        Generate and sign a compliance certificate.

        Args:
            test_results: Test execution results from ScenarioRunner
            api_url: The API URL that was tested
            version: OpenAPI version ('2020' or '2022')

        Returns:
            Certificate dict with signature
        """
        # Extract scenario results
        scenarios_tested = list(test_results.get("scenarios", {}).keys())
        overall_status = test_results.get("overall_status", "unknown")

        # Create certificate payload
        certificate_payload = {
            "version": "1.0",
            "issued_at": datetime.utcnow().isoformat() + "Z",
            "expires_at": (datetime.utcnow() + timedelta(days=CERT_EXPIRY_DAYS)).isoformat() + "Z",
            "api_url": api_url,
            "ss12000_version": version,
            "overall_status": overall_status,
            "scenarios_tested": scenarios_tested,
            "test_results": test_results,
        }

        # Create signature
        payload_json = json.dumps(certificate_payload, sort_keys=True, separators=(",", ":"))
        signature = self._sign_payload(payload_json)

        certificate_payload["signature"] = signature

        logger.info(f"Generated compliance certificate for {api_url}")
        return certificate_payload

    def verify_certificate(self, certificate: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Verify the authenticity and integrity of a certificate.

        Args:
            certificate: Certificate dict (as returned by sign_certificate)

        Returns:
            Tuple of (is_valid: bool, details: dict)
        """
        # Extract signature
        provided_signature = certificate.pop("signature", None)
        if not provided_signature:
            return False, {"error": "No signature found in certificate"}

        # Recreate payload without signature
        payload_json = json.dumps(certificate, sort_keys=True, separators=(",", ":"))

        # Verify signature
        is_valid = self._verify_signature(payload_json, provided_signature)

        details = {
            "valid": is_valid,
            "api_url": certificate.get("api_url"),
            "ss12000_version": certificate.get("ss12000_version"),
            "overall_status": certificate.get("overall_status"),
            "issued_at": certificate.get("issued_at"),
            "expires_at": certificate.get("expires_at"),
            "scenarios_tested": certificate.get("scenarios_tested"),
        }

        if is_valid:
            # Check expiration
            expires_at = certificate.get("expires_at")
            if expires_at:
                try:
                    expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    if datetime.utcnow() > expires_dt:
                        details["valid"] = False
                        details["error"] = "Certificate has expired"
                        is_valid = False
                except ValueError:
                    pass

        if not is_valid:
            details["message"] = "Certificate signature is invalid or tampered"

        logger.info(f"Certificate verification result: {is_valid}")
        return is_valid, details

    def _sign_payload(self, payload: str) -> str:
        """
        Create HMAC-SHA256 signature of payload.

        Args:
            payload: JSON string to sign

        Returns:
            Base64-encoded signature
        """
        signature_bytes = hmac.new(
            self.secret_key, payload.encode("utf-8"), hashlib.sha256
        ).digest()
        return base64.b64encode(signature_bytes).decode("utf-8")

    def _verify_signature(self, payload: str, provided_signature: str) -> bool:
        """
        Verify HMAC-SHA256 signature.

        Args:
            payload: JSON string that was signed
            provided_signature: Base64-encoded signature to verify

        Returns:
            True if signature is valid
        """
        try:
            expected_signature = self._sign_payload(payload)
            # Use constant-time comparison to prevent timing attacks
            return hmac.compare_digest(expected_signature, provided_signature)
        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return False

    @staticmethod
    def export_certificate_to_file(certificate: Dict[str, Any], filename: str) -> str:
        """
        Export certificate to a JSON file.

        Args:
            certificate: Certificate dict
            filename: Path to save the certificate

        Returns:
            Path to the saved file
        """
        with open(filename, "w") as f:
            json.dump(certificate, f, indent=2)
        logger.info(f"Certificate exported to {filename}")
        return filename

    @staticmethod
    def load_certificate_from_file(filename: str) -> Optional[Dict[str, Any]]:
        """
        Load certificate from a JSON file.

        Args:
            filename: Path to certificate file

        Returns:
            Certificate dict or None if loading failed
        """
        try:
            with open(filename, "r") as f:
                certificate = json.load(f)
            return certificate
        except Exception as e:
            logger.error(f"Error loading certificate from {filename}: {e}")
            return None
