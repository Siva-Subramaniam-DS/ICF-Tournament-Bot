#!/bin/bash

# ICF Tournament Bot Docker Runner Script
# This script helps you run the ICF Tournament Bot in Docker
# Last Updated: September 7, 2025

echo "🎮 ICF Tournament Bot Docker Runner"
echo "============================"

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "Please create a .env file with your Discord bot token:"
    echo "DISCORD_TOKEN=your_bot_token_here"
    exit 1
fi

# Load environment variables
source .env

# Check if DISCORD_TOKEN is set
if [ -z "$DISCORD_TOKEN" ]; then
    echo "❌ DISCORD_TOKEN not found in .env file!"
    echo "Please add your Discord bot token to the .env file:"
    echo "DISCORD_TOKEN=your_bot_token_here"
    exit 1
fi

echo "✅ Environment variables loaded"
echo "🤖 Starting Discord bot in Docker..."

# Create logs directory if it doesn't exist
mkdir -p logs

# Run with docker-compose
docker-compose up --build -d

echo "✅ Bot started successfully!"
echo "📊 To view logs: docker-compose logs -f"
echo "🛑 To stop: docker-compose down"
echo "🔄 To restart: docker-compose restart"
