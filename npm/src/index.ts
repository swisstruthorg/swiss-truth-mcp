#!/usr/bin/env node
/**
 * Swiss Truth MCP — stdio proxy
 *
 * Bridges stdio (Claude Desktop / any MCP host) ↔ Swiss Truth HTTP MCP server.
 * Usage in claude_desktop_config.json:
 *
 *   "swiss-truth": {
 *     "command": "npx",
 *     "args": ["-y", "swiss-truth-mcp"]
 *   }
 *
 * Optional env vars:
 *   SWISS_TRUTH_URL      — override server URL (default: https://swisstruth.org/mcp)
 *   SWISS_TRUTH_API_KEY  — API key (only needed for write operations)
 */

import { Client } from "@modelcontextprotocol/sdk/client/index";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse";
import { Server } from "@modelcontextprotocol/sdk/server/index";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  CallToolResult,
} from "@modelcontextprotocol/sdk/types";

const UPSTREAM_URL = process.env.SWISS_TRUTH_URL ?? "https://swisstruth.org/mcp";
const API_KEY      = process.env.SWISS_TRUTH_API_KEY ?? "";

async function main() {
  // ── 1. Connect to upstream HTTP MCP server ────────────────────────────────
  const headers: Record<string, string> = {};
  if (API_KEY) headers["X-Swiss-Truth-Key"] = API_KEY;

  const upstreamTransport = new SSEClientTransport(
    new URL(UPSTREAM_URL),
    { requestInit: { headers } },
  );

  const upstream = new Client(
    { name: "swiss-truth-proxy", version: "0.1.1" },
    { capabilities: {} },
  );
  await upstream.connect(upstreamTransport);

  // ── 2. Fetch tool list from upstream ──────────────────────────────────────
  const { tools } = await upstream.listTools();

  // ── 3. Create local stdio MCP server ─────────────────────────────────────
  const server = new Server(
    { name: "swiss-truth", version: "0.1.1" },
    { capabilities: { tools: {} } },
  );

  // List tools — return what upstream reported
  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools }));

  // Call tool — forward to upstream
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const result = await upstream.callTool({
      name: request.params.name,
      arguments: request.params.arguments ?? {},
    });
    return result as CallToolResult;
  });

  // ── 4. Start stdio transport ──────────────────────────────────────────────
  const stdioTransport = new StdioServerTransport();
  await server.connect(stdioTransport);

  // Graceful shutdown
  process.on("SIGINT",  () => { upstream.close(); server.close(); process.exit(0); });
  process.on("SIGTERM", () => { upstream.close(); server.close(); process.exit(0); });
}

main().catch((err) => {
  process.stderr.write(`[swiss-truth-mcp] Fatal: ${err.message}\n`);
  process.exit(1);
});
