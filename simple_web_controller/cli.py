#!/usr/bin/env python3
"""
Command line interface for the Simple Web Controller.
"""

import sys
import os
import argparse
from pathlib import Path

from . import server
from .server import app, load_config, add_log_message
from .systemd import install_service, uninstall_service, service_status


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="OpenHSI Flask Web Controller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run the server
  simple-web-controller                    # Use default config.yaml
  simple-web-controller -c my_config.yaml # Use custom config file
  simple-web-controller --host 0.0.0.0    # Bind to all interfaces
  
  # Service management
  simple-web-controller install-service   # Install systemd service
  simple-web-controller service-status    # Check service status
  simple-web-controller uninstall-service # Remove systemd service
        """
    )
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Server command (default)
    server_parser = subparsers.add_parser('server', help='Run the web server (default)')
    server_parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    server_parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host to bind to (default: 127.0.0.1)'
    )
    server_parser.add_argument(
        '--port', '-p',
        type=int,
        default=5000,
        help='Port to bind to (default: 5000)'
    )
    server_parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode (overrides config)'
    )
    
    # Service management commands
    install_parser = subparsers.add_parser('install-service', help='Install systemd service')
    install_parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    install_parser.add_argument(
        '--working-directory',
        default=os.getcwd(),
        help='Working directory for the service (default: current directory)'
    )
    install_parser.add_argument(
        '--user',
        help='User to run the service as (default: current user)'
    )
    install_parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host to bind to (default: 127.0.0.1)'
    )
    install_parser.add_argument(
        '--port', '-p',
        type=int,
        default=5000,
        help='Port to bind to (default: 5000)'
    )
    install_parser.add_argument(
        '--service-name',
        default='simple-web-controller',
        help='Name of the systemd service (default: simple-web-controller)'
    )
    install_parser.add_argument(
        '--enable',
        action='store_true',
        default=True,
        help='Enable the service to start on boot (default: true)'
    )
    install_parser.add_argument(
        '--no-enable',
        action='store_true',
        help='Do not enable the service to start on boot'
    )
    install_parser.add_argument(
        '--start',
        action='store_true',
        help='Start the service after installation'
    )
    
    uninstall_parser = subparsers.add_parser('uninstall-service', help='Uninstall systemd service')
    uninstall_parser.add_argument(
        '--service-name',
        default='simple-web-controller',
        help='Name of the systemd service (default: simple-web-controller)'
    )
    
    status_parser = subparsers.add_parser('service-status', help='Check systemd service status')
    status_parser.add_argument(
        '--service-name',
        default='simple-web-controller',
        help='Name of the systemd service (default: simple-web-controller)'
    )
    
    # Add the original arguments as top-level for backward compatibility
    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host to bind to (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=5000,
        help='Port to bind to (default: 5000)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode (overrides config)'
    )
    
    return parser.parse_args()


def run_server(args):
    """Run the web server."""
    # Check if config file exists
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Configuration file '{args.config}' not found")
        print(f"Please create a config file or specify a different path with --config")
        sys.exit(1)
    
    try:
        # Update the server module to use the specified config
        server.config = load_config(args.config)
        
        # Re-extract configuration values in the server module
        server.json_path = server.config['camera']['json_path']
        server.cal_path = server.config['camera']['cal_path']
        server.default_camera_settings = server.config['camera']['default_settings']
        server.data_directory = server.config['files']['data_directory']
        server.default_save_directory = server.config['files']['default_save_directory']
        server.max_log_messages = server.config['logging']['max_log_messages']
        server.server_debug = server.config['server']['debug']
        server.server_threaded = server.config['server']['threaded']
        
        # Reinitialize camera with new config
        server.cam = server.openhsiCamera(
            n_lines=server.default_camera_settings['n_lines'],
            exposure_ms=server.default_camera_settings['exposure_ms'],
            processing_lvl=server.default_camera_settings['processing_lvl'],
            json_path=server.json_path,
            cal_path=server.cal_path,
        )
        
        # Get server settings from config, allow CLI args to override
        debug = args.debug or server.server_debug
        threaded = server.server_threaded
        
        print(f"Starting Simple Web Controller...")
        print(f"Config file: {args.config}")
        print(f"Server: http://{args.host}:{args.port}")
        print(f"API docs: http://{args.host}:{args.port}/api/apidocs")
        
        # Add initial log message
        add_log_message("Server started", "success")
        
        # Start the Flask app
        app.run(
            host=args.host,
            port=args.port,
            debug=debug,
            threaded=threaded
        )
        
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)


def handle_install_service(args):
    """Handle service installation."""
    # Check if config file exists
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Configuration file '{args.config}' not found")
        print(f"Please create a config file or specify a different path with --config")
        sys.exit(1)
    
    # Handle enable/no-enable logic
    enable = args.enable and not args.no_enable
    
    success = install_service(
        working_directory=args.working_directory,
        config_file=args.config,
        user=args.user,
        host=args.host,
        port=args.port,
        service_name=args.service_name,
        enable=enable,
        start=args.start
    )
    
    if not success:
        sys.exit(1)


def handle_uninstall_service(args):
    """Handle service uninstallation."""
    success = uninstall_service(service_name=args.service_name)
    if not success:
        sys.exit(1)


def handle_service_status(args):
    """Handle service status check."""
    service_status(service_name=args.service_name)


def main():
    """Main entry point for the CLI."""
    args = parse_args()
    
    # Handle different commands
    if args.command == 'install-service':
        handle_install_service(args)
    elif args.command == 'uninstall-service':
        handle_uninstall_service(args)
    elif args.command == 'service-status':
        handle_service_status(args)
    elif args.command == 'server' or args.command is None:
        # Default to server command for backward compatibility
        run_server(args)
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == '__main__':
    main()