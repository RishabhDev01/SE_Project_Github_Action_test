# Design Smell Detection & Refactoring Pipeline

A fully automated pipeline that detects design smells in Java code, refactors them using **Grok AI (FREE!)**, and creates Pull Requests.

## 🚀 Features

- **Automated Detection**: Uses DesigniteJava and TypeMetrics to detect design smells
- **FREE LLM Refactoring**: Uses xAI Grok API (FREE!) for intelligent code refactoring
- **Smart Chunking**: Handles large files by intelligently splitting them while preserving context
- **Validation**: Automatically validates refactored code (syntax, compilation, tests)
- **PR Generation**: Creates detailed Pull Requests with metrics comparison
- **Daily Automation**: Runs automatically via GitHub Actions

---

## 🔄 How It Runs (GitHub Actions - NOT Locally!)

This pipeline is designed to run **automatically on GitHub Actions**, not on your local machine:

### Automatic Daily Runs
```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions                            │
│                                                              │
│  ⏰ Daily at 2:00 AM UTC                                     │
│            │                                                 │
│            ▼                                                 │
│  ┌─────────────────┐                                        │
│  │ 1. Checkout     │ ← Clones your repo                     │
│  │    Repository   │                                        │
│  └────────┬────────┘                                        │
│           ▼                                                  │
│  ┌─────────────────┐                                        │
│  │ 2. Setup        │ ← Java 11 + Python 3.11                │
│  │    Environment  │                                        │
│  └────────┬────────┘                                        │
│           ▼                                                  │
│  ┌─────────────────┐                                        │
│  │ 3. Run          │ ← DesigniteJava + TypeMetrics          │
│  │    Detection    │                                        │
│  └────────┬────────┘                                        │
│           ▼                                                  │
│  ┌─────────────────┐                                        │
│  │ 4. Call Grok    │ ← FREE xAI API refactors code          │
│  │    API (FREE!)  │                                        │
│  └────────┬────────┘                                        │
│           ▼                                                  │
│  ┌─────────────────┐                                        │
│  │ 5. Validate     │ ← mvn compile + mvn test               │
│  │    & Test       │                                        │
│  └────────┬────────┘                                        │
│           ▼                                                  │
│  ┌─────────────────┐                                        │
│  │ 6. Create PR    │ ← Auto-creates Pull Request!           │
│  │    on GitHub    │                                        │
│  └─────────────────┘                                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Manual Trigger
1. Go to your repo on GitHub
2. Click **Actions** tab
3. Select **"Design Smell Detection & Refactoring"**
4. Click **"Run workflow"**
5. Optionally enable dry-run mode

---

## ⚙️ Setup (One-Time)

### Step 1: Get FREE Grok API Key
1. Go to [https://console.x.ai/](https://console.x.ai/)
2. Sign up / Log in with X account
3. Create API key (it's FREE!)

### Step 2: Add Secrets to GitHub
1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **"New repository secret"**
3. Add:
   - Name: `GROK_API_KEY`
   - Value: `xai-your-api-key-here`

### Step 3: (Optional) Download DesigniteJava
- Get from [designite-tools.com](https://www.designite-tools.com/designitejava/)
- Upload to `design_smell_pipeline/tools/` or use GitHub artifact

---

## 📁 Project Structure

```
design_smell_pipeline/
├── config/config.yaml       # Configuration (uses Grok!)
├── detection/               # Smell detection modules
├── refactoring/             # LLM refactoring (Grok/OpenAI/Gemini)
├── pr_generator/            # PR creation
└── main.py                  # Orchestrator
```

---

## 🔐 Required GitHub Secrets

| Secret | Description | How to Get |
|--------|-------------|------------|
| `GROK_API_KEY` | xAI Grok API key (FREE!) | [console.x.ai](https://console.x.ai/) |
| `GITHUB_TOKEN` | Auto-provided by GitHub | Already available |

---

## 🔍 Detected Smell Types

| Smell | Priority |
|-------|----------|
| God Class | High |
| Long Method | High |
| Feature Envy | Medium |
| Complex Method | Medium |
| Data Class | Low |

---

## 📊 Sample PR Output

PRs automatically include:
- ✅ Detected smells table
- ✅ Applied refactoring techniques
- ✅ Before/after metrics comparison
- ✅ Validation status

---

## 🏃 Local Run (Optional)

```bash
# Set API key
export GROK_API_KEY="xai-your-key"

# Dry run (no PR)
python main.py --dry-run

# Full run
python main.py
```
