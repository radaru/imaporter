#!/usr/bin/env bash
set -e

APP_DIR="/opt/imaporter"
SYS_USER="imaporter"

echo "Checking dependencies..."
if ! command -v spamc &> /dev/null; then
    echo "Warning: spamc is not installed. Will not be able to process spam locally."
    echo "Please run: sudo apt install spamassassin spamc"
fi

if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed. Exiting."
    exit 1
fi

echo "Creating system user '${SYS_USER}'..."
if ! id -u ${SYS_USER} > /dev/null 2>&1; then
    useradd -r -s /usr/sbin/nologin ${SYS_USER}
fi

echo "Setting up application directory '${APP_DIR}'..."
mkdir -p ${APP_DIR}

# Always copy core Python scripts and requirements
cp imaporter.py ${APP_DIR}/
cp requirements.txt ${APP_DIR}/

# Only map a template config if one is missing so we don't overwrite passwords
if [ ! -f "${APP_DIR}/config.ini" ]; then
    echo "Copying default config.ini template..."
    cp config.ini ${APP_DIR}/
fi

echo "Setting up Python Virtual Environment..."
# Ensure the apt virtual environment module is physically present if on Raspbian/Ubuntu
if ! dpkg -s python3-venv >/dev/null 2>&1; then
    echo "Installing python3-venv..."
    apt-get update && apt-get install -y python3-venv
fi

python3 -m venv ${APP_DIR}/venv
${APP_DIR}/venv/bin/pip install --upgrade pip
${APP_DIR}/venv/bin/pip install -r ${APP_DIR}/requirements.txt

echo "Setting permissions..."
chown -R ${SYS_USER}:${SYS_USER} ${APP_DIR}
# config.ini requires careful permissions
chmod 600 ${APP_DIR}/config.ini
chmod 755 ${APP_DIR}/imaporter.py

echo "Setting up secure systemd credentials folder..."
mkdir -p /etc/imaporter
chown root:root /etc/imaporter
chmod 700 /etc/imaporter

for cred in "source.secret" "destination.secret"; do
    if [ ! -f "/etc/imaporter/$cred" ]; then
        touch /etc/imaporter/$cred
        chown root:root /etc/imaporter/$cred
        chmod 600 /etc/imaporter/$cred
    fi
done

echo "Installing systemd service..."
cp imaporter.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable imaporter.service

echo ""
echo "Installation Finished!"
echo "---------------------------------------------------------"
echo "1. Configure IMAP settings: sudo nano ${APP_DIR}/config.ini"
echo "2. Add your Source Password securely:"
echo "   sudo nano /etc/imaporter/source.secret"
echo "3. Add your Gmail App Password securely:"
echo "   sudo nano /etc/imaporter/destination.secret"
echo "4. Start the service: sudo systemctl start imaporter"
echo "5. View live logs: make run-logs"
echo "---------------------------------------------------------"
