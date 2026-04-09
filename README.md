# IMAPorter

A self-hosted IMAP proxy script running as a `systemd` daemon.

Google is officially deprecating the ability to natively pull emails into Gmail from external POP3/IMAP accounts (via the legacy "Check mail from other accounts" setting). This project serves as a robust self-hosted replacement for that functionality. 

It connects to any external IMAP account, fetches unread emails via efficient IMAP `IDLE` state checking, runs them natively through local `SpamAssassin` rules, and then securely delivers them directly into your target Gmail account.

Features:
- **Instant IMAP IDLE Push Validation**: Polls cleanly without exhausting server resources.
- **SpamAssassin Integration**: Automatically flags or moves spam to the `[Gmail]/Spam` folder based on robust local header execution (Optional and can be disabled in `config.ini`).
- **Custom Deduplication and Labels**: Configurable hooks to cleanly copy mail to specific label endpoints natively bypassing Gmail POP3 limits.
- **Systemd Integration**: Securely loads proxy credentials out of memory without retaining configuration files in plain text using `LoadCredential`.

---

## Installation

This application is designed specifically to run headless cleanly on Linux instances like Raspbian or Ubuntu via systemd wrappers.

1. **Install OS Dependencies**:
   You only need Python and SpamAssassin installed globally:
   ```bash
   sudo apt update
   sudo apt install spamassassin spamc python3-venv tzdata
   ```

2. **Configure SpamAssassin**:
   Enable the daemon so it accepts connections from the `spamc` client:
   ```bash
   sudo systemctl enable --now spamassassin
   ```

3. **Install the Application**:
   Just run `make install` in the project directory. This completely sandboxes python requirements into a `/opt/` virtual-environment and installs the systemd unit file automatically.
   ```bash
   sudo make install
   ```

4. **Prepare Passwords and Config**:
   Update `config.ini` substituting with your explicit account details:
   ```bash
   sudo nano /opt/imaporter/config.ini
   ```
   Provide your passwords to the secure systemd credential stores (these files are provisioned locked to root-only, so `config.ini` stays free of cleartext passwords):
   ```bash
   sudo nano /etc/imaporter/source.secret
   sudo nano /etc/imaporter/destination.secret
   ```

5. **Start Systemd Daemon**:
   ```bash
   sudo systemctl restart imaporter.service
   ```

You can view the processing logs securely at any time by running:
```bash
make run-logs
```

---

## Generating Gmail Passwords (2-Factor Authentication)

When a Gmail account has 2-Step Verification (2FA) enabled, you can no longer use your standard Google password for programmatic IMAP connections. Instead, you must generate an **App Password**. 

An App Password is a 16-character passcode that grants an app or device permission to bypass standard 2FA prompts and access your Google Account exclusively for standard protocols (like IMAP and SMTP).

1. Go to your Google Account management page: [myaccount.google.com](https://myaccount.google.com/).
2. On the left navigation panel, click on **Security**.
3. Under the section *"How you sign in to Google"*, look for **2-Step Verification** and click on it. You may need to sign in again. (If you don't have 2-Step Verification turned on, you must enable it first).
4. Scroll to the very bottom of the 2-Step Verification page and click on **App passwords**.
5. You’ll be asked to *"Select app"* and *"Select device"*. 
   - App: Select **Mail** (or "Other (Custom name)" and type `Email-Relay-Script`).
   - Device: Select **Other (Custom name)** and type something like `Raspberry-Pi`.
6. Click **Generate**.
7. Google will present you with a 16-character app passcode in a yellow bar (it looks like `abcd efgh ijkl mnop`). 

Place this exact 16-character string into the secure `/etc/imaporter/destination.secret` file and restart your daemon.

---

## Contributing

Pull Requests are welcome! If you think of robust improvements to IMAP error handling or spam-validation flags, feel free to contribute.

## License

This project is licensed under the MIT License.
