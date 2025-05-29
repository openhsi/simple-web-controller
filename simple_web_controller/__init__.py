"""
Simple Web Controller for OpenHSI cameras.

A Flask-based web interface for controlling and managing OpenHSI hyperspectral cameras.
"""

__version__ = "1.1.0"
__author__ = "OpenHSI Team"

from .server import app

__all__ = ["app"]