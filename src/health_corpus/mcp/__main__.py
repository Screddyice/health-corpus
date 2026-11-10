"""Entry point: ``python -m health_corpus.mcp`` runs FastMCP over stdio."""
from health_corpus.mcp.server import server

if __name__ == "__main__":
    server.run()
