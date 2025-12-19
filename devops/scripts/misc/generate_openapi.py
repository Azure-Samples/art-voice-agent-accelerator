#!/usr/bin/env python3
"""
Generate OpenAPI JSON schema from FastAPI application
====================================================

This script generates the OpenAPI/Swagger JSON schema from the FastAPI app
and saves it to the docs/api/ directory for inclusion in MkDocs.

Usage:
    python scripts/generate_openapi.py
    python scripts/generate_openapi.py --output docs/api/openapi.json --pretty
"""

import sys
import os
import json
import argparse
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent / "apps" / "artagent" / "backend"
sys.path.insert(0, str(backend_dir))


def generate_openapi_json(output_path: str = "docs/api/openapi.json", pretty: bool = True):
    """
    Generate OpenAPI JSON from FastAPI application.

    Args:
        output_path: Path where to save the OpenAPI JSON file
        pretty: Whether to format JSON with indentation for readability
    """
    try:
        # Import the FastAPI app
        from main import app

        # Get the OpenAPI schema
        openapi_schema = app.openapi()

        # Ensure output directory exists
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Write the schema to file
        with open(output_file, "w", encoding="utf-8") as f:
            if pretty:
                json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
            else:
                json.dump(openapi_schema, f, ensure_ascii=False)

        print(f"✅ OpenAPI schema generated successfully: {output_file}")
        print(f"📊 Found {len(openapi_schema.get('paths', {}))} API paths")
        print(f"🏷️  API Title: {openapi_schema.get('info', {}).get('title', 'N/A')}")
        print(f"📝 API Version: {openapi_schema.get('info', {}).get('version', 'N/A')}")

        # Print summary of endpoints
        paths = openapi_schema.get("paths", {})
        if paths:
            print(f"\n📋 API Endpoints Summary:")
            for path, methods in paths.items():
                method_list = [
                    method.upper() for method in methods.keys() if method != "parameters"
                ]
                if method_list:
                    print(f"   {', '.join(method_list)} {path}")

        return output_file

    except ImportError as e:
        print(f"❌ Failed to import FastAPI app: {e}")
        print(
            "💡 Make sure you're running this from the project root and all dependencies are installed"
        )
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to generate OpenAPI schema: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Generate OpenAPI JSON schema from FastAPI application"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="docs/api/openapi.json",
        help="Output path for the OpenAPI JSON file (default: docs/api/openapi.json)",
    )
    parser.add_argument(
        "--pretty", action="store_true", help="Format JSON with indentation for readability"
    )
    parser.add_argument(
        "--minify", action="store_true", help="Generate minified JSON (opposite of --pretty)"
    )

    args = parser.parse_args()

    # Determine pretty formatting
    pretty = args.pretty if args.pretty else not args.minify

    print(f"🚀 Generating OpenAPI schema from FastAPI application...")
    print(f"📁 Output file: {args.output}")
    print(f"🎨 Pretty formatting: {'Yes' if pretty else 'No'}")

    generate_openapi_json(args.output, pretty)


if __name__ == "__main__":
    main()
