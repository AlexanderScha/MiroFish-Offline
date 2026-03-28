# MiroFish-Offline - Quick Start Guide

## ✅ Repository Initialized for Local Testing

### Current Status
- ✅ Python 3.11 conda environment created (`mirofish`)
- ✅ Backend dependencies installed
- ✅ Frontend dependencies installed
- ✅ Neo4j running in Docker
- ✅ Ollama running locally with required models
- ✅ Configuration set for local-only access

### Running the Application

**Start everything:**
```bash
./start-local.sh
```

**Stop everything:**
```bash
./stop-local.sh
```

### Access Points
- **Frontend UI**: http://localhost:3000
- **Backend API**: http://localhost:5001
- **Neo4j Browser**: http://localhost:7474 (user: `neo4j`, password: `mirofish`)
- **Ollama**: http://localhost:11434

### First Steps

1. **Open the UI**: Navigate to http://localhost:3000 in your browser

2. **Upload a document**: 
   - Upload a PDF, MD, or TXT file (max 50MB)
   - Enter a simulation requirement (e.g., "Analyze public reaction to this policy")

3. **Build knowledge graph**: 
   - Wait for ontology generation
   - Build the graph from extracted entities

4. **Create simulation**:
   - Generate AI agent profiles based on entities
   - Configure simulation parameters
   - Run the simulation!

5. **Explore results**:
   - View simulated social media posts
   - Interview agents about their opinions
   - Generate analysis reports

### View Logs

**Backend logs:**
```bash
tail -f logs/backend.log
```

**Frontend logs:**
```bash
tail -f logs/frontend.log
```

### Manual Start (Alternative)

If you prefer to run components manually:

```bash
# Activate environment
conda activate mirofish

# Terminal 1: Backend
cd backend
python run.py

# Terminal 2: Frontend (new terminal)
conda activate mirofish
cd frontend
npm run dev
```

### Services Management

**Neo4j:**
```bash
# Start
docker-compose up -d neo4j

# Stop
docker-compose stop neo4j

# View logs
docker-compose logs -f neo4j
```

**Ollama** (already running locally - no action needed)

### ⚠️ Security Reminder

This setup is configured for **LOCAL TESTING ONLY**:
- No authentication enabled
- Debug mode disabled but still not production-ready
- CORS allows all origins from localhost
- Do NOT expose ports to your network
- Do NOT run on a public-facing server

### Troubleshooting

**Backend won't start:**
- Check `logs/backend.log`
- Ensure Neo4j is healthy: `docker-compose ps`
- Verify .env configuration

**Frontend won't start:**
- Check `logs/frontend.log`
- Verify Node.js version: `node --version` (should be v25+)

**Ollama models missing:**
```bash
ollama pull qwen3:32b
ollama pull nomic-embed-text
```

**Port conflicts:**
- 3000: Frontend
- 5001: Backend
- 7474/7687: Neo4j
- 11434: Ollama

### Models Being Used

- **LLM**: qwen3:32b (20GB, runs on your RTX 3090s)
- **Embeddings**: nomic-embed-text (274MB)
- **Simulation**: OASIS framework with CAMEL-AI

### Next Steps

1. Test with a sample document
2. Explore the generated knowledge graph in Neo4j Browser
3. Run a small simulation (10-20 agents, 5-10 rounds)
4. Review security hardening if you want to deploy beyond localhost

Enjoy exploring AI swarm intelligence! 🐟
