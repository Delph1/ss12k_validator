"""
Data extraction from API responses using JSONPath.
"""

import logging
import re
from typing import Any, Dict, Optional
from jsonpath_ng import parse

logger = logging.getLogger(__name__)


class DataExtractor:
    """Extract data from API responses using JSONPath and substitute variables in URLs."""

    @staticmethod
    def extract_value(data: Any, json_path: str) -> Optional[Any]:
        """
        Extract a value from data using JSONPath.

        Args:
            data: Data structure (dict, list, etc.)
            json_path: JSONPath expression (e.g., "data[0].id", "$.organisations[0].schoolTypes[0]")

        Returns:
            Extracted value or None if not found
        """
        try:
            # Normalize path: if it doesn't start with $, add it
            if not json_path.startswith("$"):
                json_path = "$." + json_path if not json_path.startswith(".") else "$" + json_path

            expr = parse(json_path)
            matches = expr.find(data)

            if matches:
                return matches[0].value
            else:
                logger.debug(f"JSONPath '{json_path}' found no matches in data")
                return None

        except (ValueError, KeyError, TypeError, AttributeError) as e:
            logger.error(f"Invalid JSONPath expression '{json_path}': {e}")
            return None
        except Exception as e:
            logger.error(f"Error extracting value from data with JSONPath '{json_path}': {e}")
            return None

    @staticmethod
    def substitute_variables(template: str, variables: Dict[str, Any]) -> str:
        """
        Substitute variables in a template string.

        Args:
            template: String with placeholders like {variable_name}
            variables: Dictionary of variable names and values

        Returns:
            String with variables substituted
        """
        if not variables:
            return template

        result = template
        for var_name, var_value in variables.items():
            placeholder = "{" + var_name + "}"
            result = result.replace(placeholder, str(var_value))

        # Check for any remaining placeholders
        remaining = re.findall(r"\{(\w+)\}", result)
        if remaining:
            logger.warning(f"Unresolved variables in template: {remaining}")

        return result

    @staticmethod
    def extract_multiple(data: Any, extraction_rules: Dict[str, str]) -> Dict[str, Any]:
        """
        Extract multiple values from data using a dictionary of extraction rules.

        Args:
            data: Data structure
            extraction_rules: Dict mapping output_name -> json_path
                             e.g., {"org_id": "data[0].id", "count": "pageToken"}

        Returns:
            Dict with extracted values, excluding None values
        """
        extracted = {}

        for output_name, json_path in extraction_rules.items():
            value = DataExtractor.extract_value(data, json_path)
            if value is not None:
                extracted[output_name] = value
                logger.debug(f"Extracted '{output_name}': {json_path} -> {value}")
            else:
                logger.warning(f"Failed to extract '{output_name}' from JSONPath: {json_path}")

        return extracted

    @staticmethod
    def parse_extraction_rules(extract_data: Dict[str, str] or None) -> Dict[str, str]:
        """
        Parse extraction rules from YAML format.
        
        Args:
            extract_data: Dict from YAML extractData section
            
        Returns:
            Validated extraction rules dict
        """
        if not extract_data:
            return {}

        if not isinstance(extract_data, dict):
            logger.warning(f"extractData must be a dict, got {type(extract_data)}")
            return {}

        return extract_data
