# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands
- Create environment: `mamba create -n openhsi python==3.10 openhsi flask`
- Activate environment: `mamba activate openhsi`
- Run server: `python server.py`
- Run as service: `sudo systemctl start openhsi-flask.service`

## Code Style Guidelines
- Indentation: 4 spaces
- Line length: ~88 characters (Black default)
- Imports: Group by source (stdlib, third-party, local); use parenthesized imports
- Naming: Classes: PascalCase, Functions/vars: snake_case, Constants: UPPER_SNAKE_CASE
- Error handling: Use try/except with specific exceptions, log errors with app.logger
- Types: Type annotations not currently used
- Documentation: Docstrings and Flask-RestX for API endpoints
- API patterns: Use Flask-RestX models for validation and documentation

## Project Structure
- Flask-based web controller for OpenHSI cameras
- RESTful API with Swagger documentation at `/api/apidocs`
- Static files in `/static` and templates in `/templates`