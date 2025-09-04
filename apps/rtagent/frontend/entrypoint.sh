#!/bin/sh
set -e

echo "🚀 Starting frontend container..."

# Replace placeholder with actual backend URL from environment variable
if [ -n "$BACKEND_URL" ]; then
    echo "📝 Replacing __BACKEND_URL__ with: $BACKEND_URL"
    find /app/dist -type f -name "*.js" -exec sed -i "s|__BACKEND_URL__|${BACKEND_URL}|g" {} \;
    find /app/dist -type f -name "*.html" -exec sed -i "s|__BACKEND_URL__|${BACKEND_URL}|g" {} \;
else
    echo "⚠️  BACKEND_URL environment variable not set, using placeholder"
fi

# Start the application
echo "🌟 Starting serve..."
exec "$@"
