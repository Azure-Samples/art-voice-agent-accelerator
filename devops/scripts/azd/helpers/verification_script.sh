#!/bin/bash
echo "🔍 Checking prerequisites..."

# Check each tool
for cmd in az azd docker python3 node jq; do
  if command -v $cmd &> /dev/null; then
    echo "✅ $cmd: $(command -v $cmd)"
  else
    echo "❌ $cmd: NOT FOUND"
  fi
done

# Check Azure login
if az account show &> /dev/null; then
  echo "✅ Azure CLI: Logged in"
else
  echo "❌ Azure CLI: Not logged in (run 'az login')"
fi

# Check azd auth
if azd auth login --check-status &> /dev/null; then
  echo "✅ Azure Developer CLI: Authenticated"
else
  echo "❌ Azure Developer CLI: Not authenticated (run 'azd auth login')"
fi

echo "🏁 Done!"