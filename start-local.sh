#!/bin/bash
# MiroFish-Offline Local Startup Script
# Starts backend and frontend for local-only testing

set -e

echo "🐟 Starting MiroFish-Offline (Local Testing Mode)"
echo "=================================================="
echo ""

# Activate conda environment
echo "📦 Activating conda environment..."
source ~/miniconda3/bin/activate mirofish

# Check services
echo ""
echo "🔍 Checking services..."

# Check Neo4j
if curl -s http://localhost:7474 > /dev/null; then
    echo "  ✓ Neo4j running on http://localhost:7474"
else
    echo "  ⚠ Neo4j not running! Start with: docker-compose up -d neo4j"
    exit 1
fi

# Check Ollama
if curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "  ✓ Ollama running on http://localhost:11434"
else
    echo "  ⚠ Ollama not running! Start with: ollama serve"
    exit 1
fi

# Check required models
echo ""
echo "🤖 Checking Ollama models..."
if ollama list | grep -q "qwen3:32b"; then
    echo "  ✓ qwen3:32b found"
else
    echo "  ⚠ qwen3:32b not found. Pull with: ollama pull qwen3:32b"
    exit 1
fi

if ollama list | grep -q "nomic-embed-text"; then
    echo "  ✓ nomic-embed-text found"
else
    echo "  ⚠ nomic-embed-text not found. Pull with: ollama pull nomic-embed-text"
    exit 1
fi

# Start backend
echo ""
echo "🚀 Starting backend server..."
cd /home/tank/Development_Projects/MiroFish-Offline/backend
python run.py > ../logs/backend.log 2>&1 &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

# Wait for backend to start
sleep 3

# Start frontend
echo ""
echo "🎨 Starting frontend server..."
cd /home/tank/Development_Projects/MiroFish-Offline/frontend
npm run dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "  Frontend PID: $FRONTEND_PID"

# Save PIDs
echo "$BACKEND_PID" > /tmp/mirofish-backend.pid
echo "$FRONTEND_PID" > /tmp/mirofish-frontend.pid

echo ""
echo "=================================================="
echo "✅ MiroFish-Offline is starting!"
echo "=================================================="
echo ""
echo "🌐 Access from this machine:"
echo "   Frontend:  http://localhost:3000"
echo "   Backend:   http://localhost:5001"
echo ""
echo "🌐 Access from your office machine:"
SERVER_IP=$(hostname -I | awk '{print $1}')
echo "   Frontend:  http://${SERVER_IP}:3000"
echo "   Backend:   http://${SERVER_IP}:5001"
echo ""
echo "📊 Neo4j Browser: http://${SERVER_IP}:7474"
echo "   (user: neo4j, password: mirofish)"
echo ""
echo "📋 Logs:"
echo "  Backend:  tail -f logs/backend.log"
echo "  Frontend: tail -f logs/frontend.log"
echo ""
echo "🛑 To stop:"
echo "  kill $(cat /tmp/mirofish-backend.pid) $(cat /tmp/mirofish-frontend.pid)"
echo "  or use: ./stop-local.sh"
echo ""
echo "⏳ Waiting for services to be ready..."
sleep 5

# Check if services are running
if curl -s http://localhost:5001/health > /dev/null 2>&1; then
    echo "  ✓ Backend is ready!"
else
    echo "  ⚠ Backend may still be starting... check logs/backend.log"
fi

if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo "  ✓ Frontend is ready!"
else
    echo "  ⚠ Frontend may still be starting... check logs/frontend.log"
fi

echo ""
echo "🎉 Open http://localhost:3000 in your browser to get started!"
