![[Pasted image 20250324130015.png]]

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


#### setup Systemd auto start
from repo folder

`cp assets/openhsi-flask.service /etc/systemd/system/openhsi-flask.service `

`sudo systemctl daemon-reload`
`sudo systemctl enable openhsi-flask.service`
`sudo systemctl start openhsi-flask.service`


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












