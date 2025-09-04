# Dockerfile for the frontend React application

# Stage 1: Build the application
FROM node:22-alpine AS builder
WORKDIR /app

# Copy package.json and package-lock.json
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci

# Copy the rest of the application code
COPY . .

# Build the application for production (with placeholder)
RUN npm run build

# Stage 2: Serve the application
FROM node:22-alpine
WORKDIR /app

# Copy built files and package.json
COPY --from=builder /app/dist ./dist
COPY package.json package-lock.json ./
COPY entrypoint.sh ./

# Install production dependencies
RUN npm ci --omit=dev

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Expose port
EXPOSE 8080

# Set environment variable
ENV PORT=8080

# Use entrypoint to replace placeholders at runtime
ENTRYPOINT ["./entrypoint.sh"]
CMD ["npm", "start"]