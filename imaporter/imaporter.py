#!/usr/bin/env python3
import argparse
import configparser
import logging
import os
import signal
import subprocess
import sys
import time
import socket
import threading
import traceback
from dataclasses import dataclass
from typing import List, Tuple, Optional
from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError

logger = logging.getLogger('imaporter')

@dataclass
class SourceConfig:
    name: str
    host: str
    port: int
    ssl: bool
    username: str
    password: str
    delete_on_source: bool
    ham_label: str

@dataclass
class DestConfig:
    host: str
    port: int
    ssl: bool
    username: str
    password: str
    ham_folder: str
    spam_folder: str

@dataclass
class SpamConfig:
    enabled: bool
    max_size: int


class ConfigManager:
    def __init__(self, config_path: str):
        self.config = configparser.ConfigParser()
        if not self.config.read(config_path):
            raise FileNotFoundError(f"Config file '{config_path}' not found.")
            
    def get_sources(self) -> List[SourceConfig]:
        sources = []
        for section in self.config.sections():
            if section.startswith('source_'):
                name = section.replace('source_', '', 1)
                opts = self.config[section]
                
                sources.append(SourceConfig(
                    name=name,
                    host=opts.get('host'),
                    port=opts.getint('port', 993),
                    ssl=opts.getboolean('ssl', True),
                    username=opts.get('username'),
                    password=opts.get('password', ''),
                    delete_on_source=opts.getboolean('delete_on_source', True),
                    ham_label=opts.get('ham_label', '')
                ))
                
        # Support fallback legacy
        if not sources and 'source' in self.config.sections():
            opts = self.config['source']
            sources.append(SourceConfig(
                name="default",
                host=opts.get('host'),
                port=opts.getint('port', 993),
                ssl=opts.getboolean('ssl', True),
                username=opts.get('username'),
                password=opts.get('password', ''),
                delete_on_source=opts.getboolean('delete_on_source', True),
                ham_label=opts.get('ham_label', '')
            ))
            
        return sources

    def get_destination(self) -> DestConfig:
        opts = self.config['destination']
        return DestConfig(
            host=opts.get('host'),
            port=opts.getint('port', 993),
            ssl=opts.getboolean('ssl', True),
            username=opts.get('username'),
            password=opts.get('password', ''),
            ham_folder=opts.get('ham_folder', 'INBOX'),
            spam_folder=opts.get('spam_folder', '[Gmail]/Spam')
        )
        
    def get_spam_config(self) -> SpamConfig:
        opts = self.config['spamassassin']
        return SpamConfig(
            enabled=opts.getboolean('enabled', True),
            max_size=opts.getint('max_size', 5242880)
        )


class SpamFilter:
    def __init__(self, config: SpamConfig):
        self.config = config

    def score(self, raw_msg: bytes) -> Tuple[bool, bytes]:
        if not self.config.enabled:
            return False, raw_msg
            
        if len(raw_msg) > self.config.max_size:
            logger.warning(f"Message exceeds max_size ({len(raw_msg)} > {self.config.max_size}), skipping spam check.")
            return False, raw_msg

        try:
            result = subprocess.run(
                ['spamc', '-E'],
                input=raw_msg,
                capture_output=True,
                timeout=60
            )
            is_spam = (result.returncode == 1)
            scored_msg = result.stdout if result.stdout else raw_msg
            
            if result.returncode > 1:
                logger.error(f"spamc returned unexpected exit code {result.returncode}. Stderr: {result.stderr.decode(errors='ignore')}")
                is_spam = False

            return is_spam, scored_msg
        except Exception as e:
            logger.error(f"Failed to run spamc: {e}")
            return False, raw_msg


