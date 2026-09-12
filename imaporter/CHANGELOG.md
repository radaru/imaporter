# Changelog

## 1.3.1

- Fix `spamd` running as `nobody` by adding `-u root` flag (container runs as root intentionally)
- Fix Bayes lock file `Permission denied` error on `/data/spamassassin/bayes.lock` (side-effect of above)
- Disable DNSBL queries blocked for residential IPs (`multi.uribl.com`, `list.dnswl.org`, `zen.spamhaus.org`) via `dns_query_restriction` to eliminate repeated warnings

## 1.3.0

- Persist SpamAssassin Bayes database across container rebuilds (`/data/spamassassin/bayes`)
- Add system cron daemon (`crond`) for automated daily `sa-update` rule updates and seamless `spamd` reloading
- Add `perl-db_file` package for Berkeley DB Bayes storage support on Alpine Linux
- Improve IMAP connection resilience with exponential backoff on retries
- Add guaranteed cleanup via `try...finally` (only cleans up source if delivery succeeds)
- Add documentation and examples for manual sender and domain blocking (`blocklist_from`)

## 1.2.1

- Rename Home Assistant "Add-on" to "App" across the repository to align with latest terminology
- Update branded icon and logo for better presentation in the Home Assistant app store


## 1.2.0

- Expose `spamassassin_required_score` option in the app UI (default: 5.0)
- Support custom SpamAssassin rules via `/config/imaporter/spamassassin.cf`
- Fix `map` type from legacy `config:ro` to `homeassistant_config:ro`
- Add minimum Home Assistant version requirement (`2023.11.0`)
- Add official icon and logo for better presentation in the Home Assistant app store

## 1.1.0

- Added support for fetching from multiple source IMAP accounts
- Simplified credential management (moved from systemd secrets to direct config file authentication)
- Added SpamAssassin daemon integration improvements
- Refactored core logic

## 1.0.1

- Fix SpamAssassin "no rules were found" error by running sa-update during image build
- Run sa-update at each app startup to keep SpamAssassin rules fresh

## 1.0.0

- Initial Home Assistant app release
- IMAP IDLE push-based email fetching from external accounts
- Bundled SpamAssassin daemon for spam filtering
- Delivery to Gmail (or any IMAP server) via IMAP APPEND
- Gmail label support via APPENDUID/COPY
- Configurable log level (debug/info/warning/error)
- Option to delete or retain (mark read) emails on source
