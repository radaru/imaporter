# Home Assistant Add-on: IMAPorter

IMAPorter fetches emails from an external IMAP account using IMAP IDLE push
notifications, optionally filters them through the bundled SpamAssassin, and
delivers them into a Gmail (or any IMAP) account via IMAP APPEND.

## How it works

1. Connects to your source IMAP server and enters IDLE mode
2. When new email arrives, fetches the message
3. If SpamAssassin is enabled, pipes it through `spamc` for spam scoring
4. Delivers the message to the destination IMAP account:
   - Spam goes to the configured spam folder (e.g., `[Gmail]/Spam`)
   - Ham goes to the ham folder and optionally gets a Gmail label applied
5. Deletes the message from source (or marks it read, based on config)
6. Returns to IDLE and waits for the next message

## Configuration

### Source account

- **Source IMAP Host**: Your external email provider's IMAP server
- **Source Port**: Usually `993` for SSL
- **Source Username**: Your email address on the source account
- **Source Password**: Your password or app-specific password
- **Source SSL**: Enable SSL/TLS (recommended)
- **Source Folder**: Folder to monitor, usually `INBOX`
- **Delete from Source**: If enabled, emails are deleted after delivery;
  if disabled, they are marked as read

### Destination account (Gmail)

- **Destination IMAP Host**: `imap.gmail.com` for Gmail
- **Destination Port**: `993`
- **Destination Username**: Your Gmail address
- **Destination Password**: A Gmail **App Password**
  (see [Google's guide](https://support.google.com/accounts/answer/185833))
- **Destination SSL**: Enable SSL/TLS (recommended)
- **Ham Folder**: Where to deliver legitimate emails (`INBOX`)
- **Ham Label**: Optional Gmail label to apply (leave empty to skip)
- **Spam Folder**: Where to deliver spam (`[Gmail]/Spam`)

### SpamAssassin

- **Enable SpamAssassin**: Toggle spam filtering on/off
- **Max Size**: Messages larger than this (in bytes) skip spam scanning.
  Default is 5,242,880 (5 MB).

### Logging

- **Log Level**: Set to `debug`, `info`, `warning`, or `error`

## Why was this built?

Google deprecated the "Check mail from other accounts" POP3/IMAP feature.
IMAPorter replaces that functionality with a self-hosted solution that runs
on your Home Assistant instance, giving you control over spam filtering and
email routing.

## Support

For issues and feature requests, visit the
[GitHub repository](https://github.com/st4nson/imaporter).
