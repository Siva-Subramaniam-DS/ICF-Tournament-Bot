#!/bin/bash
# ICF Tournament Bot - Update File Timestamps
# Last Updated: September 7, 2025

echo "Updating file timestamps for ICF Tournament Bot v3.0.0..."

# Update all configuration files
touch .dockerignore
touch .gitignore
touch .railwayignore
touch nixpacks.toml
touch pip.conf
touch requirements-lock.txt
touch railway.json
touch Procfile
touch runtime.txt

echo "✅ All file timestamps updated to current date"
echo "🚀 Ready for Git push and Railway deployment"