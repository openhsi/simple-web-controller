![[assets/logo.png]]

## Install dependancies

### Miniforge
Download and install miniforge.
`wget "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"`
`bash Miniforge3-$(uname)-$(uname -m).sh`

### Openhsi env
make python env and install openhsi+depenacies (match python version to that required by FLIR/Spinaker)
`mamba create -n openhsi python==3.10 openhsi flask`
`mamba activate openhsi`

The rest assume you have openhsi env activated etc.

### # Spinnaker SDK (FLIR camera, see openhsi docs for other cameras)
Download SDK.
https://www.teledynevisionsolutions.com/products/spinnaker-sdk/?model=Spinnaker%20SDK&vertical=machine%20vision&segment=iis

#### Spinnaker SDK 4.2.0.46 for Ubuntu 22.04 (January 10, 2025)
https://flir.netx.net/file/asset/68772/original/attachment - 64-bit ARM  SDK
https://flir.netx.net/file/asset/68774/original/attachment - Python 3.10 aarch64

`wget -O spinnaker_python-4.2.0.46-cp310-cp310-linux_aarch64-22.04.tar.gz https://flir.netx.net/file/asset/68774/original/attachment
`wget -O spinnaker-4.2.0.46-arm64-22.04-pkg.tar.gz https://flir.netx.net/file/asset/68772/original/attachment`

`tar -xvzf spinnaker_python-4.2.0.46-cp310-cp310-linux_aarch64-22.04.tar.gz`
`tar -xvzf spinnaker-4.2.0.46-arm64-22.04-pkg.tar.gz`

`sudo apt-get install libusb-1.0-0 qtbase5-dev qtchooser qt5-qmake qtbase5-dev-tools`
`sudo sh install_spinnaker_arm.sh`

Answer yes to all quesitons. At "Adding new members to usergroup flirimaging", and any users on system that need to access camera., eg. *openhsi* user.

`pip install spinnaker_python-4.2.0.46-cp310-cp310-linux_aarch64.whl --no-deps`
`pip install simple-pyspin --no-deps`

## Install OpenHSI Orlar code
Clone or download this repo.


#### Setup Systemd Auto Start

##### Raspberry Pi Permissions Note
By default on Raspberry Pi, the original user (typically `pi`) has sudo NOPASSWD privileges configured in `/etc/sudoers.d/010_pi-nopasswd`. This means the default user can run sudo commands without entering a password.

##### Service Installation
From the repo folder:

```bash
# Copy the service file to systemd directory
sudo cp assets/openhsi-flask.service /etc/systemd/system/openhsi-flask.service

# Edit the service file to match your paths (if different from default)
sudo nano /etc/systemd/system/openhsi-flask.service

# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable openhsi-flask.service

# Start the service now
sudo systemctl start openhsi-flask.service

# Check service status
sudo systemctl status openhsi-flask.service
```

##### Service Management Commands
```bash
# Start the service
sudo systemctl start openhsi-flask.service

# Stop the service
sudo systemctl stop openhsi-flask.service

# Restart the service
sudo systemctl restart openhsi-flask.service

# Check service status and logs
sudo systemctl status openhsi-flask.service
sudo journalctl -u openhsi-flask.service -f  # Follow logs in real-time
sudo journalctl -u openhsi-flask.service --since today  # Today's logs
```

##### Time Permissions Setup
The OpenHSI application may need to set the system time for synchronization purposes. The included `setup_time_permissions.sh` script configures the necessary permissions:

**Note for Raspberry Pi OS:** The default Raspberry Pi OS does not require this permissions script. The default user (typically `pi`) already has passwordless sudo access for all commands via `/etc/sudoers.d/010_pi-nopasswd`. This script is useful for:
- Non-Raspberry Pi systems
- Custom user accounts without full sudo access
- Production deployments where you want to limit sudo permissions to only the `date` command

```bash
# Make the script executable
chmod +x setup_time_permissions.sh

# Run as root to set up time permissions for the openhsi user
sudo ./setup_time_permissions.sh

# Or specify a different user
sudo ./setup_time_permissions.sh myuser
```

**What the script does:**
1. **Creates a sudoers rule** in `/etc/sudoers.d/openhsi-time`
2. **Allows the specified user** (default: `openhsi`) to run `sudo date` without password
3. **Sets proper permissions** (440) on the sudoers file for security
4. **Validates syntax** using `visudo -c` to prevent system lockout

**Security Note:** This only grants permission to run the `date` command with sudo, not full sudo access.

**Usage after setup:**
```bash
# The openhsi user can now set system time without password prompt
sudo date -s '2024-12-25 10:30:00'
```

## Updating the System

### Update OpenHSI Package
To update the OpenHSI package to the latest version:

```bash
# Activate the openhsi environment
mamba activate openhsi

# Update OpenHSI package
mamba update openhsi

# Or update all packages in the environment
mamba update --all
```

### Update Repository Code

#### Update to Latest Development Version
```bash
# Navigate to the repository directory
cd /path/to/simple-web-controller

# Pull latest changes from the dev branch (active development)
git pull origin dev

# Or pull from main branch (stable releases)
git pull origin main

# Restart the service to apply changes
sudo systemctl restart openhsi-flask.service
```

#### Update to Specific Release
```bash
# Navigate to the repository directory
cd /path/to/simple-web-controller

# Fetch all tags and releases
git fetch --tags

# List available release tags
git tag -l

# Checkout a specific release (replace v1.2.3 with desired version)
git checkout v1.2.3

# Restart the service to apply changes
sudo systemctl restart openhsi-flask.service
```

#### Check Current Version
```bash
# Check current git commit/tag
git describe --tags --always

# Check current branch
git branch --show-current

# View recent commits
git log --oneline -5
```

### Update Workflow
1. Stop the service: `sudo systemctl stop openhsi-flask.service`
2. Update OpenHSI package (if needed): `mamba update openhsi`
3. Update repository code: `git pull` or `git checkout <tag>`
4. Start the service: `sudo systemctl start openhsi-flask.service`
5. Check service status: `sudo systemctl status openhsi-flask.service`


#### ngnix port 80 proxy
Setup ngnix proxy so interface can accessed via browser without port.

`sudo apt update`
`sudo apt install nginx`

`sudo rm /etc/nginx/sites-enabled/default`
`sudp cp assets//openhsi.ngnix /etc/nginx/sites-available/openhsi`
`sudo ln -s /etc/nginx/sites-available/openhsi /etc/nginx/sites-enabled/`

`sudo nginx -t`
`sudo systemctl reload nginx`


##  Setup Tailscale (FOR REMOTE  ACCESS)
Depending on use case and deployment, it may be sensible to setup a remote access system, such as tailscale.com












