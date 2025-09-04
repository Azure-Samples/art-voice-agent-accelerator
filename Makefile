############################################################
# Makefile for gbb-ai-audio-agent
# Purpose: Manage code quality, environment, and app tasks
# Each target is documented for clarity and maintainability
############################################################

# Python interpreter to use
PYTHON_INTERPRETER = python
# Conda environment name (default: audioagent)
CONDA_ENV ?= audioagent
# Ensure current directory is in PYTHONPATH
export PYTHONPATH=$(PWD):$PYTHONPATH;
SCRIPTS_DIR = apps/rtagent/scripts
SCRIPTS_LOAD_DIR = tests/load
PHONE = +18165019907


# Install pre-commit and pre-push git hooks
set_up_precommit_and_prepush:
	pre-commit install -t pre-commit
	pre-commit install -t pre-push


# Run all code quality checks (formatting, linting, typing, security, etc.)
check_code_quality:
	# Ruff: auto-fix common Python code issues
	@pre-commit run ruff --all-files

	# Black: enforce code formatting
	@pre-commit run black --all-files

	# isort: sort and organize imports
	@pre-commit run isort --all-files

	# flake8: linting
	@pre-commit run flake8 --all-files

	# mypy: static type checking
	@pre-commit run mypy --all-files

	# check-yaml: validate YAML files
	@pre-commit run check-yaml --all-files

	# end-of-file-fixer: ensure newline at EOF
	@pre-commit run end-of-file-fixer --all-files

	# trailing-whitespace: remove trailing whitespace
	@pre-commit run trailing-whitespace --all-files

	# interrogate: check docstring coverage
	@pre-commit run interrogate --all-files

	# bandit: scan for Python security issues
	bandit -c pyproject.toml -r .


# Auto-fix code quality issues (formatting, imports, lint)
fix_code_quality:
	# Only use in development, not production
	black .
	isort .
	ruff --fix .


# Run unit tests with coverage report
run_unit_tests:
	$(PYTHON_INTERPRETER) -m pytest --cov=my_module --cov-report=term-missing --cov-config=.coveragerc


# Convenience targets for full code/test quality cycle
check_and_fix_code_quality: fix_code_quality check_code_quality
check_and_fix_test_quality: run_unit_tests


