 @"
  # Development Guide
  ## Setup
  1. Clone repo
  2. Copy .env.example to .env
  3. Install dependencies: pip install -r requirements.txt
  4. Start databases: docker-compose up -d
  5. Run backend: python backend/main.py
  ## Git Workflow
  1. Create feature branch: git checkout -b feature/name
  2. Make changes & commit: git commit -m "feat: description"
  3. Push: git push origin feature/name
  4. Create PR on GitHub
  5. Merge after review
  ## Code Quality
  - Type hints required
  - Docstrings on all classes/functions
  - Tests for new features
  - No hardcoded values
  "@ | Out-File -Encoding UTF8 docs\DEVELOPMENT.md