class IMAPConnection:
    def __init__(self, host: str, port: int, ssl: bool, username: str, password: str):
        self.host = host
        self.port = port
        self.ssl = ssl
        self.username = username
        self.password = password
        self.client: Optional[IMAPClient] = None

    def connect(self):
        logger.info(f"Connecting to IMAP {self.username}@{self.host}:{self.port} (SSL: {self.ssl})")
        self.client = IMAPClient(self.host, port=self.port, ssl=self.ssl, use_uid=True)
        self.client.login(self.username, self.password)

    def disconnect(self):
        if self.client:
            try:
                self.client.logout()
            except Exception:
                pass
            finally:
                self.client = None

    def ensure_folder(self, folder_name: str):
        try:
            self.client.select_folder(folder_name)
        except Exception:
            try:
                logger.info(f"Folder '{folder_name}' not found, attempting to create it...")
                self.client.create_folder(folder_name)
                self.client.select_folder(folder_name)
            except Exception as e:
                logger.error(f"Failed to create/select folder '{folder_name}': {e}")
                raise


class RelayWorker(threading.Thread):
    def __init__(self, source_conf: SourceConfig, dest_conf: DestConfig, spam_filter: SpamFilter, shutdown_event: threading.Event):
        super().__init__(name=f"Worker-{source_conf.name}")
        self.source_conf = source_conf
        self.dest_conf = dest_conf
        self.spam_filter = spam_filter
        self.shutdown_event = shutdown_event
        self.src_conn = IMAPConnection(source_conf.host, source_conf.port, source_conf.ssl, source_conf.username, source_conf.password)
        self.dst_conn = IMAPConnection(dest_conf.host, dest_conf.port, dest_conf.ssl, dest_conf.username, dest_conf.password)

    def connect_clients(self):
        if self.src_conn.client is None:
            self.src_conn.connect()
            self.src_conn.client.select_folder('INBOX')
        if self.dst_conn.client is None:
            self.dst_conn.connect()

    def process_unseen(self) -> bool:
        try:
            self.src_conn.client.select_folder('INBOX')
            messages = self.src_conn.client.search(['UNSEEN'])
        except Exception as e:
            logger.error(f"[{self.name}] Failed to search INBOX: {e}")
            return False

        if not messages:
            return True

        logger.info(f"[{self.name}] Found {len(messages)} unread messages to process.")

        for uid, msg_data in self.src_conn.client.fetch(messages, ['BODY.PEEK[]']).items():
            if self.shutdown_event.is_set():
                break

            raw_msg = msg_data.get(b'BODY[]')
            if not raw_msg:
                continue
            
            is_spam, scored_msg = self.spam_filter.score(raw_msg)
            logger.info(f"[{self.name}] Processing Msg UID {uid} | Size: {len(raw_msg)} | Spam: {is_spam}")
            
            delivered = False
            try:
                if is_spam:
                    self.dst_conn.ensure_folder(self.dest_conf.spam_folder)
                    self.dst_conn.client.append(self.dest_conf.spam_folder, scored_msg, flags=(b'Junk',))
                    logger.info(f"[{self.name}] Msg UID {uid} appended to {self.dest_conf.spam_folder} (Spam)")
                else:
                    self.dst_conn.ensure_folder(self.dest_conf.ham_folder)
                    res = self.dst_conn.client.append(self.dest_conf.ham_folder, scored_msg)
                    
                    ham_label = self.source_conf.ham_label
                    if ham_label and ham_label != self.dest_conf.ham_folder:
                        self.dst_conn.ensure_folder(ham_label)
                        parsed_uid = None
                        
                        if isinstance(res, tuple) and hasattr(res, 'uid'):
                            pass
                        elif type(res) == bytes and b'APPENDUID' in res:
                            parts = res.decode('utf-8').split()
                            for i, part in enumerate(parts):
                                if part == 'APPENDUID' and i + 2 < len(parts):
                                    parsed_uid = int(parts[i+2].strip(']'))
                                    break
                                    
                        if parsed_uid:
                            self.dst_conn.client.select_folder(self.dest_conf.ham_folder)
                            self.dst_conn.client.copy(parsed_uid, ham_label)
                            logger.info(f"[{self.name}] Msg UID {uid} appended and copied to {ham_label}")
                        else:
                            self.dst_conn.client.append(ham_label, scored_msg)
                            logger.info(f"[{self.name}] Msg UID {uid} double-appended to {ham_label} (No UID mapping)")
                    else:
                        logger.info(f"[{self.name}] Msg UID {uid} appended to {self.dest_conf.ham_folder}")
                
                delivered = True
            except Exception as e:
                logger.error(f"[{self.name}] Failed to deliver msg: {e}")
                # Bubble up so the worker disconnects and spawns a fresh dest_conn channel structure!
                raise
                
            if delivered:
                if self.source_conf.delete_on_source:
                    try:
                        self.src_conn.client.add_flags(uid, [b'\\Deleted'])
                        self.src_conn.client.expunge()
                        logger.info(f"[{self.name}] Msg UID {uid} deleted from source")
                    except Exception as e:
                        logger.error(f"[{self.name}] Failed to delete source msg {uid}: {e}")
                else:
                    try:
                        self.src_conn.client.add_flags(uid, [b'\\Seen'])
                        logger.info(f"[{self.name}] Msg UID {uid} retained on source tracking as Read")
                    except Exception as e:
                        logger.error(f"[{self.name}] Failed to mark Read: {e}")
                    
        return True

    def run(self):
        logger.info(f"[{self.name}] Starting worker thread.")
        while not self.shutdown_event.is_set():
            try:
                self.connect_clients()
                self.process_unseen()

                if self.shutdown_event.is_set():
                    break
                    
                logger.debug(f"[{self.name}] Entering IMAP IDLE state...")
                self.src_conn.client.idle()
                
                for _ in range(29 * 60):
                    if self.shutdown_event.is_set():
                        break
                    responses = self.src_conn.client.idle_check(timeout=1.0)
                    if responses:
                        break
                self.src_conn.client.idle_done()
                
            except (socket.error, socket.timeout, IMAPClientError) as e:
                logger.error(f"[{self.name}] Network/IMAP error: {e}")
                logger.info(f"[{self.name}] Reconnecting in 30 seconds...")
                self.src_conn.disconnect()
                self.dst_conn.disconnect()
                for _ in range(30):
                    if self.shutdown_event.is_set(): break
                    time.sleep(1)
            except Exception as e:
                logger.error(f"[{self.name}] Unexpected error: {e}\n{traceback.format_exc()}")
                for _ in range(60):
                    if self.shutdown_event.is_set(): break
                    time.sleep(1)
                    
        self.src_conn.disconnect()
        self.dst_conn.disconnect()
        logger.info(f"[{self.name}] Shut down gracefully.")


