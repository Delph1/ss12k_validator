"""
Scenario executor for multi-step API testing with data extraction between steps.
"""

import logging
import requests
from typing import Any, Dict, List, Optional
from datetime import datetime
from requests.exceptions import RequestException, Timeout
import json

from validators.schema_loader import get_schema_loader
from validators.data_extractor import DataExtractor
from jsonschema import validate, ValidationError
from config import API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class StepResult:
    """Result of a single step execution."""

    def __init__(self, step_name: str, method: str, endpoint: str):
        self.step_name = step_name
        self.method = method
        self.endpoint = endpoint
        self.status = "pending"  # pending, pass, fail
        self.timestamp = None
        self.error_details = None
        self.extracted_data = {}
        self.http_status_code = None
        self.response_data = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert step result to dictionary."""
        return {
            "name": self.step_name,
            "method": self.method,
            "endpoint": self.endpoint,
            "status": self.status,
            "timestamp": self.timestamp,
            "error_details": self.error_details,
            "extracted_data": self.extracted_data,
            "http_status_code": self.http_status_code,
        }


class ScenarioResult:
    """Result of a complete scenario execution."""

    def __init__(self, scenario_id: str, scenario_name: str):
        self.scenario_id = scenario_id
        self.scenario_name = scenario_name
        self.status = "pending"  # pending, pass, fail
        self.steps: List[StepResult] = []
        self.started_at = None
        self.completed_at = None
        self.error_summary = None

    def add_step(self, step_result: StepResult):
        """Add a step result."""
        self.steps.append(step_result)

    def to_dict(self) -> Dict[str, Any]:
        """Convert scenario result to dictionary."""
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_summary": self.error_summary,
            "steps": [step.to_dict() for step in self.steps],
        }


class ScenarioExecutor:
    """Execute multi-step test scenarios against an API."""

    def __init__(self, api_base_url: str, version: str = "2022", custom_headers: Optional[Dict[str, str]] = None):
        """
        Initialize the scenario executor.

        Args:
            api_base_url: Base URL of the API to test (e.g., 'https://api.example.com')
            version: OpenAPI version ('2020' or '2022')
            custom_headers: Custom headers to include in all requests
        """
        self.api_base_url = api_base_url.rstrip("/")  # Remove trailing slash
        self.version = version
        self.custom_headers = custom_headers or {}
        self.schema_loader = get_schema_loader()
        self.session = requests.Session()
        self.extracted_variables = {}  # Store extracted data between steps

    def execute_scenario(self, scenario_def: Dict[str, Any]) -> ScenarioResult:
        """
        Execute a complete scenario with multiple steps.

        Args:
            scenario_def: Scenario definition dict from YAML
                         {
                             'id': 'c1',
                             'name': 'Organisations & Persons',
                             'description': '...',
                             'steps': [...]
                         }

        Returns:
            ScenarioResult with detailed status and step information
        """
        scenario_id = scenario_def.get("id", "unknown")
        scenario_name = scenario_def.get("name", "Unknown Scenario")

        result = ScenarioResult(scenario_id, scenario_name)
        result.started_at = datetime.utcnow().isoformat()

        steps = scenario_def.get("steps", [])
        if not steps:
            result.error_summary = "No steps defined in scenario"
            result.status = "fail"
            result.completed_at = datetime.utcnow().isoformat()
            return result

        # Reset extracted variables for this scenario
        self.extracted_variables = {}

        for step_index, step_def in enumerate(steps):
            try:
                step_result = self._execute_step(step_def, step_index)
                result.add_step(step_result)

                # If step failed, stop processing further steps
                if step_result.status == "fail":
                    result.status = "fail"
                    result.error_summary = f"Failed at step {step_index + 1}: {step_result.step_name}"
                    break

                # Extract data for next step if defined
                if step_result.extracted_data:
                    self.extracted_variables.update(step_result.extracted_data)
                    logger.debug(f"Extracted variables: {self.extracted_variables}")

            except Exception as e:
                logger.error(f"Unexpected error in step {step_index + 1}: {e}")
                step_result = StepResult(
                    step_def.get("name", f"Step {step_index + 1}"),
                    step_def.get("method", "UNKNOWN"),
                    step_def.get("endpoint", ""),
                )
                step_result.status = "fail"
                step_result.error_details = str(e)
                result.add_step(step_result)
                result.status = "fail"
                result.error_summary = f"Unexpected error: {e}"
                break

        # If no step failed, mark scenario as pass
        if result.status == "pending":
            result.status = "pass"

        result.completed_at = datetime.utcnow().isoformat()
        return result

    def _execute_step(self, step_def: Dict[str, Any], step_index: int) -> StepResult:
        """
        Execute a single step.

        Args:
            step_def: Step definition from YAML
            step_index: Index of this step (for logging/errors)

        Returns:
            StepResult with status and extracted data
        """
        step_name = step_def.get("name", f"Step {step_index + 1}")
        method = step_def.get("method", "GET").upper()
        endpoint_template = step_def.get("endpoint", "")
        expected_schema = step_def.get("expectedSchema")
        extract_rules = step_def.get("extractData", {})

        step_result = StepResult(step_name, method, endpoint_template)

        # Substitute variables in endpoint
        endpoint = DataExtractor.substitute_variables(endpoint_template, self.extracted_variables)
        step_result.endpoint = endpoint  # Update with actual endpoint

        # Build full URL
        full_url = self._build_url(endpoint)

        # Prepare headers
        headers = self._prepare_headers(step_def.get("headers", {}))

        try:
            # Make API request
            logger.info(f"[Step {step_index + 1}] {method} {full_url}")
            response = self.session.request(
                method=method,
                url=full_url,
                headers=headers,
                timeout=API_TIMEOUT_SECONDS,
            )

            step_result.http_status_code = response.status_code

            # Check HTTP status
            if response.status_code < 200 or response.status_code >= 300:
                step_result.status = "fail"
                step_result.error_details = (
                    f"HTTP {response.status_code}: {response.text[:500]}"  # First 500 chars
                )
                logger.warning(f"[Step {step_index + 1}] Failed with HTTP {response.status_code}")
                return step_result

            # Parse response JSON
            try:
                response_data = response.json()
                step_result.response_data = response_data
            except json.JSONDecodeError as e:
                step_result.status = "fail"
                step_result.error_details = f"Invalid JSON response: {str(e)}"
                logger.warning(f"[Step {step_index + 1}] Invalid JSON response")
                return step_result

            # Validate response against schema if specified
            if expected_schema:
                validation_error = self._validate_response(response_data, expected_schema)
                if validation_error:
                    step_result.status = "fail"
                    step_result.error_details = validation_error
                    logger.warning(f"[Step {step_index + 1}] Validation error: {validation_error}")
                    return step_result

            # Extract data if specified
            if extract_rules:
                try:
                    extracted = DataExtractor.extract_multiple(response_data, extract_rules)
                    step_result.extracted_data = extracted

                    # Check if all expected extractions succeeded
                    for key in extract_rules:
                        if key not in extracted:
                            step_result.status = "fail"
                            step_result.error_details = f"Failed to extract required field: {key} via JSONPath: {extract_rules[key]}"
                            logger.warning(
                                f"[Step {step_index + 1}] Failed to extract {key} from response"
                            )
                            return step_result

                except Exception as e:
                    step_result.status = "fail"
                    step_result.error_details = f"Error extracting data: {str(e)}"
                    logger.warning(f"[Step {step_index + 1}] Data extraction error: {e}")
                    return step_result

            # Step passed
            step_result.status = "pass"
            logger.info(f"[Step {step_index + 1}] Passed")

        except Timeout:
            step_result.status = "fail"
            step_result.error_details = f"Request timeout after {API_TIMEOUT_SECONDS} seconds"
            logger.error(f"[Step {step_index + 1}] Timeout")

        except RequestException as e:
            step_result.status = "fail"
            step_result.error_details = f"Network error: {str(e)}"
            logger.error(f"[Step {step_index + 1}] Network error: {e}")

        return step_result

    def _build_url(self, endpoint: str) -> str:
        """Build full URL from base URL and endpoint."""
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        return self.api_base_url + endpoint

    def _prepare_headers(self, step_headers: Dict[str, str]) -> Dict[str, str]:
        """Merge custom headers with step-specific headers."""
        headers = {**self.custom_headers}
        headers.update(step_headers)
        # Ensure Content-Type is set for requests
        if "Content-Type" not in headers:
            headers["Accept"] = "application/json"
        return headers

    def _validate_response(self, response_data: Any, schema_name: str) -> Optional[str]:
        """
        Validate response against OpenAPI schema.

        Args:
            response_data: The API response data
            schema_name: Name of the schema component to validate against

        Returns:
            Error message if validation fails, None if validation passes
        """
        try:
            # Get the schema component
            schema = self.schema_loader.get_schema_component(self.version, schema_name)
            if not schema:
                return f"Schema component not found: {schema_name}"

            # Convert OpenAPI to JSON Schema
            json_schema = self.schema_loader.export_as_json_schema(self.version, schema_name)
            if not json_schema:
                return f"Could not export schema for validation: {schema_name}"

            # Validate
            validate(instance=response_data, schema=json_schema)
            return None  # Validation passed

        except ValidationError as e:
            # Format validation error message
            path = ".".join(str(p) for p in e.path) if e.path else "root"
            return f"Validation error at '{path}': {e.message}"

        except Exception as e:
            return f"Validation error: {str(e)}"


class ScenarioRunner:
    """Run multiple scenarios and aggregate results."""

    def __init__(self, api_base_url: str, version: str = "2022", custom_headers: Optional[Dict[str, str]] = None):
        self.executor = ScenarioExecutor(api_base_url, version, custom_headers)
        self.results: Dict[str, ScenarioResult] = {}

    def run_scenarios(self, scenarios: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Run a list of scenarios.

        Args:
            scenarios: List of scenario definitions

        Returns:
            Aggregated results dict
        """
        self.results = {}
        all_passed = True

        for scenario_def in scenarios:
            scenario_id = scenario_def.get("id", "unknown")
            logger.info(f"Running scenario: {scenario_id}")

            result = self.executor.execute_scenario(scenario_def)
            self.results[scenario_id] = result

            if result.status != "pass":
                all_passed = False

        return {
            "overall_status": "pass" if all_passed else "fail",
            "scenarios": {sid: result.to_dict() for sid, result in self.results.items()},
            "total_scenarios": len(scenarios),
            "passed_scenarios": sum(1 for r in self.results.values() if r.status == "pass"),
        }
