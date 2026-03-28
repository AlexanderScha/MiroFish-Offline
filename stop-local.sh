#!/bin/bash
# Stop MiroFish-Offline local servers

echo "🛑 Stopping MiroFish-Offline..."

if [ -f /tmp/mirofish-backend.pid ]; then
    BACKEND_PID=$(cat /tmp/mirofish-backend.pid)
    if ps -p $BACKEND_PID > /dev/null; then
        kill $BACKEND_PID
        echo "  ✓ Backend stopped (PID: $BACKEND_PID)"
    fi
    rm /tmp/mirofish-backend.pid
fi

if [ -f /tmp/mirofish-frontend.pid ]; then
    FRONTEND_PID=$(cat /tmp/mirofish-frontend.pid)
    if ps -p $FRONTEND_PID > /dev/null; then
        kill $FRONTEND_PID
        echo "  ✓ Frontend stopped (PID: $FRONTEND_PID)"
    fi
    rm /tmp/mirofish-frontend.pid
fi

echo "✅ MiroFish-Offline stopped"
