#!/bin/bash

# Simple script to deploy a zipped webapp to Azure using remote Oryx build

set -e

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <webapp-name> <resource-group> <zip-path>"
    exit 1
fi

WEBAPP_NAME="$1"
RESOURCE_GROUP="$2"
ZIP_PATH="$3"

if [ ! -f "$ZIP_PATH" ]; then
    echo "Error: ZIP file '$ZIP_PATH' not found."
    exit 1
fi

az webapp deploy \
    --resource-group "$RESOURCE_GROUP" \
    --name "$WEBAPP_NAME" \
    --src-path "$ZIP_PATH" \
    --type zip \
    --build-remote true

echo "Deployment triggered for $WEBAPP_NAME in $RESOURCE_GROUP using $ZIP_PATH"