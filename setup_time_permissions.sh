#\!/bin/bash

# Setup script to allow the openhsi user to set system time without password
# This script must be run as root (sudo)

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (use sudo)"
    exit 1
fi

# Get the username that will run the Flask application
USERNAME=${1:-openhsi}

echo "Setting up time permissions for user: $USERNAME"

# Create sudoers rule to allow the user to run date command without password
SUDOERS_FILE="/etc/sudoers.d/openhsi-time"

cat > "$SUDOERS_FILE" << INNER_EOF
# Allow $USERNAME to set system time without password
$USERNAME ALL=(ALL) NOPASSWD: /bin/date
INNER_EOF

# Set proper permissions on the sudoers file
chmod 440 "$SUDOERS_FILE"

# Verify the sudoers file syntax
if visudo -c -f "$SUDOERS_FILE"; then
    echo "Successfully created sudoers rule: $SUDOERS_FILE"
    echo "User $USERNAME can now set system time using: sudo date -s 'YYYY-MM-DD HH:MM:SS'"
else
    echo "Error: Invalid sudoers syntax, removing file"
    rm -f "$SUDOERS_FILE"
    exit 1
fi

echo "Setup complete\!"
EOF < /dev/null
