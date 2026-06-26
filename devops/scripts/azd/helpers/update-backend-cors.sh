#!/bin/bash
# Update backend Container Apps ingress CORS for the deployed frontend origin.

set -euo pipefail

usage() {
    cat <<EOF
Usage: $0 -g <resource-group> -b <backend-container-app> -f <frontend-fqdn-or-origin>

Options:
  -g, --resource-group       Azure resource group
  -b, --backend-app          Backend Container App name
  -f, --frontend             Frontend Container App FQDN or origin URL
  -h, --help                 Show this help
EOF
}

resource_group=""
backend_app=""
frontend=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -g|--resource-group)
            resource_group="$2"
            shift 2
            ;;
        -b|--backend-app)
            backend_app="$2"
            shift 2
            ;;
        -f|--frontend)
            frontend="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "$resource_group" || -z "$backend_app" || -z "$frontend" ]]; then
    echo "Missing required arguments." >&2
    usage >&2
    exit 2
fi

case "$frontend" in
    http://*|https://*) frontend_origin="$frontend" ;;
    *) frontend_origin="https://${frontend}" ;;
esac

backend_id=$(az containerapp show \
    --resource-group "$resource_group" \
    --name "$backend_app" \
    --query id \
    --output tsv)

body_file=$(mktemp)
trap 'rm -f "$body_file"' EXIT

cat > "$body_file" <<EOF
{
  "properties": {
    "configuration": {
      "ingress": {
        "stickySessions": {
          "affinity": "sticky"
        },
        "corsPolicy": {
          "allowedOrigins": ["$frontend_origin"],
          "allowedMethods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
          "allowedHeaders": ["Content-Type", "Authorization", "X-Requested-With", "Accept", "Cache-Control"],
          "exposeHeaders": ["Content-Length", "Content-Range"],
          "allowCredentials": true,
          "maxAge": 86400
        }
      }
    }
  }
}
EOF

az rest \
    --method PATCH \
    --url "https://management.azure.com${backend_id}?api-version=2024-03-01" \
    --body @"$body_file" \
    --output none

echo "Backend CORS policy allows: $frontend_origin"