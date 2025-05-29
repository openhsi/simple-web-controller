"""
Systemd service management for Simple Web Controller.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import Optional


def get_current_user():
    """Get the current user name."""
    return os.getenv('USER') or os.getenv('USERNAME')


def get_python_executable():
    """Get the path to the current Python executable."""
    return sys.executable


def get_simple_web_controller_executable():
    """Get the path to the simple-web-controller executable."""
    # Try to find the executable in the current environment
    executable_path = shutil.which('simple-web-controller')
    if executable_path:
        return executable_path
    
    # If not found, construct the path based on the Python executable
    python_dir = Path(sys.executable).parent
    simple_web_controller_path = python_dir / 'simple-web-controller'
    
    if simple_web_controller_path.exists():
        return str(simple_web_controller_path)
    
    # Fall back to using python -m
    return f"{sys.executable} -m simple_web_controller.cli"


def create_service_file(
    working_directory: str,
    config_file: str = "config.yaml",
    user: Optional[str] = None,
    host: str = "127.0.0.1",
    port: int = 5000,
    service_name: str = "simple-web-controller"
) -> str:
    """
    Create a systemd service file content.
    
    Args:
        working_directory: Directory where the service should run
        config_file: Path to the config file (relative to working directory)
        user: User to run the service as (defaults to current user)
        host: Host to bind to
        port: Port to bind to
        service_name: Name of the service
    
    Returns:
        Service file content as string
    """
    if user is None:
        user = get_current_user()
    
    executable = get_simple_web_controller_executable()
    
    # Build the command
    if config_file == "config.yaml":
        # Default config file
        exec_start = f"{executable} --host {host} --port {port}"
    else:
        # Custom config file
        exec_start = f"{executable} --config {config_file} --host {host} --port {port}"
    
    service_content = f"""[Unit]
Description=Simple Web Controller - OpenHSI Flask Web Server
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory={working_directory}
ExecStart={exec_start}
Restart=always
RestartSec=3
Environment=FLASK_ENV=production

[Install]
WantedBy=multi-user.target
"""
    
    return service_content


def install_service(
    working_directory: str,
    config_file: str = "config.yaml",
    user: Optional[str] = None,
    host: str = "127.0.0.1",
    port: int = 5000,
    service_name: str = "simple-web-controller",
    enable: bool = True,
    start: bool = False
) -> bool:
    """
    Install and optionally enable/start the systemd service.
    
    Args:
        working_directory: Directory where the service should run
        config_file: Path to the config file
        user: User to run the service as
        host: Host to bind to
        port: Port to bind to
        service_name: Name of the service
        enable: Whether to enable the service
        start: Whether to start the service after installation
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Create service file content
        service_content = create_service_file(
            working_directory=working_directory,
            config_file=config_file,
            user=user,
            host=host,
            port=port,
            service_name=service_name
        )
        
        # Service file path
        service_file_path = f"/etc/systemd/system/{service_name}.service"
        
        print(f"Creating systemd service file: {service_file_path}")
        print("Service content:")
        print("-" * 50)
        print(service_content)
        print("-" * 50)
        
        # Write service file (requires sudo)
        write_cmd = ['sudo', 'tee', service_file_path]
        result = subprocess.run(
            write_cmd,
            input=service_content,
            text=True,
            capture_output=True
        )
        
        if result.returncode != 0:
            print(f"Error writing service file: {result.stderr}")
            return False
        
        # Reload systemd
        print("Reloading systemd daemon...")
        reload_result = subprocess.run(['sudo', 'systemctl', 'daemon-reload'], capture_output=True)
        if reload_result.returncode != 0:
            print(f"Error reloading systemd: {reload_result.stderr.decode()}")
            return False
        
        # Enable service if requested
        if enable:
            print(f"Enabling service {service_name}...")
            enable_result = subprocess.run(['sudo', 'systemctl', 'enable', service_name], capture_output=True)
            if enable_result.returncode != 0:
                print(f"Error enabling service: {enable_result.stderr.decode()}")
                return False
        
        # Start service if requested
        if start:
            print(f"Starting service {service_name}...")
            start_result = subprocess.run(['sudo', 'systemctl', 'start', service_name], capture_output=True)
            if start_result.returncode != 0:
                print(f"Error starting service: {start_result.stderr.decode()}")
                return False
        
        print(f"✓ Service {service_name} installed successfully!")
        
        if enable and not start:
            print(f"To start the service, run: sudo systemctl start {service_name}")
        
        print(f"To check service status: sudo systemctl status {service_name}")
        print(f"To view logs: sudo journalctl -u {service_name} -f")
        
        return True
        
    except Exception as e:
        print(f"Error installing service: {e}")
        return False


def uninstall_service(service_name: str = "simple-web-controller") -> bool:
    """
    Uninstall the systemd service.
    
    Args:
        service_name: Name of the service to uninstall
    
    Returns:
        True if successful, False otherwise
    """
    try:
        service_file_path = f"/etc/systemd/system/{service_name}.service"
        
        # Stop the service if running
        print(f"Stopping service {service_name}...")
        stop_result = subprocess.run(['sudo', 'systemctl', 'stop', service_name], capture_output=True)
        
        # Disable the service
        print(f"Disabling service {service_name}...")
        disable_result = subprocess.run(['sudo', 'systemctl', 'disable', service_name], capture_output=True)
        
        # Remove service file
        if os.path.exists(service_file_path):
            print(f"Removing service file: {service_file_path}")
            remove_result = subprocess.run(['sudo', 'rm', service_file_path], capture_output=True)
            if remove_result.returncode != 0:
                print(f"Error removing service file: {remove_result.stderr.decode()}")
                return False
        
        # Reload systemd
        print("Reloading systemd daemon...")
        reload_result = subprocess.run(['sudo', 'systemctl', 'daemon-reload'], capture_output=True)
        if reload_result.returncode != 0:
            print(f"Error reloading systemd: {reload_result.stderr.decode()}")
            return False
        
        print(f"✓ Service {service_name} uninstalled successfully!")
        return True
        
    except Exception as e:
        print(f"Error uninstalling service: {e}")
        return False


def service_status(service_name: str = "simple-web-controller") -> None:
    """
    Show the status of the systemd service.
    
    Args:
        service_name: Name of the service
    """
    try:
        result = subprocess.run(['systemctl', 'status', service_name], capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
    except Exception as e:
        print(f"Error checking service status: {e}")