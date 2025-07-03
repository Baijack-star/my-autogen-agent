#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Run database migrations
echo "Running database migrations..."
poetry run prisma migrate deploy

# Start the main application
echo "Starting the main application..."
exec poetry run rest
