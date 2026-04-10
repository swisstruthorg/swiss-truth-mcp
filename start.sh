#!/bin/bash
set -e

JAVA_HOME=/Users/admin/Applications/runtimes/jdk-21.0.7+6/Contents/Home
NEO4J_HOME=/Users/admin/Applications/runtimes/neo4j-community-5.26.0
PROJECT=/Users/admin/Applications/swiss-truth-mcp

export JAVA_HOME

echo "=== Swiss Truth MCP — Start ==="

# Neo4j starten (falls nicht bereits lauft)
if ! curl -s --max-time 2 http://localhost:7474 > /dev/null; then
  echo "Starte Neo4j..."
  $NEO4J_HOME/bin/neo4j start
  echo "Warte auf Neo4j..."
  for i in $(seq 1 15); do
    if curl -s --max-time 2 http://localhost:7474 > /dev/null; then
      echo "Neo4j bereit."
      break
    fi
    sleep 2
  done
else
  echo "Neo4j läuft bereits."
fi

# FastAPI REST API starten
echo "Starte REST API auf :8001..."
cd "$PROJECT"
.venv/bin/uvicorn swiss_truth_mcp.api.main:app --host 127.0.0.1 --port 8001 &
echo "API PID: $!"

echo ""
echo "Swiss Truth läuft:"
echo "  REST API:   http://127.0.0.1:8001/docs"
echo "  Neo4j UI:   http://localhost:7474"
echo "  MCP Server: Claude Desktop (via mcpServers config)"
echo ""
echo "Stoppen: ./stop.sh"
