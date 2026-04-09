#!/usr/bin/env python3
import configparser
import logging
import signal
import subprocess
import sys
import time
import traceback
from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError
import socket

# Configure logging to go to stdout (systemd will capture this)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('imaporter')

def load_config(config_path='config.ini'):
    config = configparser.ConfigParser()
    config.read(config_path)
    return config

def connect_imap(config_section_opts, section_name=None):
    host = config_section_opts.get('host')
    port = config_section_opts.getint('port', 993)
    ssl = config_section_opts.getboolean('ssl', True)
    username = config_section_opts.get('username')
    password = config_section_opts.get('password')

    # Secure Systemd Credentials override
    import os
    cred_dir = os.environ.get('CREDENTIALS_DIRECTORY')
    if cred_dir and section_name:
        cred_file = os.path.join(cred_dir, f"{section_name}_password")
        if os.path.exists(cred_file):
            with open(cred_file, 'r') as f:
                password = f.read().strip()
                logger.debug(f"Loaded {section_name} password from systemd secure credentials.")

    logger.info(f"Connecting to IMAP {username}@{host}:{port} (SSL: {ssl})")
    client = IMAPClient(host, port=port, ssl=ssl, use_uid=True)
    client.login(username, password)
    return client

def ensure_folder(client, folder_name):
    # Attempt to select it, if it fails, try creating it
    try:
        client.select_folder(folder_name)
    except Exception:
        try:
            logger.info(f"Folder '{folder_name}' not found, attempting to create it...")
            client.create_folder(folder_name)
            client.select_folder(folder_name)
        except Exception as e:
            logger.error(f"Failed to create/select folder '{folder_name}': {e}")
            raise

def check_spam(raw_msg, max_size):
    """
    Pipes the raw_msg through spamc -E to check for spam.
    Returns (is_spam_boolean, scored_raw_msg_bytes).
    """
    if len(raw_msg) > max_size:
        logger.warning(f"Message exceeds max_size ({len(raw_msg)} > {max_size}), skipping spam check.")
        return False, raw_msg

    try:
        # -E returns exit code 1 if spam, 0 if ham
        result = subprocess.run(
            ['spamc', '-E'],
            input=raw_msg,
            capture_output=True,
            timeout=60
        )
        is_spam = (result.returncode == 1)
        # Even if error, if stdout has content we use it, otherwise fall back to original
        scored_msg = result.stdout if result.stdout else raw_msg
        
        # If exit code > 1, it generally means an error occurred in spamc
        if result.returncode > 1:
            logger.error(f"spamc returned unexpected exit code {result.returncode}. Stderr: {result.stderr.decode(errors='ignore')}")
            is_spam = False

        return is_spam, scored_msg
    except Exception as e:
        logger.error(f"Failed to run spamc: {e}")
        return False, raw_msg

def process_new_emails(src_client, dst_client, config):
    try:
        src_client.select_folder('INBOX')
        messages = src_client.search(['UNSEEN'])
    except Exception as e:
        logger.error(f"Failed to search INBOX: {e}")
        return False

    if not messages:
        return True

    logger.info(f"Found {len(messages)} unread messages to process.")
    
    spam_enabled = config['spamassassin'].getboolean('enabled', True)
    max_size = config['spamassassin'].getint('max_size', 5242880)
    ham_folder = config['destination'].get('ham_folder', 'INBOX')
    ham_label = config['destination'].get('ham_label', '')
    spam_folder = '[Gmail]/Spam'
    delete_source = config['source'].getboolean('delete_on_source', True)

    for uid, msg_data in src_client.fetch(messages, ['BODY.PEEK[]']).items():
        raw_msg = msg_data.get(b'BODY[]')
        if not raw_msg:
            continue

        raw_size = len(raw_msg)
        
        if spam_enabled:
            is_spam, scored_msg = check_spam(raw_msg, max_size)
        else:
            is_spam = False
            scored_msg = raw_msg
            
        logger.info(f"Processing Msg UID {uid} | Size: {raw_size} | Spam: {is_spam}")
        
        delivered = False
        try:
            if is_spam:
                # Provide Junk keyword/flag
                dst_client.append(spam_folder, scored_msg, flags=(b'Junk',))
                logger.info(f"Msg UID {uid} appended to {spam_folder} (Spam)")
            else:
                # Ham
                ensure_folder(dst_client, ham_folder)
                res = dst_client.append(ham_folder, scored_msg)
                
                if ham_label and ham_label != ham_folder:
                    ensure_folder(dst_client, ham_label)
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
                        dst_client.select_folder(ham_folder)
                        dst_client.copy(parsed_uid, ham_label)
                        logger.info(f"Msg UID {uid} appended to {ham_folder} and copied to {ham_label} (Label added)")
                    else:
                        dst_client.append(ham_label, scored_msg)
                        logger.info(f"Msg UID {uid} appended to both {ham_folder} and {ham_label}")
                else:
                    logger.info(f"Msg UID {uid} appended to {ham_folder}")
            
            delivered = True
        except Exception as e:
            logger.error(f"Failed to deliver msg to destination: {e}")
            # Do NOT delete from source if delivery failed
            break
            
        if delivered:
            if delete_source:
                try:
                    src_client.add_flags(uid, [b'\\Deleted'])
                    src_client.expunge() # or wait to expunge all after loop
                    logger.info(f"Msg UID {uid} deleted from source")
                except Exception as e:
                    logger.error(f"Failed to delete source msg {uid}: {e}")
            else:
                try:
                    src_client.add_flags(uid, [b'\\Seen'])
                    logger.info(f"Msg UID {uid} retained on source and marked Read (delete_on_source=false)")
                except Exception as e:
                    logger.error(f"Failed to mark source msg {uid} as Read: {e}")
                
    return True

def run_loop(config):
    src_client = None
    dst_client = None

    while True:
        try:
            # Reconnect or initialize clients
            if src_client is None:
                src_client = connect_imap(config['source'], 'source')
                src_client.select_folder('INBOX')
                
            if dst_client is None:
                dst_client = connect_imap(config['destination'], 'destination')

            # Process any existing unseen messages first
            process_new_emails(src_client, dst_client, config)

            # Enter IDLE
            logger.info("Entering IMAP IDLE state...")
            src_client.idle()
            
            # Wait for up to 29 minutes for an event (RFC recommends re-issue IDLE at 29m)
            responses = src_client.idle_check(timeout=29*60)
            
            logger.info(f"IDLE check returned: {responses}")
            src_client.idle_done()
            
            # We woke up, loop will restart and call process_new_emails

        except (socket.error, socket.timeout, IMAPClientError) as e:
            logger.error(f"Network/IMAP error: {e}")
            logger.info("Attempting to reconnect in 30 seconds...")
            
            if src_client:
                try: src_client.logout()
                except: pass
                src_client = None
                
            if dst_client:
                try: dst_client.logout()
                except: pass
                dst_client = None
                
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"Unexpected error: {e}\n{traceback.format_exc()}")
            time.sleep(60)

def sigterm_handler(_signo, _stack_frame):
    logger.info("Received SIGTERM, shutting down gracefully.")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, sigterm_handler)
    
    try:
        conf = load_config()
    except Exception as e:
        logger.fatal(f"Could not load config file: {e}")
        sys.exit(1)
        
    logger.info("Starting IMAPorter service.")
    run_loop(conf)
