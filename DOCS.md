# GitHub MCP Server — Documentation

## Overview

A production-ready [Model Context Protocol](https://modelcontextprotocol.io) server that exposes GitHub as AI-callable tools. Connect Claude, Cursor, or any MCP client to manage repositories, issues, PRs, workflows, releases, and more.

---

## Connecting Claude (claude.ai)

1. Open **Settings → Integrations → Add MCP Server**
2. Enter your server URL: `https://mcp.yourdomain.com/mcp`
3. If `MCP_API_KEY` is set, add header: `Authorization: Bearer <your-key>`
4. Authenticate via `/auth/login` once to store your GitHub token

---

## Connecting Cursor

In `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "github": {
      "url": "https://mcp.yourdomain.com/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_API_KEY"
      }
    }
  }
}
```

---

## Connecting VS Code (Copilot)

In `.vscode/settings.json`:
```json
{
  "github.copilot.chat.mcpServers": {
    "github-mcp": {
      "url": "https://mcp.yourdomain.com/mcp"
    }
  }
}
```

---

## OAuth Setup

1. Create a GitHub OAuth App at https://github.com/settings/developers
2. Set **Authorization callback URL** to `https://mcp.yourdomain.com/auth/callback`
3. Copy Client ID and Client Secret into your `.env` / Render environment variables

---

## Available Tools (28 tools)

### Repositories
| Tool | Description |
|------|-------------|
| `create_repository` | Create a new repo |
| `get_repository` | Get repo details |
| `list_my_repositories` | List your repos |
| `search_repositories` | Search GitHub repos |
| `delete_repository` | ⚠️ Permanently delete a repo |

### Issues
| Tool | Description |
|------|-------------|
| `create_issue` | Open a new issue |
| `list_issues` | List issues (open/closed/all) |
| `close_issue` | Close an issue by number |

### Pull Requests
| Tool | Description |
|------|-------------|
| `create_pull_request` | Open a PR |
| `list_pull_requests` | List PRs |

### Files
| Tool | Description |
|------|-------------|
| `read_file` | Read a file's content |
| `upload_file` | Create or update a file |
| `delete_file` | Delete a file |
| `push_folder` | Push multiple files in one commit |

### Branches & Commits
| Tool | Description |
|------|-------------|
| `create_branch` | Create a branch |
| `list_branches` | List all branches |
| `list_commits` | Show recent commits |

### GitHub Actions
| Tool | Description |
|------|-------------|
| `list_workflows` | List defined workflows |
| `run_workflow` | Trigger a workflow dispatch |
| `workflow_status` | Get recent run statuses |

### Releases
| Tool | Description |
|------|-------------|
| `list_releases` | List releases |
| `create_release` | Create a new release/tag |

### Code Search
| Tool | Description |
|------|-------------|
| `search_code` | Search code across GitHub |

### Organizations
| Tool | Description |
|------|-------------|
| `list_org_repos` | List org's repositories |
| `list_org_members` | List org's public members |

### Discussions
| Tool | Description |
|------|-------------|
| `list_discussions` | List repo discussions |

### Auth
| Tool | Description |
|------|-------------|
| `whoami` | Get authenticated user info |

---

## Deploying to Render

1. Create a **Web Service** pointing to this repo
2. Set **Build Command**: `pip install -r requirements.txt`
3. Set **Start Command**: `python -m app.main`
4. Add a **PostgreSQL** database from the Render dashboard
5. Set these environment variables in Render:
   - `DATABASE_URL` → Render PostgreSQL internal URL
   - `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`
   - `APP_SECRET_KEY`, `JWT_SECRET_KEY` → generate random strings
   - `ENCRYPTION_KEY` → `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   - `MCP_API_KEY` → any random string to protect your MCP endpoint
   - `OAUTH_REDIRECT_URI` → `https://your-app.onrender.com/auth/callback`
   - `CORS_ORIGINS` → `https://claude.ai,https://cursor.sh`

---

## Local Development

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env  # fill in your values

# 3. Start with Docker Compose (includes PostgreSQL)
docker compose up

# OR run directly with SQLite
python -m app.main
```

Server runs at http://localhost:8000

- API docs: http://localhost:8000/docs
- MCP endpoint: http://localhost:8000/mcp
- Health: http://localhost:8000/health
- Authenticate: http://localhost:8000/auth/login

---

## Security Notes

- **Always set `ENCRYPTION_KEY`** in production to encrypt stored GitHub tokens
- **Always set `MCP_API_KEY`** to prevent unauthorized access to your tools
- **Always use PostgreSQL** in production (SQLite data is lost on Render restarts)
- **Never commit `.env`** to version control
