"""
Schema loader for OpenAPI 3.0 specifications.
Converts OpenAPI YAML to JSON Schema for validation.
"""

import yaml
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from config import OPENAPI_2020_FILE, OPENAPI_2022_FILE

logger = logging.getLogger(__name__)


class SchemaLoader:
    """Load and cache OpenAPI schemas."""

    def __init__(self):
        self.schemas: Dict[str, Dict[str, Any]] = {}
        self._load_all_schemas()

    def _load_all_schemas(self):
        """Load both 2020 and 2022 schemas on initialization."""
        for version, file_path in [("2020", OPENAPI_2020_FILE), ("2022", OPENAPI_2022_FILE)]:
            try:
                self.schemas[version] = self._load_openapi_spec(file_path)
                logger.info(f"Loaded OpenAPI {version} schema from {file_path}")
            except Exception as e:
                logger.error(f"Failed to load OpenAPI {version} schema: {e}")
                self.schemas[version] = {}

    def _load_openapi_spec(self, file_path: Path) -> Dict[str, Any]:
        """Load OpenAPI YAML file and parse it."""
        if not file_path.exists():
            raise FileNotFoundError(f"OpenAPI spec file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            spec = yaml.safe_load(f)

        if not spec:
            raise ValueError(f"OpenAPI spec file is empty or invalid: {file_path}")

        return spec

    def get_schema(self, version: str) -> Dict[str, Any]:
        """Get the full OpenAPI schema for a specific version."""
        if version not in self.schemas:
            raise ValueError(f"Unsupported version: {version}. Supported: {list(self.schemas.keys())}")
        return self.schemas[version]

    def get_schema_component(self, version: str, component_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific schema component (e.g., 'Organisations', 'Persons').
        
        Args:
            version: OpenAPI version ('2020' or '2022')
            component_name: Name of the component to retrieve
            
        Returns:
            Schema component dict or None if not found
        """
        schema = self.get_schema(version)
        
        # OpenAPI 3.0 structure: components.schemas.<component_name>
        components = schema.get("components", {}).get("schemas", {})
        
        if component_name in components:
            return components[component_name]
        
        logger.warning(f"Component '{component_name}' not found in version {version}")
        return None

    def list_components(self, version: str) -> list:
        """List all available schema components for a version."""
        schema = self.get_schema(version)
        components = schema.get("components", {}).get("schemas", {})
        return list(components.keys())

    def resolve_schema_ref(self, version: str, ref: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a JSON Schema $ref (e.g., '#/components/schemas/Organisations').
        
        Args:
            version: OpenAPI version
            ref: Reference string (e.g., '#/components/schemas/Organisations')
            
        Returns:
            Resolved schema component or None
        """
        if not ref.startswith("#/"):
            logger.warning(f"Unsupported reference format: {ref}")
            return None

        # Parse reference path: #/components/schemas/ComponentName
        parts = ref.split("/")
        if len(parts) != 4 or parts[1] != "components" or parts[2] != "schemas":
            logger.warning(f"Invalid reference format: {ref}")
            return None

        component_name = parts[3]
        return self.get_schema_component(version, component_name)

    def export_as_json_schema(self, version: str, component_name: str) -> Optional[Dict[str, Any]]:
        """
        Export a component as JSON Schema Draft 7 compatible format.
        Handles OpenAPI-specific properties and converts to Standard JSON Schema.
        
        Args:
            version: OpenAPI version
            component_name: Name of the component
            
        Returns:
            JSON Schema compatible dict
        """
        component = self.get_schema_component(version, component_name)
        if not component:
            return None

        # Convert OpenAPI schema to JSON Schema
        # Remove OpenAPI-specific properties like 'readOnly', 'writeOnly', 'deprecated'
        json_schema = self._convert_openapi_to_json_schema(component, version)
        return json_schema

    def _convert_openapi_to_json_schema(self, schema: Dict[str, Any], version: str) -> Dict[str, Any]:
        """
        Recursively convert OpenAPI schema to JSON Schema.
        Removes OpenAPI-specific keywords.
        """
        if isinstance(schema, dict):
            # Create a new dict without OpenAPI-specific keys
            converted = {}

            for key, value in schema.items():
                # Skip OpenAPI-only properties
                if key in ["readOnly", "writeOnly", "xml", "externalDocs", "deprecated", "discriminator"]:
                    continue

                # Recursively convert nested objects
                if key == "properties" and isinstance(value, dict):
                    converted[key] = {k: self._convert_openapi_to_json_schema(v, version) for k, v in value.items()}
                elif key == "items" and isinstance(value, dict):
                    converted[key] = self._convert_openapi_to_json_schema(value, version)
                elif key == "allOf" and isinstance(value, list):
                    converted[key] = [self._convert_openapi_to_json_schema(v, version) for v in value]
                elif key == "oneOf" and isinstance(value, list):
                    converted[key] = [self._convert_openapi_to_json_schema(v, version) for v in value]
                elif key == "anyOf" and isinstance(value, list):
                    converted[key] = [self._convert_openapi_to_json_schema(v, version) for v in value]
                else:
                    converted[key] = value

            return converted
        elif isinstance(schema, list):
            return [self._convert_openapi_to_json_schema(item, version) for item in schema]
        else:
            return schema


# Global schema loader instance
_schema_loader: Optional[SchemaLoader] = None


def get_schema_loader() -> SchemaLoader:
    """Get or initialize the global schema loader."""
    global _schema_loader
    if _schema_loader is None:
        _schema_loader = SchemaLoader()
    return _schema_loader
