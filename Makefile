.PHONY: install uninstall update run-logs enable disable

install:
	@echo "Installing IMAPorter..."
	@sudo bash install.sh

uninstall:
	@echo "Uninstalling IMAPorter..."
	@sudo systemctl stop imaporter.service || true
	@sudo systemctl disable imaporter.service || true
	@sudo rm -f /etc/systemd/system/imaporter.service
	@sudo systemctl daemon-reload
	@echo "Removing /opt/imaporter/..."
	@sudo rm -rf /opt/imaporter/
	@echo "Uninstallation complete."

update:
	@echo "Updating IMAPorter Script code..."
	@sudo systemctl stop imaporter.service || true
	@sudo cp imaporter.py /opt/imaporter/
	@sudo chown imaporter:imaporter /opt/imaporter/imaporter.py
	@sudo chmod 755 /opt/imaporter/imaporter.py
	@sudo systemctl start imaporter.service
	@echo "Update complete."

run-logs:
	@sudo journalctl -u imaporter.service -f

enable:
	@sudo systemctl enable --now imaporter.service

disable:
	@sudo systemctl disable --now imaporter.service
