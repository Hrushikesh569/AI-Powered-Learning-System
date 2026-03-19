Contributing to AI-Powered-Learning-System

Thanks for your interest in contributing! This document outlines a minimal workflow to make contributions smooth.

- Code of conduct: Be respectful and collaborative.
- Issues: Open an issue describing the problem or feature with steps to reproduce.
- Branches: Create feature branches from `main` named `feat/short-description` or `fix/short-description`.
- Commits: Write clear commit messages. Squash related small commits when appropriate.
- Tests: Add or update tests for any behavior you modify. Run `pytest -q backend/tests` before submitting.
- Formatting: Use `black` for Python and follow existing style. Run linters (`flake8`) locally.
- CI: The repository runs checks on PRs—address failures before merging.
- PRs: Open a pull request against `main`, include testing steps and summary of changes.

If your change touches ML code or training pipelines, include instructions to reproduce runs locally and any required environment variables (MLFLOW_TRACKING_URI, CELERY_BROKER_URL, etc.).

Thanks — maintainers