# ANSI color codes for pretty output
RED = \033[0;31m
NC = \033[0m # No Color
GREEN = \033[0;32m


# Helper function: print section titles in green
define log_section
	@printf "\n${GREEN}--> $(1)${NC}\n\n"
endef


# Create the conda environment from environment.yaml
create_conda_env:
	@echo "Creating conda environment"
	conda env create -f environment.yaml


# Activate the conda environment
activate_conda_env:
	@echo "Creating conda environment"
	conda activate $(CONDA_ENV)


# Remove the conda environment
remove_conda_env:
	@echo "Removing conda environment"
	conda env remove --name $(CONDA_ENV)

start_backend:
	python $(SCRIPTS_DIR)/start_backend.py

start_frontend:
	bash $(SCRIPTS_DIR)/start_frontend.sh

start_tunnel:
	bash $(SCRIPTS_DIR)/start_devtunnel_host.sh

generate_audio:
	python $(SCRIPTS_LOAD_DIR)/utils/audio_generator.py --max-turns 5

# WebSocket endpoint load testing (current approach)
# DEPLOYED_URL = 
LOCAL_URL = localhost:8010
run_load_test:
	@echo "Running load test (override with e.g. make run_load_test URL=wss://host TURNS=10 CONVERSATIONS=50 CONCURRENT=5 RECORD=1 RECORD_RATE=0.1 EXTRA_ARGS='--verbose')"
	$(eval URL ?= wss://$(LOCAL_URL)/api/v1/media/stream)
	$(eval TURNS ?= 5)
	$(eval CONVERSATIONS ?= 20)
	$(eval CONCURRENT ?= 20)
	$(eval RECORD ?= )
	$(eval RECORD_RATE ?= 0.2)
	@python $(SCRIPTS_LOAD_DIR)/detailed_statistics_analyzer.py \
		--url $(URL) \
		--turns $(TURNS) \
		--conversations $(CONVERSATIONS) \
		--concurrent $(CONCURRENT) \
		$(if $(RECORD),--record) \
		$(if $(RECORD_RATE),--record-rate $(RECORD_RATE)) \
		$(EXTRA_ARGS)

# Conversation Analysis Targets
list-conversations:
	python $(SCRIPTS_LOAD_DIR)/conversation_playback.py --list

FILE_TO_ANALYZE = tests\load\results\recorded_conversations_20250829_085350.json

playback-conversations:
	python $(SCRIPTS_LOAD_DIR)/conversation_playback.py --conversation-file $(FILE_TO_ANALYZE)

# ACS call load testing (real phone calls - requires phone numbers)
run_acs_call_load_test:
	@echo "⚠️  WARNING: This will initiate real ACS phone calls!"
	@echo "⚠️  Make sure you have test numbers and sufficient credits!"
	@echo "⚠️  Press Ctrl+C to cancel in the next 5 seconds..."
	@sleep 5
	python $(SCRIPTS_LOAD_DIR)/acs_call_load_test.py

# Development ACS testing (single call to specified phone)
run_acs_dev_test:
	python $(SCRIPTS_LOAD_DIR)/acs_call_load_test_dev.py --environment dev --target-phones $(PHONE)

# Staging ACS testing (5 calls)
run_acs_staging_test:
	python $(SCRIPTS_LOAD_DIR)/acs_call_load_test_dev.py --environment staging --target-phones $(PHONE)

############################################################
# Azure App Service Deployment Artifacts
# Purpose: Generate build artifacts and deployment packages
############################################################

# Directories and files to include in backend deployment
BACKEND_DIRS = src utils apps/rtagent/backend
BACKEND_FILES = requirements.txt .deploy/runtime.txt .deploy/.python-version
EXCLUDE_PATTERNS = __pycache__ *.pyc .pytest_cache *.log .coverage htmlcov .DS_Store .git node_modules *.tmp *.temp dist .env
DEPLOY_DIR = .deploy/backend
TIMESTAMP = $(shell date +%Y%m%d_%H%M%S)
GIT_HASH = $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
DEPLOY_ZIP = backend_deployment_$(GIT_HASH)_$(TIMESTAMP).zip

# Generate frontend deployment artifacts
generate_frontend_deployment:
	@echo "🏗️  Generating Frontend Deployment Artifacts"
	@echo "=============================================="
	@echo ""

	# Clean and create deployment directory
	@echo "🧹 Cleaning previous frontend deployment artifacts..."
	@rm -rf .deploy/frontend
	@mkdir -p .deploy/frontend

	# Copy frontend directory
	@echo "📦 Copying frontend directory..."
	@if [ -d "apps/rtagent/frontend" ]; then \
		rsync -av --exclude='node_modules' --exclude='.env' --exclude='.DS_Store' apps/rtagent/frontend/ .deploy/frontend/; \
	else \
		echo "   ❌ Error: apps/rtagent/frontend directory not found."; \
		exit 1; \
	fi

	# Create deployment zip
	@FRONTEND_DEPLOY_ZIP=frontend_deployment_$(GIT_HASH)_$(TIMESTAMP).zip; \
	echo "📦 Creating deployment zip: $$FRONTEND_DEPLOY_ZIP"; \
	cd .deploy/frontend && zip -rq "../$$FRONTEND_DEPLOY_ZIP" .; \
	echo ""; \
	echo "✅ Frontend deployment artifacts generated successfully!"; \
	echo "📊 Deployment Summary:"; \
	echo "   📁 Artifacts directory: .deploy/frontend"; \
	echo "   📦 Deployment package: .deploy/$$FRONTEND_DEPLOY_ZIP"; \
	echo "   📏 Package size: $$(du -h .deploy/$$FRONTEND_DEPLOY_ZIP | cut -f1)"; \
	echo "   🔢 Git commit: $(GIT_HASH)"; \
	echo "   🕐 Timestamp: $(TIMESTAMP)"; \
	echo ""; \
	echo "🚀 Ready for Azure App Service deployment!"

# Generate backend deployment artifacts
generate_backend_deployment:
	@echo "🏗️  Generating Backend Deployment Artifacts"
	@echo "=============================================="
	@echo ""
	# Clean and create deployment directory
	@echo "🧹 Cleaning previous deployment artifacts..."
	@rm -rf $(DEPLOY_DIR)
	@mkdir -p $(DEPLOY_DIR)
	
	# Copy backend directories with exclusions
	@echo "📦 Copying backend directories..."
	@echo "$(EXCLUDE_PATTERNS)" | tr ' ' '\n' > .deploy-excludes.tmp
	@for dir in $(BACKEND_DIRS); do \
		if [ -d "$$dir" ]; then \
			echo "   Copying: $$dir"; \
			rsync -av --exclude-from=.deploy-excludes.tmp "$$dir/" "$(DEPLOY_DIR)/$$dir/"; \
		else \
			echo "   ⚠️  Warning: Directory not found: $$dir"; \
		fi \
	done
	@rm -f .deploy-excludes.tmp
	
	# Copy required files
	@echo "📄 Copying required files..."
	@for file in $(BACKEND_FILES); do \
		if [ -f "$$file" ]; then \
			echo "   Copying: $$file"; \
			mkdir -p "$(DEPLOY_DIR)/$$(dirname "$$file")"; \
			cp "$$file" "$(DEPLOY_DIR)/$$file"; \
		else \
			echo "   ❌ Error: Required file missing: $$file"; \
			exit 1; \
		fi \
	done

	# Copy runtime files to root for Oryx detection, create if missing
	@echo "🐍 Setting up Python runtime configuration..."
	@if [ -f ".deploy/runtime.txt" ]; then \
		cp ".deploy/runtime.txt" "$(DEPLOY_DIR)/runtime.txt"; \
		echo "   ✅ Copied runtime.txt to deployment root"; \
	else \
		echo "python-3.11" > "$(DEPLOY_DIR)/runtime.txt"; \
		echo "   ⚠️  .deploy/runtime.txt not found, created default runtime.txt"; \
	fi
	@if [ -f ".deploy/.python-version" ]; then \
		cp ".deploy/.python-version" "$(DEPLOY_DIR)/.python-version"; \
		echo "   ✅ Copied .python-version to deployment root"; \
	else \
		echo "3.11" > "$(DEPLOY_DIR)/.python-version"; \
		echo "   ⚠️  .deploy/.python-version not found, created default .python-version"; \
	fi
	
	# Create deployment zip
	@echo "📦 Creating deployment zip: $(DEPLOY_ZIP)"
	@cd $(DEPLOY_DIR) && zip -rq "../$(DEPLOY_ZIP)" . \
		$(foreach pattern,$(EXCLUDE_PATTERNS),-x "$(pattern)")
	
	# Show deployment summary
	@echo ""
	@echo "✅ Backend deployment artifacts generated successfully!"
	@echo "📊 Deployment Summary:"
	@echo "   📁 Artifacts directory: $(DEPLOY_DIR)"
	@echo "   📦 Deployment package: .deploy/$(DEPLOY_ZIP)"
	@echo "   📏 Package size: $$(du -h .deploy/$(DEPLOY_ZIP) | cut -f1)"
	@echo "   🔢 Git commit: $(GIT_HASH)"
	@echo "   🕐 Timestamp: $(TIMESTAMP)"
	@echo ""
	@echo "🚀 Ready for Azure App Service deployment!"


# Clean deployment artifacts
clean_deployment_artifacts:
	@echo "🧹 Cleaning deployment artifacts..."
	@rm -rf .deploy/backend
	@rm -f .deploy/backend_deployment_*.zip
	@echo "✅ Deployment artifacts cleaned"


# Show deployment package info
show_deployment_info:
	@echo "📊 Deployment Package Information"
	@echo "================================="
	@echo ""
	@if [ -d "$(DEPLOY_DIR)" ]; then \
		echo "📁 Artifacts directory: $(DEPLOY_DIR)"; \
		echo "📄 Directory contents:"; \
		find $(DEPLOY_DIR) -type f | head -20 | sed 's/^/   /'; \
		echo ""; \
	else \
		echo "❌ No deployment artifacts found. Run 'make generate_backend_deployment' first."; \
	fi
	@echo "📦 Available deployment packages:"
	@ls -la .deploy/backend_deployment_*.zip 2>/dev/null | sed 's/^/   /' || echo "   No deployment packages found"


# Run pylint on all Python files (excluding tests), output to report file
run_pylint:
	@echo "Running linter"
	find . -type f -name "*.py" ! -path "./tests/*" | xargs pylint -disable=logging-fstring-interpolation > utils/pylint_report/pylint_report.txt


############################################################
# Terraform State to Environment File
# Purpose: Extract values from Terraform remote state and create local .env file
############################################################

# Environment variables for Terraform state extraction
AZURE_ENV_NAME ?= dev
# Automatically set AZURE_SUBSCRIPTION_ID from Azure CLI if not provided
AZURE_SUBSCRIPTION_ID ?= $(shell az account show --query id -o tsv 2>/dev/null)
TF_DIR = infra/terraform
ENV_FILE = .env.$(AZURE_ENV_NAME)

# Generate environment file from Terraform remote state outputs
generate_env_from_terraform:
	@echo "🔧 Generating Environment File from Terraform State"
	@echo "============================================================"
	@./devops/scripts/generate-env-from-terraform.sh $(AZURE_ENV_NAME) $(AZURE_SUBSCRIPTION_ID) generate

# Check if Terraform is initialized (now handled by script)
check_terraform_initialized:
	@echo "⚠️  Note: Terraform initialization check is now handled by the generation script"

# Show current environment file (if it exists)
show_env_file:
	@./devops/scripts/generate-env-from-terraform.sh $(AZURE_ENV_NAME) $(AZURE_SUBSCRIPTION_ID) show

# Extract sensitive values from Azure Key Vault and update environment file
update_env_with_secrets:
	@echo "🔧 Updating Environment File with Key Vault Secrets"
	@echo "============================================================"
	@./devops/scripts/generate-env-from-terraform.sh $(AZURE_ENV_NAME) $(AZURE_SUBSCRIPTION_ID) update-secrets

# Generate environment file from Terraform remote state outputs (PowerShell)
generate_env_from_terraform_ps:
	@echo "🔧 Generating Environment File from Terraform State (PowerShell)"
	@echo "============================================================"
	@powershell -ExecutionPolicy Bypass -File devops/scripts/Generate-EnvFromTerraform.ps1 -EnvironmentName $(AZURE_ENV_NAME) -SubscriptionId $(AZURE_SUBSCRIPTION_ID) -Action generate

# Show current environment file (PowerShell)
show_env_file_ps:
	@powershell -ExecutionPolicy Bypass -File devops/scripts/Generate-EnvFromTerraform.ps1 -EnvironmentName $(AZURE_ENV_NAME) -SubscriptionId $(AZURE_SUBSCRIPTION_ID) -Action show

# Update environment file with Key Vault secrets (PowerShell)
update_env_with_secrets_ps:
	@echo "🔧 Updating Environment File with Key Vault Secrets (PowerShell)"
	@echo "============================================================"
	@powershell -ExecutionPolicy Bypass -File devops/scripts/Generate-EnvFromTerraform.ps1 -EnvironmentName $(AZURE_ENV_NAME) -SubscriptionId $(AZURE_SUBSCRIPTION_ID) -Action update-secrets

# Deploy a user-provided directory to Azure Web App using Azure CLI
# Usage: make deploy_to_webapp WEBAPP_NAME=<your-app-name> DEPLOY_DIR=<directory-to-deploy>
deploy_to_webapp:
	@if [ -z "$(WEBAPP_NAME)" ]; then \
		if [ -f ".env" ]; then \
			WEBAPP_NAME_ENV=$$(grep '^BACKEND_APP_SERVICE_URL=' .env | cut -d'=' -f2 | sed 's|https\?://||;s|/.*||'); \
			if [ -n "$$WEBAPP_NAME_ENV" ]; then \
				echo "ℹ️  Using BACKEND_APP_SERVICE_URL from .env: $$WEBAPP_NAME_ENV"; \
				WEBAPP_NAME=$$WEBAPP_NAME_ENV; \
			else \
				echo "❌ WEBAPP_NAME not set and BACKEND_APP_SERVICE_URL not found in .env"; \
				exit 1; \
			fi \
		else \
			echo "❌ WEBAPP_NAME not set and .env file not found"; \
			exit 1; \
		fi \
	fi
	@if [ -z "$(DEPLOY_DIR)" ]; then \
		echo "❌ Usage: make deploy_to_webapp WEBAPP_NAME=<your-app-name> DEPLOY_DIR=<directory-to-deploy> AZURE_RESOURCE_GROUP=<your-resource-group>"; \
		exit 1; \
	fi
	@if [ -z "$(AZURE_RESOURCE_GROUP)" ]; then \
		if [ -f ".env" ]; then \
			RESOURCE_GROUP_ENV=$$(grep '^AZURE_RESOURCE_GROUP=' .env | cut -d'=' -f2); \
			if [ -n "$$RESOURCE_GROUP_ENV" ]; then \
				echo "ℹ️  Using AZURE_RESOURCE_GROUP from .env: $$RESOURCE_GROUP_ENV"; \
				AZURE_RESOURCE_GROUP=$$RESOURCE_GROUP_ENV; \
			else \
				echo "❌ AZURE_RESOURCE_GROUP not set and not found in .env"; \
				exit 1; \
			fi \
		else \
			echo "❌ AZURE_RESOURCE_GROUP not set and .env file not found"; \
			exit 1; \
		fi \
	fi
	@echo "🚀 Deploying '$(DEPLOY_DIR)' to Azure Web App '$(WEBAPP_NAME)' in resource group '$(AZURE_RESOURCE_GROUP)'"
	@echo "⏳ Note: Large deployments may take 10+ minutes. Please be patient..."
	@echo ""
	@echo "📊 Deployment Progress Monitor:"
	@echo "   🌐 Azure Portal: https://portal.azure.com/#@/resource/subscriptions/$(shell az account show --query id -o tsv 2>/dev/null)/resourceGroups/$(AZURE_RESOURCE_GROUP)/providers/Microsoft.Web/sites/$(WEBAPP_NAME)/deploymentCenter"
	@echo "   📋 Deployment Logs: https://$(WEBAPP_NAME).scm.azurewebsites.net/api/deployments/latest/log"
	@echo ""
	@set -e; \
	if az webapp deploy --resource-group $(AZURE_RESOURCE_GROUP) --name $(WEBAPP_NAME) --src-path $(DEPLOY_DIR) --type zip; then \
		DEPLOY_EXIT_CODE=$$?; \
		echo ""; \
		echo "⚠️  Deployment command timed out or encountered an issue (exit code: $$DEPLOY_EXIT_CODE)"; \
		echo ""; \
		if [ "$$DEPLOY_EXIT_CODE" = "124" ]; then \
			echo "🔄 TIMEOUT NOTICE: The deployment is likely still in progress in the background."; \
			echo "   The 15-minute timeout is a safety measure to prevent hanging builds."; \
			echo ""; \
		fi; \
		echo "📋 Next Steps:"; \
		echo "   1. 🔍 Check deployment status in Azure Portal:"; \
		echo "      https://portal.azure.com/#@/resource/subscriptions/$(shell az account show --query id -o tsv 2>/dev/null)/resourceGroups/$(AZURE_RESOURCE_GROUP)/providers/Microsoft.Web/sites/$(WEBAPP_NAME)/deploymentCenter"; \
		echo ""; \
		echo "   2. 📊 Monitor real-time logs via VS Code:"; \
		echo "      • Install 'Azure App Service' extension"; \
		echo "      • Right-click on '$(WEBAPP_NAME)' → 'Start Streaming Logs'"; \
		echo "      • Or use Command Palette: 'Azure App Service: Start Streaming Logs'"; \
		echo ""; \
		echo "   3. 🖥️  Monitor logs via Azure CLI:"; \
		echo "      az webapp log tail --resource-group $(AZURE_RESOURCE_GROUP) --name $(WEBAPP_NAME)"; \
		echo ""; \
		echo "   4. 🌐 Check deployment logs directly:"; \
		echo "      https://$(WEBAPP_NAME).scm.azurewebsites.net/api/deployments/latest/log"; \
		echo ""; \
		echo "   5. 🔄 If deployment fails, retry with:"; \
		echo "      make deploy_to_webapp WEBAPP_NAME=$(WEBAPP_NAME) DEPLOY_DIR=$(DEPLOY_DIR) AZURE_RESOURCE_GROUP=$(AZURE_RESOURCE_GROUP)"; \
		echo ""; \
		echo "💡 Pro Tip: Large Node.js builds (like Vite) typically take 5-15 minutes."; \
		echo "   The site may show 'Application Error' until build completes."; \
		exit $$DEPLOY_EXIT_CODE; \
	else \
		echo ""; \
		echo "✅ Deployment command completed successfully!"; \
		echo "🌐 Your app should be available at: https://$(WEBAPP_NAME).azurewebsites.net"; \
		echo ""; \
		echo "📋 Post-Deployment Verification:"; \
		echo "   • Wait 2-3 minutes for app startup"; \
		echo "   • Check app health: https://$(WEBAPP_NAME).azurewebsites.net/health (if available)"; \
		echo "   • Monitor logs for any startup issues"; \
		echo ""; \
	fi

# Deploy frontend to Azure Web App using Terraform outputs and deployment artifacts
deploy_frontend:
	@echo "🚀 Deploying frontend to Azure Web App using Terraform outputs"
	$(MAKE) generate_frontend_deployment
	$(eval WEBAPP_NAME := $(shell terraform -chdir=$(TF_DIR) output -raw FRONTEND_APP_SERVICE_NAME 2>/dev/null))
	$(eval AZURE_RESOURCE_GROUP := $(shell terraform -chdir=$(TF_DIR) output -raw AZURE_RESOURCE_GROUP 2>/dev/null))
	$(eval DEPLOY_ZIP := $(shell ls -1t .deploy/frontend_deployment_*.zip 2>/dev/null | head -n1))
	@if [ -z "$(WEBAPP_NAME)" ]; then \
		echo "❌ Could not determine frontend web app name from Terraform outputs."; \
		exit 1; \
	fi
	@if [ -z "$(AZURE_RESOURCE_GROUP)" ]; then \
		echo "❌ Could not determine resource group name from Terraform outputs."; \
		exit 1; \
	fi
	@if [ -z "$(DEPLOY_ZIP)" ]; then \
		echo "❌ No frontend deployment zip found. Run 'make generate_frontend_deployment' first."; \
		exit 1; \
	fi
	$(MAKE) deploy_to_webapp WEBAPP_NAME=$(WEBAPP_NAME) DEPLOY_DIR=$(DEPLOY_ZIP) AZURE_RESOURCE_GROUP=$(AZURE_RESOURCE_GROUP)

# Deploy backend to Azure Web App using Terraform outputs and deployment artifacts
deploy_backend:
	@echo "🚀 Deploying backend to Azure Web App using Terraform outputs"
	$(MAKE) generate_backend_deployment
	$(eval WEBAPP_NAME := $(shell terraform -chdir=$(TF_DIR) output -raw BACKEND_APP_SERVICE_NAME 2>/dev/null))
	$(eval AZURE_RESOURCE_GROUP := $(shell terraform -chdir=$(TF_DIR) output -raw AZURE_RESOURCE_GROUP 2>/dev/null))
	$(eval DEPLOY_ZIP := $(shell ls -1t .deploy/backend_deployment_*.zip 2>/dev/null | head -n1))
	@if [ -z "$(WEBAPP_NAME)" ]; then \
		echo "❌ Could not determine backend web app name from Terraform outputs."; \
		exit 1; \
	fi
	@if [ -z "$(AZURE_RESOURCE_GROUP)" ]; then \
		echo "❌ Could not determine resource group name from Terraform outputs."; \
		exit 1; \
	fi
	@if [ -z "$(DEPLOY_ZIP)" ]; then \
		echo "❌ No backend deployment zip found. Run 'make generate_backend_deployment' first."; \
		exit 1; \
	fi
	$(MAKE) deploy_to_webapp WEBAPP_NAME=$(WEBAPP_NAME) DEPLOY_DIR=$(DEPLOY_ZIP) AZURE_RESOURCE_GROUP=$(AZURE_RESOURCE_GROUP)

# Monitor deployment status and logs for any webapp
# Usage: make monitor_deployment WEBAPP_NAME=<your-app-name> AZURE_RESOURCE_GROUP=<your-resource-group>
monitor_deployment:
	@if [ -z "$(WEBAPP_NAME)" ]; then \
		echo "❌ Usage: make monitor_deployment WEBAPP_NAME=<your-app-name> AZURE_RESOURCE_GROUP=<your-resource-group>"; \
		exit 1; \
	fi
	@if [ -z "$(AZURE_RESOURCE_GROUP)" ]; then \
		if [ -f ".env" ]; then \
			RESOURCE_GROUP_ENV=$$(grep '^AZURE_RESOURCE_GROUP=' .env | cut -d'=' -f2); \
			if [ -n "$$RESOURCE_GROUP_ENV" ]; then \
				echo "ℹ️  Using AZURE_RESOURCE_GROUP from .env: $$RESOURCE_GROUP_ENV"; \
				AZURE_RESOURCE_GROUP=$$RESOURCE_GROUP_ENV; \
			else \
				echo "❌ AZURE_RESOURCE_GROUP not set and not found in .env"; \
				exit 1; \
			fi \
		else \
			echo "❌ AZURE_RESOURCE_GROUP not set and .env file not found"; \
			exit 1; \
		fi \
	fi
	@echo "📊 Monitoring Azure Web App: $(WEBAPP_NAME)"
	@echo "============================================="
	@echo ""
	@echo "🔍 App Service Status:"
	@az webapp show --resource-group $(AZURE_RESOURCE_GROUP) --name $(WEBAPP_NAME) --query "{name:name,state:state,defaultHostName:defaultHostName,lastModifiedTime:lastModifiedTime}" --output table 2>/dev/null || echo "❌ Could not retrieve app status"
	@echo ""
	@echo "📋 Recent Deployment Status:"
	@az webapp deployment list --resource-group $(AZURE_RESOURCE_GROUP) --name $(WEBAPP_NAME) --query "[0].{status:status,deploymentId:id,startTime:startTime,endTime:endTime,message:message}" --output table 2>/dev/null || echo "❌ Could not retrieve deployment status"
	@echo ""
	@echo "🌐 Useful Links:"
	@echo "   • App URL: https://$(WEBAPP_NAME).azurewebsites.net"
	@echo "   • Azure Portal: https://portal.azure.com/#@/resource/subscriptions/$(shell az account show --query id -o tsv 2>/dev/null)/resourceGroups/$(AZURE_RESOURCE_GROUP)/providers/Microsoft.Web/sites/$(WEBAPP_NAME)"
	@echo "   • Deployment Center: https://portal.azure.com/#@/resource/subscriptions/$(shell az account show --query id -o tsv 2>/dev/null)/resourceGroups/$(AZURE_RESOURCE_GROUP)/providers/Microsoft.Web/sites/$(WEBAPP_NAME)/deploymentCenter"
	@echo "   • Kudu Console: https://$(WEBAPP_NAME).scm.azurewebsites.net"
	@echo "   • Deployment Logs: https://$(WEBAPP_NAME).scm.azurewebsites.net/api/deployments/latest/log"
	@echo ""
	@echo "📊 VS Code Log Streaming:"
	@echo "   1. Install 'Azure App Service' extension"
	@echo "   2. Sign in to Azure account"
	@echo "   3. Right-click '$(WEBAPP_NAME)' → 'Start Streaming Logs'"
	@echo "   4. Or use Command Palette: 'Azure App Service: Start Streaming Logs'"
	@echo ""
	@echo "🖥️  CLI Log Streaming (run in separate terminal):"
	@echo "   az webapp log tail --resource-group $(AZURE_RESOURCE_GROUP) --name $(WEBAPP_NAME)"
	@echo ""

# Stream logs for backend app service
monitor_backend_deployment:
	@echo "📊 Monitoring Backend Deployment"
	$(eval WEBAPP_NAME := $(shell terraform -chdir=$(TF_DIR) output -raw BACKEND_APP_SERVICE_NAME 2>/dev/null))
	$(eval AZURE_RESOURCE_GROUP := $(shell terraform -chdir=$(TF_DIR) output -raw AZURE_RESOURCE_GROUP 2>/dev/null))
	@if [ -z "$(WEBAPP_NAME)" ]; then \
		echo "❌ Could not determine backend web app name from Terraform outputs."; \
		exit 1; \
	fi
	@if [ -z "$(AZURE_RESOURCE_GROUP)" ]; then \
		echo "❌ Could not determine resource group name from Terraform outputs."; \
		exit 1; \
	fi
	$(MAKE) monitor_deployment WEBAPP_NAME=$(WEBAPP_NAME) AZURE_RESOURCE_GROUP=$(AZURE_RESOURCE_GROUP)

# Stream logs for frontend app service  
monitor_frontend_deployment:
	@echo "📊 Monitoring Frontend Deployment"
	$(eval WEBAPP_NAME := $(shell terraform -chdir=$(TF_DIR) output -raw FRONTEND_APP_SERVICE_NAME 2>/dev/null))
	$(eval AZURE_RESOURCE_GROUP := $(shell terraform -chdir=$(TF_DIR) output -raw AZURE_RESOURCE_GROUP 2>/dev/null))
	@if [ -z "$(WEBAPP_NAME)" ]; then \
		echo "❌ Could not determine frontend web app name from Terraform outputs."; \
		exit 1; \
	fi
	@if [ -z "$(AZURE_RESOURCE_GROUP)" ]; then \
		echo "❌ Could not determine resource group name from Terraform outputs."; \
		exit 1; \
	fi
	$(MAKE) monitor_deployment WEBAPP_NAME=$(WEBAPP_NAME) AZURE_RESOURCE_GROUP=$(AZURE_RESOURCE_GROUP)

.PHONY: generate_env_from_terraform check_terraform_initialized show_env_file update_env_with_secrets generate_env_from_terraform_ps show_env_file_ps update_env_with_secrets_ps monitor_deployment monitor_backend_deployment monitor_frontend_deployment


############################################################
# Azure Communication Services Phone Number Management
# Purpose: Purchase and manage ACS phone numbers
############################################################

# Purchase ACS phone number and store in environment file
# Usage: make purchase_acs_phone_number [ENV_FILE=custom.env] [COUNTRY_CODE=US] [AREA_CODE=833] [PHONE_TYPE=TOLL_FREE]
purchase_acs_phone_number:
	@echo "📞 Azure Communication Services - Phone Number Purchase"
	@echo "======================================================"
	@echo ""
	# Set default parameters
	$(eval ENV_FILE ?= .env.$(AZURE_ENV_NAME))
	$(eval COUNTRY_CODE ?= US)
	$(eval AREA_CODE ?= 866)
	$(eval PHONE_TYPE ?= TOLL_FREE)

	# Extract ACS endpoint from environment file
	@echo "🔍 Extracting ACS endpoint from $(ENV_FILE)"
	$(eval ACS_ENDPOINT := $(shell grep '^ACS_ENDPOINT=' $(ENV_FILE) | cut -d'=' -f2))

	@if [ -z "$(ACS_ENDPOINT)" ]; then \
		echo "❌ ACS_ENDPOINT not found in $(ENV_FILE). Please ensure the environment file contains ACS_ENDPOINT."; \
		exit 1; \
	fi

	@echo "📞 Creating a new ACS phone number using Python script..."
	python3 devops/scripts/azd/helpers/acs_phone_number_manager.py --endpoint $(ACS_ENDPOINT) purchase --country $(COUNTRY_CODE) --area $(AREA_CODE)  --phone-number-type $(PHONE_TYPE)

# Purchase ACS phone number using PowerShell (Windows)	
# Usage: make purchase_acs_phone_number_ps [ENV_FILE=custom.env] [COUNTRY_CODE=US] [AREA_CODE=833] [PHONE_TYPE=TOLL_FREE]
purchase_acs_phone_number_ps:
	@echo "📞 Azure Communication Services - Phone Number Purchase (PowerShell)"
	@echo "=================================================================="
	@echo ""
	
	# Set default parameters
	$(eval ENV_FILE ?= .env.$(AZURE_ENV_NAME))
	$(eval COUNTRY_CODE ?= US)
	$(eval AREA_CODE ?= 866)
	$(eval PHONE_TYPE ?= TOLL_FREE)
	
	# Execute the PowerShell script with parameters
	@powershell -ExecutionPolicy Bypass -File devops/scripts/Purchase-AcsPhoneNumber.ps1 \
		-EnvFile "$(ENV_FILE)" \
		-AzureEnvName "$(AZURE_ENV_NAME)" \
		-CountryCode "$(COUNTRY_CODE)" \
		-AreaCode "$(AREA_CODE)" \
		-PhoneType "$(PHONE_TYPE)" \
		-TerraformDir "$(TF_DIR)"


############################################################
# Azure Redis Management
# Purpose: Connect to Azure Redis using Azure AD authentication
############################################################

# Connect to Azure Redis using Azure AD authentication
# Usage: make connect_redis [ENV_FILE=custom.env]
connect_redis:
	@echo "🔌 Azure Redis - Connecting with Azure AD Authentication"
	@echo "========================================================"
	@echo ""
	
	# Set default environment file
	$(eval ENV_FILE ?= .env)
	
	# Extract Redis configuration from environment file
	@echo "🔍 Extracting Redis configuration from $(ENV_FILE)"
	$(eval REDIS_HOST := $(shell grep '^REDIS_HOST=' $(ENV_FILE) | cut -d'=' -f2))
	$(eval REDIS_PORT := $(shell grep '^REDIS_PORT=' $(ENV_FILE) | cut -d'=' -f2))
	
	@if [ -z "$(REDIS_HOST)" ]; then \
		echo "❌ REDIS_HOST not found in $(ENV_FILE)"; \
		exit 1; \
	fi
	
	@if [ -z "$(REDIS_PORT)" ]; then \
		echo "❌ REDIS_PORT not found in $(ENV_FILE)"; \
		exit 1; \
	fi
	
	@echo "📋 Redis Configuration:"
	@echo "   🌐 Host: $(REDIS_HOST)"
	@echo "   🔌 Port: $(REDIS_PORT)"
	@echo ""
	
	# Get current Azure user's object ID
	@echo "🔍 Getting current Azure user's object ID..."
	$(eval USER_OBJECT_ID := $(shell az ad signed-in-user show --query id -o tsv 2>/dev/null))
	
	@if [ -z "$(USER_OBJECT_ID)" ]; then \
		echo "❌ Unable to get current user's object ID. Please ensure you are signed in to Azure CLI."; \
		echo "   Run: az login"; \
		exit 1; \
	fi
	
	@echo "👤 Current User Object ID: $(USER_OBJECT_ID)"
	@echo ""
	
	# Get access token for Redis scope
	@echo "🔐 Getting Azure access token for Redis scope..."
	$(eval ACCESS_TOKEN := $(shell az account get-access-token --scope https://redis.azure.com/.default --query accessToken -o tsv 2>/dev/null))
	
	@if [ -z "$(ACCESS_TOKEN)" ]; then \
		echo "❌ Unable to get access token for Redis scope."; \
		echo "   Please ensure you have proper permissions for Azure Cache for Redis."; \
		exit 1; \
	fi
	
	@echo "✅ Access token obtained successfully"
	@echo ""
	
	# Connect to Redis using Azure AD authentication
	@echo "🚀 Connecting to Redis with Azure AD authentication..."
	@echo "   Username: $(USER_OBJECT_ID)"
	@echo "   Password: [Azure Access Token]"
	@echo ""
	@echo "� Debug: Using command:"
	@echo "   redis-cli -h $(REDIS_HOST) -p $(REDIS_PORT) --tls -u $(USER_OBJECT_ID) -a [ACCESS_TOKEN]"
	@echo ""
	@echo "�📝 Note: You are now connected to Redis. Use Redis commands as needed."
	@echo "   Example commands: PING, INFO, KEYS *, GET <key>, SET <key> <value>"
	@echo "   Type 'quit' or 'exit' to disconnect."
	@echo ""
	
	@redis-cli -h $(REDIS_HOST) -p $(REDIS_PORT) --tls -u $(USER_OBJECT_ID) -a $(ACCESS_TOKEN) || { \
		echo ""; \
		echo "❌ Redis connection failed!"; \
		echo ""; \
		echo "🔧 Debug: Command that failed:"; \
		echo "   redis-cli -h $(REDIS_HOST) -p $(REDIS_PORT) --tls -u $(USER_OBJECT_ID) -a $(ACCESS_TOKEN)"; \
		echo ""; \
		echo "💡 Troubleshooting steps:"; \
		echo "   1. Test basic connectivity: telnet $(REDIS_HOST) $(REDIS_PORT)"; \
		echo "   2. Verify Azure permissions: az role assignment list --assignee $(USER_OBJECT_ID) --scope /subscriptions/$(shell az account show --query id -o tsv)/resourceGroups/$(shell grep '^AZURE_RESOURCE_GROUP=' $(ENV_FILE) | cut -d'=' -f2)/providers/Microsoft.Cache/redis/$(shell echo $(REDIS_HOST) | cut -d'.' -f1)"; \
		echo "   3. Check Redis configuration in Azure Portal"; \
		echo "   4. Verify TLS settings and Azure AD authentication is enabled"; \
		exit 1; \
	}

# Test Redis connection without interactive session
# Usage: make test_redis_connection [ENV_FILE=custom.env]
test_redis_connection:
	@echo "🧪 Azure Redis - Testing Connection"
	@echo "===================================="
	@echo ""
	
	# Set default environment file
	$(eval ENV_FILE ?= .env)
	
	# Extract Redis configuration from environment file
	$(eval REDIS_HOST := $(shell grep '^REDIS_HOST=' $(ENV_FILE) | cut -d'=' -f2))
	$(eval REDIS_PORT := $(shell grep '^REDIS_PORT=' $(ENV_FILE) | cut -d'=' -f2))
	
	@if [ -z "$(REDIS_HOST)" ] || [ -z "$(REDIS_PORT)" ]; then \
		echo "❌ Redis configuration not found in $(ENV_FILE)"; \
		exit 1; \
	fi
	
	# Get current Azure user's object ID and access token
	$(eval USER_OBJECT_ID := $(shell az ad signed-in-user show --query id -o tsv 2>/dev/null))
	$(eval ACCESS_TOKEN := $(shell az account get-access-token --scope https://redis.azure.com/.default --query accessToken -o tsv 2>/dev/null))
	
	@if [ -z "$(USER_OBJECT_ID)" ] || [ -z "$(ACCESS_TOKEN)" ]; then \
		echo "❌ Unable to authenticate with Azure. Please run: az login"; \
		exit 1; \
	fi
	
	@echo "🔍 Testing Redis connection..."
	@echo "   Host: $(REDIS_HOST):$(REDIS_PORT)"
	@echo "   User: $(USER_OBJECT_ID)"
	@echo ""
	
	# Test connection with PING command
	@echo "🔧 Debug: Attempting Redis connection with command:"
	@echo "   redis-cli -h $(REDIS_HOST) -p $(REDIS_PORT) --tls --user $(USER_OBJECT_ID) --pass [ACCESS_TOKEN]"
	@echo ""
	@if redis-cli -h $(REDIS_HOST) -p $(REDIS_PORT) --tls --user $(USER_OBJECT_ID) --pass $(ACCESS_TOKEN) PING > /dev/null 2>&1; then \
		echo "✅ Redis connection successful!"; \
		echo "📊 Redis Info:"; \
		redis-cli -h $(REDIS_HOST) -p $(REDIS_PORT) --tls --user $(USER_OBJECT_ID) --pass $(ACCESS_TOKEN) INFO server | head -5; \
	else \
		echo "❌ Redis connection failed!"; \
		echo ""; \
		echo "🔧 Debug: Full command that failed:"; \
		echo "   redis-cli -h $(REDIS_HOST) -p $(REDIS_PORT) --tls --user $(USER_OBJECT_ID) --pass $(ACCESS_TOKEN) PING"; \
		echo ""; \
		echo "🔧 Debug: Testing connection with verbose output:"; \
		redis-cli -h $(REDIS_HOST) -p $(REDIS_PORT) --tls --user $(USER_OBJECT_ID) --pass $(ACCESS_TOKEN) PING 2>&1 || true; \
		echo ""; \
		echo "   Please check:"; \
		echo "   • Redis host and port are correct"; \
		echo "   • Your Azure account has Redis Data Contributor role"; \
		echo "   • Azure Cache for Redis allows Azure AD authentication"; \
		echo "   • TLS is properly configured on the Redis instance"; \
		echo "   • Network connectivity to $(REDIS_HOST):$(REDIS_PORT)"; \
		exit 1; \
	fi

.PHONY: connect_redis test_redis_connection

############################################################
# Help and Documentation
############################################################

# Default target - show help
.DEFAULT_GOAL := help
# Show help information
help:
	@echo ""
	@echo "🛠️  gbb-ai-audio-agent Makefile"
	@echo "=============================="
	@echo ""
	@echo "📋 Code Quality:"
	@echo "  check_code_quality               Run all code quality checks (pre-commit, bandit, etc.)"
	@echo "  fix_code_quality                 Auto-fix code quality issues (black, isort, ruff)"
	@echo "  run_unit_tests                   Run unit tests with coverage"
	@echo "  run_pylint                       Run pylint analysis"
	@echo "  set_up_precommit_and_prepush     Install git hooks"
	@echo ""
	@echo "🐍 Environment Management:"
	@echo "  create_conda_env                 Create conda environment from environment.yaml"
	@echo "  activate_conda_env               Activate conda environment"
	@echo "  remove_conda_env                 Remove conda environment"
	@echo ""
	@echo "🚀 Application:"
	@echo "  starts_rtagent_server            Start backend server (FastAPI/Uvicorn)"
	@echo "  starts_rtagent_browser           Start frontend dev server (Vite + React)"
	@echo "  start_backend                    Start backend via script"
	@echo "  start_frontend                   Start frontend via script"
	@echo "  start_tunnel                     Start dev tunnel via script"
	@echo ""
	@echo "⚡ Load Testing:"
	@echo "  generate_audio                   Generate PCM audio files for load testing"
	@echo "  run_load_test                    Run WebSocket endpoint load testing (safe)"
	@echo "  run_acs_dev_test                 Run 1 ACS call to +8165019907 (development)"
	@echo "  run_acs_staging_test             Run 5 ACS calls (staging environment)"
	@echo "  run_acs_prod_test                Run 20 ACS calls (production testing)"
	@echo "  show_acs_test_config             Show ACS test configurations without running"
	@echo ""
	@echo "📦 Deployment Artifacts:"
	@echo "  generate_backend_deployment      Generate backend deployment artifacts and zip"
	@echo "  generate_frontend_deployment     Generate frontend deployment artifacts and zip"
	@echo "  clean_deployment_artifacts       Clean deployment artifacts"
	@echo "  show_deployment_info             Show deployment package information"
	@echo ""
	@echo "🌐 Azure Web App Deployment:"
	@echo "  deploy_backend                   Deploy backend to Azure App Service (using Terraform outputs)"
	@echo "  deploy_frontend                  Deploy frontend to Azure App Service (using Terraform outputs)"
	@echo "  deploy_to_webapp                 Generic Web App deployment (manual parameters)"
	@echo "  monitor_deployment               Monitor any webapp deployment status and logs"
	@echo "  monitor_backend_deployment       Monitor backend deployment (using Terraform outputs)"
	@echo "  monitor_frontend_deployment      Monitor frontend deployment (using Terraform outputs)"
	@echo ""
	@echo "🏗️  Terraform Environment Management:"
	@echo "  generate_env_from_terraform      Generate .env file from Terraform state (Bash)"
	@echo "  generate_env_from_terraform_ps   Generate .env file from Terraform state (PowerShell)"
	@echo "  show_env_file                    Display current environment file info (Bash)"
	@echo "  show_env_file_ps                 Display current environment file info (PowerShell)"
	@echo "  update_env_with_secrets          Update .env file with Key Vault secrets (Bash)"
	@echo "  update_env_with_secrets_ps       Update .env file with Key Vault secrets (PowerShell)"
	@echo "  check_terraform_initialized      Check if Terraform is properly initialized"
	@echo ""
	@echo "📞 Azure Communication Services:"
	@echo "  purchase_acs_phone_number        Purchase ACS phone number and store in env file"
	@echo "  purchase_acs_phone_number_ps     Purchase ACS phone number (PowerShell version)"
	@echo ""
	@echo "🔴 Azure Redis Management:"
	@echo "  connect_redis                    Connect to Azure Redis using Azure AD authentication"
	@echo "  test_redis_connection            Test Redis connection without interactive session"
	@echo ""
	@echo "📖 Required Environment Variables (for Terraform):"
	@echo "  AZURE_SUBSCRIPTION_ID            Your Azure subscription ID"
	@echo "  AZURE_ENV_NAME                   Environment name (default: dev)"
	@echo ""
	@echo "💡 Quick Start for Environment Generation:"
	@echo "  export AZURE_SUBSCRIPTION_ID=<your-subscription-id>"
	@echo "  export AZURE_ENV_NAME=dev"
	@echo "  make generate_env_from_terraform"
	@echo "  make update_env_with_secrets"
	@echo ""
	@echo "💡 Quick Start for Full Terraform Deployment (Alternative to azd):"
	@echo "  1. cd infra/terraform && terraform init && terraform apply"
	@echo "  2. cd ../.. && make generate_env_from_terraform"
	@echo "  3. make update_env_with_secrets"
	@echo "  4. make generate_backend_deployment && make deploy_backend"
	@echo "  5. make generate_frontend_deployment && make deploy_frontend"
	@echo ""
	@echo "💡 Quick Start for ACS Phone Number Purchase:"
	@echo "  make purchase_acs_phone_number                    # Bash/Python version"
	@echo "  make purchase_acs_phone_number_ps                # PowerShell version"
	@echo ""
	@echo "💡 Deployment Monitoring Tips:"
	@echo "  • Large deployments may timeout after 15 minutes but continue in background"
	@echo "  • Use monitor_deployment targets to check status during/after deployment"
	@echo "  • Install 'Azure App Service' VS Code extension for easy log streaming"
	@echo "  • Frontend builds (Vite/React) typically take 5-15 minutes"
	@echo ""
	@echo "📝 Note: ACS endpoint will be retrieved from:"
	@echo "  1. Environment file (ACS_ENDPOINT variable)"
	@echo "  2. Terraform state output (acs_endpoint)"
	@echo "  3. Manual input if not found above"
	@echo ""

.PHONY: help
