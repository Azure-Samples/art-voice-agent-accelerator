# Dev container Dockerfile
# Removes expired Yarn GPG key that breaks apt-get update

FROM mcr.microsoft.com/devcontainers/python:1-3.11

# Remove the expired Yarn repository and GPG key to prevent apt-get update failures
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && rm -f /usr/share/keyrings/yarn-keyring.gpg \
    && rm -f /etc/apt/keyrings/yarn.gpg \
    && apt-get update
