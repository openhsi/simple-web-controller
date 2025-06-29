# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands
- Create environment: `mamba create -n openhsi python==3.10 openhsi flask`
- Activate environment: `mamba activate openhsi`
- Run server: `python server.py`
- Run as service: `sudo systemctl start openhsi-flask.service`
- Service management: `sudo systemctl {start|stop|restart|status} openhsi-flask.service`
- View logs: `sudo journalctl -u openhsi-flask.service -f`

## Code Style Guidelines
- Indentation: 4 spaces
- Line length: ~88 characters (Black default)
- Imports: Group by source (stdlib, third-party, local); use parenthesized imports
- Naming: Classes: PascalCase, Functions/vars: snake_case, Constants: UPPER_SNAKE_CASE
- Error handling: Use try/except with specific exceptions, log errors with app.logger
- Types: Type annotations not currently used
- Documentation: Docstrings and Flask-RestX for API endpoints
- API patterns: Use Flask-RestX models for validation and documentation

## Architecture Overview

### Core Application Structure
- **Single-file Flask application** (`server.py`) with Flask-RestX for API documentation
- **Threaded camera operations** with global state management using thread locks
- **Real-time status polling** architecture for capture progress monitoring
- **Bootstrap-based responsive frontend** with tabbed interface

### Camera Integration Patterns
- **Custom OpenHSI camera wrapper** extending `FlirCamera` with progress callbacks
- **Thread-safe capture operations** using `capture_lock` and `capture_status` globals
- **Dual-tier settings system**: Basic settings (exposure, lines, processing) and advanced settings (binning, windowing, etc.)
- **Calibration file integration**: Hardcoded paths to `.json` settings and `.nc` calibration files

### API Architecture
- **RESTful endpoints** grouped by functionality (camera, file management, system)
- **Flask-RestX models** for request/response validation and auto-generated Swagger docs
- **Secure file operations** restricted to `/data` directory with path traversal protection
- **System time management** with sudo permission handling

### Frontend Communication
- **AJAX polling pattern** (500ms intervals) for real-time status updates
- **Tabbed interface** with Bootstrap for modular feature organization
- **Progress monitoring** with elapsed time and capture rate display
- **File browser integration** with download, view, and delete capabilities

### Key Global Variables
- `capture_lock`: Threading lock for camera operations
- `capture_status`: Dictionary tracking capture state, progress, and timing
- `log_messages`: Centralized logging system with timestamps and severity levels
- `current_camera`: Global camera instance for thread-safe operations

### File System Integration
- **Secure file browsing** within `/data` directory only
- **Multiple file operations**: view, download, delete files and empty folders
- **Image display options**: histogram equalization and contrast adjustment
- **Metadata extraction** for file listings

## Deployment Configuration
- **Systemd service**: Pre-configured in `assets/openhsi-flask.service`
- **Nginx reverse proxy**: Configuration in `assets/openhsi.ngnix`
- **Time permissions**: `setup_time_permissions.sh` for sudo date command access
- **Production settings**: Environment variables and user permissions for `openhsi` user