class RelayDaemon:
    def __init__(self, config_path: str):
        self.config_manager = ConfigManager(config_path)
        self.shutdown_event = threading.Event()
        self.workers: List[RelayWorker] = []

    def start(self):
        sources = self.config_manager.get_sources()
        dest = self.config_manager.get_destination()
        spam_filter = SpamFilter(self.config_manager.get_spam_config())

        if not sources:
            logger.fatal("No source configurations found. Exiting.")
            sys.exit(1)

        for source in sources:
            worker = RelayWorker(source, dest, spam_filter, self.shutdown_event)
            self.workers.append(worker)
            worker.start()

        # Keep main thread alive to catch signals
        try:
            while not self.shutdown_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    def stop(self):
        logger.info("Shutdown event triggered. Waiting for worker threads to finish safely...")
        self.shutdown_event.set()
        for worker in self.workers:
            worker.join()
        logger.info("All workers terminated. Daemon exiting.")


def main():
    parser = argparse.ArgumentParser(description='IMAPorter OOP - Mutli-threaded IMAP relay')
    parser.add_argument('--config', default='config.ini', help='Path to config file')
    parser.add_argument('--log-level', default=os.environ.get('IMAPORTER_LOG_LEVEL', 'INFO'),
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        type=str.upper,
                        help='Log level')
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    daemon = None

    def sigterm_handler(_signo, _stack_frame):
        logger.info("Received SIGTERM.")
        if daemon:
            daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, sigterm_handler)

    try:
        daemon = RelayDaemon(args.config)
        daemon.start()
    except Exception as e:
        logger.fatal(f"Daemon crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
