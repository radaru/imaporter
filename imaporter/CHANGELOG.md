# Changelog

## 1.1.0

- Added support for fetching from multiple source IMAP accounts
- Simplified credential management (moved from systemd secrets to direct config file authentication)
- Added SpamAssassin daemon integration improvements
- Refactored core logic

## 1.0.1

- Fix SpamAssassin "no rules were found" error by running sa-update during image build
- Run sa-update at each add-on startup to keep SpamAssassin rules fresh

## 1.0.0

- Initial Home Assistant add-on release
- IMAP IDLE push-based email fetching from external accounts
- Bundled SpamAssassin daemon for spam filtering
- Delivery to Gmail (or any IMAP server) via IMAP APPEND
- Gmail label support via APPENDUID/COPY
- Configurable log level (debug/info/warning/error)
- Option to delete or retain (mark read) emails on source
