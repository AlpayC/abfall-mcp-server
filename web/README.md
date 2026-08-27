# Abfall MCP website

Bilingual Next.js landing page for the public Abfall MCP service.

```bash
npm ci
npm run dev
npm run lint
npm run build
```

The production build uses Next.js static export and writes to `out/`. The root
Dockerfile copies that directory into the Python image, where the MCP server
serves `/`, `/en/`, and the generated `/_next/` assets alongside `/mcp` and
`/health`.
