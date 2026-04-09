# AI Dev Pipeline

**AI-driven development automation framework with 3-stage quality assurance.**

[English](#english) | [中文文档](#中文文档)

---

<a name="english"></a>
## Overview

AI Dev Pipeline is an intelligent automation framework that leverages AI agents to handle development tasks through a rigorous 3-stage quality assurance system. Each task passes through **Dev → Test → Review** stages, each handled by independent AI agents, significantly improving code quality and bug detection rates.

### Key Features

- **3-Stage Quality Assurance**: Dev (implementation) → Test (issue detection) → Review (code review)
- **Technology Agnostic**: Works with React, Vue, Laravel, Django, and any other framework
- **Intelligent Initialization**: Auto-detects project tech stack, generates configurations
- **Flexible Task Management**: JSON-based task storage with acceptance criteria
- **Timeout & Retry Handling**: Robust error handling with exponential backoff
- **Node.js Bridge**: Cross-platform CLI invocation via stdin pipe, bypassing Windows command line length limits
- **Git Integration**: Automatic commits after each successful stage

### Bug Detection Rate

Traditional single-agent development: **~60%**

AI Dev Pipeline (3 stages): **~90%**

---

## Quick Start

### Prerequisites

- Python 3.7+
- Node.js 18+ (required for the CLI bridge layer)
- Claude CLI (`claude` command available)
- Git

### Installation

1. **Copy to your project**

```bash
# Linux/macOS
cp -r .harness /path/to/your/project/
cd /path/to/your/project

# Windows (PowerShell)
Copy-Item -Recurse .harness /path/to/your/project/
cd /path/to/your/project
```

2. **Configure environment**

```bash
# Copy environment configuration
cp .harness/.env.example .harness/.env

# Install Node.js bridge dependencies
cd .harness/scripts && npm install && cd ../../..
```

3. **Initialize the system**

In Claude Code conversation, say:

```
Help me initialize the Harness system
```

Or manually (coming soon):

```bash
python3 .harness/scripts/init_harness.py
```

3. **Create your first task**

```bash
python3 .harness/scripts/add_task.py \
  --id FE_Component_001 \
  --desc "Create user avatar component" \
  --acceptance \
    "src/components/UserAvatar/UserAvatar.tsx exists" \
    "npm test passes"
```

4. **Run automation**

```bash
python .harness/scripts/run_automation.py -v
```

---

## How It Works

### 3-Stage System

| Stage | Responsibility | Output |
|-------|---------------|--------|
| **Dev** | Implement features | Code files + basic tests |
| **Test** | Find issues | Test report + issue list |
| **Review** | Code review | Quality assessment + improvement suggestions |

### Workflow

```
┌──────────────────────────────────────────────────────┐
│           Automation Workflow                         │
├──────────────────────────────────────────────────────┤
│  1. run_automation.py → Get next pending stage       │
│  2. Assemble Prompt (CLAUDE.md + Task + Template)   │
│  3. Write prompt to file → node runner.js (bridge)  │
│  4. runner.js spawns Claude CLI via stdin pipe      │
│  5. Agent executes and calls mark-stage              │
│  6. Detect completion (TaskStorage → logs → git)    │
│  7. Success → Next task / Failure → Retry → Skip    │
└──────────────────────────────────────────────────────┘
```

---

## Task Creation

### Using Script (Recommended)

**React/Vue Example:**

```bash
python3 .harness/scripts/add_task.py \
  --id FE_Component_001 \
  --category feature \
  --desc "Create user avatar component" \
  --acceptance \
    "src/components/UserAvatar/UserAvatar.tsx exists" \
    "Supports 3 sizes: small, medium, large" \
    "npm test passes"
```

**Laravel Example:**

```bash
python3 .harness/scripts/add_task.py \
  --id SIM_API_001 \
  --category feature \
  --desc "Implement user list API endpoint" \
  --acceptance \
    "app/Http/Controllers/Api/App/UserController.php exists" \
    "Contains index method" \
    "php artisan test passes"
```

**More examples:**

```bash
cat .harness/examples/task_examples.json
```

### Manual Creation

```bash
cat > .harness/tasks/pending/FE_Component_001.json << 'EOF'
{
  "id": "FE_Component_001",
  "category": "feature",
  "complexity": "medium",
  "description": "Create user avatar component",
  "acceptance": [
    "src/components/UserAvatar/UserAvatar.tsx exists",
    "Supports 3 sizes",
    "npm test passes"
  ],
  "stages": {
    "dev": {"completed": false, "completed_at": null, "issues": []},
    "test": {"completed": false, "completed_at": null, "issues": [], "test_results": {}},
    "review": {"completed": false, "completed_at": null, "issues": [], "risk_level": null}
  }
}
EOF

# Rebuild index
python3 .harness/scripts/task_file_storage.py --action rebuild-index
```

---

## Task Format

```json
{
  "id": "SIM_Feature_001",
  "category": "feature",
  "complexity": "medium",
  "description": "Task description",
  "acceptance": ["criterion 1", "criterion 2"],
  "validation": {
    "enabled": true,
    "threshold": 0.8,
    "max_retries": 3
  },
  "stages": {...}
}
```

**Categories**: `controller`, `model`, `migration`, `feature`, `fix`, `test`, `style`

**Complexity**: `simple` (5 min), `medium` (8 min), `complex` (10 min)

---

## Common Commands

### Task Management

```bash
# View current task
python3 .harness/scripts/harness-tools.py --action current

# View all tasks
python3 .harness/scripts/harness-tools.py --action list

# Check stage status
python3 .harness/scripts/harness-tools.py --action stage-status --id TASK_ID

# Mark stage complete
python3 .harness/scripts/harness-tools.py --action mark-stage \
  --id TASK_ID --stage dev --files file1.php file2.php

# Mark task complete
python3 .harness/scripts/harness-tools.py --action mark-done --id TASK_ID

# Verify task
python3 .harness/scripts/harness-tools.py --action verify --id TASK_ID
```

### Troubleshooting

```bash
# View logs
tail -f .harness/logs/automation/$(date +%Y/%m)/*.log

# Check next stage
python3 .harness/scripts/next_stage.py

# Detect stage completion
python3 .harness/scripts/detect_stage_completion.py --id TASK_ID --stage test
```

---

## Configuration

Edit `.harness/.env`:

| Config | Default | Description |
|--------|---------|-------------|
| `CLAUDE_CMD` | claude | Claude CLI command |
| `PERMISSION_MODE` | bypassPermissions | Permission mode |
| `MAX_RETRIES` | 3 | Max retry attempts |
| `LOOP_SLEEP` | 2 | Loop interval (seconds) |
| `BASE_SILENCE_TIMEOUT` | 300 | Base timeout (seconds) |
| `MAX_SILENCE_TIMEOUT` | 600 | Max timeout (seconds) |
| `TIMEOUT_BACKOFF_FACTOR` | 1.3 | Timeout backoff factor |
| `MAX_TIMEOUT_RETRIES` | 3 | Max timeout retries |

### Performance Tuning

```bash
# .harness/.env

# Base timeout (seconds)
BASE_SILENCE_TIMEOUT=300

# Max timeout cap (seconds)
MAX_SILENCE_TIMEOUT=600

# Faster loop interval
LOOP_SLEEP=2
```

Timeouts are calculated as `min(BASE_SILENCE_TIMEOUT * stage_multiplier * backoff, MAX_SILENCE_TIMEOUT)`.
Stage multipliers: dev=4x, test=3x, review=2x, validation=1.5x.

---

## Project Configuration

After initialization, `.harness/project-config.json` is generated:

```json
{
  "tech_stack": {
    "language": "typescript",
    "framework": "react",
    "package_manager": "npm"
  },
  "paths": {
    "source": "src",
    "components": "src/components",
    "tests": "src/__tests__"
  },
  "commands": {
    "test": "npm test",
    "lint": "npm run lint",
    "build": "npm run build"
  }
}
```

Modify this file to customize system behavior.

---

## Directory Structure

```
.harness/
├── README.md                    # This file
├── task-index.json              # Task index (auto-managed)
├── project-config.json          # Project config
├── .env                         # Environment config
├── .env.example                 # Environment config template
├── .gitignore                   # Git ignore rules
│
├── tasks/                       # Task storage
│   ├── pending/                 # Pending tasks (*.json)
│   └── completed/YYYY/MM/       # Completed tasks archive
│
├── scripts/                     # Automation scripts (unified Python + Node.js)
│   ├── run_automation.py        # Main automation engine
│   ├── dual_timeout.py          # Timeout executor with Node.js bridge
│   ├── runner.js                # Node.js CLI bridge (stdin pipe)
│   ├── package.json             # Node.js dependencies
│   ├── config.py                # Configuration center
│   ├── detect_stage_completion.py  # Stage completion detection
│   ├── task_storage.py          # Task file storage
│   ├── harness-tools.py         # Core tools (task management)
│   ├── next_stage.py            # Next stage detection
│   ├── add_task.py              # Create new tasks
│   ├── logger.py                # Logging system
│   └── ...
│
├── templates/                   # Agent prompt templates
│   ├── init_prompt.md           # Initialization wizard
│   ├── dev_prompt.md            # Dev stage
│   ├── test_prompt.md           # Test stage
│   ├── review_prompt.md         # Review stage
│   └── validation_prompt.md     # Validation stage
│
├── examples/                    # Examples and templates
│   └── task_examples.json       # Acceptance criteria examples
│
├── docs/                        # Documentation
│   ├── stages_guide.md          # 3-stage system details
│   ├── ai_agent_quickstart.md   # AI Agent quickstart
│   ├── task_file_storage_quickstart.md
│   └── troubleshooting.md       # Troubleshooting guide
│
├── cli-io/                      # CLI session I/O (runtime)
├── logs/automation/             # Runtime logs
├── knowledge/                   # Knowledge base (contracts + constraints)
├── artifacts/                   # Task artifacts
└── reports/                     # Execution reports
```

---

## Initialization Guide

### When to Initialize

- First time copying Harness to a new project
- Switching project tech stack (e.g., Laravel → React)
- Resetting all tasks and environment data
- Updating templates for a new tech stack

### Smart Initialization

AI Dev Pipeline uses **LLM-driven intelligent initialization**.

#### Execution

In Claude Code conversation:

```
Help me initialize the Harness system
```

Or (coming soon):

```bash
python3 .harness/scripts/init_harness.py
```

#### Initialization Steps

1. **Clear historical data**
   - Delete all old tasks
   - Clear runtime logs
   - Reset CLI sessions

2. **Detect tech stack**
   - Read `package.json` / `composer.json` / `requirements.txt`
   - Detect language, framework, package manager
   - Analyze directory structure
   - **Interactive confirmation**

3. **Check local environment**
   - Verify required tools (node/php/python)
   - Check version requirements
   - Provide installation suggestions

4. **Generate project config**
   - Create `.harness/project-config.json`
   - Configure path mappings
   - Configure command mappings
   - Configure acceptance criteria templates

5. **Update CLAUDE.md**
   - Check for existing `CLAUDE.md` in project root
   - Generate specification document based on tech stack
   - Include code style, directory structure, testing strategy

6. **Verify script compatibility**
   - Check `.harness/scripts/*.py` for hardcoded paths
   - Adapt scripts to read `project-config.json`

7. **Update prompt templates**
   - Replace tech-specific commands in templates
   - Update test commands
   - Update review checkpoints

8. **Create acceptance examples**
   - Add examples to `.harness/examples/task_examples.json`
   - Include component, Hook, API, page task types

### Supported Tech Stacks

**Frontend:**
- React + TypeScript/JavaScript
- Vue 3 + TypeScript/JavaScript
- Next.js (App Router/Pages Router)
- Nuxt.js
- Angular

**Backend:**
- Laravel (PHP)
- Django (Python)
- Flask (Python)
- Express (Node.js)
- NestJS (Node.js)

**Other:**
- Go projects
- Rust projects
- Custom tech stacks (manual selection)

---

## Important Rules

1. **Initialize on first use** - Say "Help me initialize the Harness system"
2. **Never manually edit `task-index.json`** - Managed automatically
3. **Rebuild index after creating tasks** - `python3 .harness/scripts/task_file_storage.py --action rebuild-index`
4. **Dev stage must record artifacts** - Use `--files` parameter
5. **Acceptance criteria must be verifiable** - Specify file paths, method names, expected results
6. **Test isolation** - Ensure tests don't pollute database or filesystem
7. **Tech stack adaptation** - Re-run initialization to switch tech stacks

---

## Documentation

| Document | Description |
|----------|-------------|
| [stages_guide.md](docs/stages_guide.md) | 3-stage system detailed guide |
| [ai_agent_quickstart.md](docs/ai_agent_quickstart.md) | AI Agent quickstart |
| [task_file_storage_quickstart.md](docs/task_file_storage_quickstart.md) | Single-file storage system |
| [troubleshooting.md](docs/troubleshooting.md) | Troubleshooting guide |

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

## Maintainer

Harness Automation Team

**Last Updated**: 2026-04

**Core Features**:
- Smart tech stack detection
- 3-stage quality assurance (Dev → Test → Review)
- Cross-platform Node.js CLI bridge (stdin pipe)
- TaskStorage-first stage completion detection
- Works out of the box with any tech stack
- LLM-driven initialization

---

<a name="中文文档"></a>
## 中文文档

详见 [README.md](.harness/README.md)（项目内部完整中文文档）

---

## Quick Reference

### Essential Operations

```bash
# First time
Say in conversation: "Help me initialize the Harness system"

# Install bridge dependencies
cd .harness/scripts && npm install && cd ../..

# Create task
python3 .harness/scripts/add_task.py --id FE_Component_001 --desc "Description"

# Run automation
python .harness/scripts/run_automation.py -v
```

### Common Commands

```bash
# View current task
python3 .harness/scripts/harness-tools.py --action current

# View all tasks
python3 .harness/scripts/harness-tools.py --action list

# Mark stage complete
python3 .harness/scripts/harness-tools.py --action mark-stage --id TASK_ID --stage dev --files file1 file2

# View acceptance examples
cat .harness/examples/task_examples.json
```

### Key Files

- **Project Config**: `.harness/project-config.json`
- **Development Standards**: `CLAUDE.md`
- **Initialization Prompt**: `.harness/templates/init_prompt.md`
- **Acceptance Examples**: `.harness/examples/task_examples.json`
- **Task Templates**: `.harness/templates/dev_prompt.md` etc.