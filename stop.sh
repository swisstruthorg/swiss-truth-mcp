#!/bin/bash
JAVA_HOME=/Users/admin/Applications/runtimes/jdk-21.0.7+6/Contents/Home
NEO4J_HOME=/Users/admin/Applications/runtimes/neo4j-community-5.26.0
export JAVA_HOME

echo "Stoppe Swiss Truth MCP..."
lsof -ti:8001 | xargs kill -9 2>/dev/null && echo "REST API gestoppt." || echo "REST API war nicht aktiv."
$NEO4J_HOME/bin/neo4j stop 2>/dev/null && echo "Neo4j gestoppt." || echo "Neo4j war nicht aktiv."
