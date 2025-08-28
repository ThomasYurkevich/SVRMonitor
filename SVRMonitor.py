import requests
import yagmail
import time
import threading
import logging
import sys
import os

URLS = [
    "x",
    "x",
    "x"
]

RECEIVER_EMAIL = "x"
SENDER_EMAIL = "x"
SENDER_PASSWORD = "x"

REBOOT_INTERVAL_MINUTES = 60
FAILURE_THRESHOLD = 3
RECHECK_INTERVAL = 15
MONITOR_INTERVAL = 60
REQUEST_TIMEOUT = 10

INITIAL_DOWN_ALERT_DELAY_MINUTES = 5
SUBSEQUENT_DOWN_ALERT_INTERVAL_MINUTES = 2

server_failure_counts = {url: 0 for url in URLS}
server_down_since = {url: None for url in URLS}
server_last_alert_sent = {url: None for url in URLS}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
    handlers=[
        logging.FileHandler("server_monitor.log"),
        logging.StreamHandler()
    ]
)

def check_website_status(url):
    try:
        response = requests.get(url, verify=False, timeout=REQUEST_TIMEOUT)
        if 200 <= response.status_code < 400:
            logging.debug(f"{url} returned status code {response.status_code} (Up)")
            return "Up"
        else:
            logging.info(f"{url} returned non-success status code: {response.status_code}")
            return "Down"
    except requests.exceptions.Timeout:
        logging.warning(f"{url} timed out after {REQUEST_TIMEOUT} seconds.")
        return "Down"
    except requests.exceptions.ConnectionError:
        logging.warning(f"{url} connection error (could not reach server).")
        return "Down"
    except Exception as e:
        logging.error(f"{url} encountered an unexpected error: {e}", exc_info=True)
        return "Down"

def send_email(subject, body, receiver, sender_email, sender_password):
    try:
        yag = yagmail.SMTP(user=sender_email, password=sender_password)
        yag.send(
            to=receiver,
            subject=subject,
            contents=body
        )
        logging.info(f"Email sent: '{subject}' to {receiver}")
    except Exception as e:
        logging.error(f"Failed to send email: {e}", exc_info=True)

def monitor_server(url, receiver, sender_email, sender_password):
    global server_failure_counts, server_down_since, server_last_alert_sent
    threading.current_thread().name = f"Monitor-{url.split('//')[1].split('/')[0]}"

    INITIAL_DOWN_ALERT_DELAY_MINUTES = 7

    while True:
        status = check_website_status(url)
        current_time = time.time()

        if status == "Down":
            server_failure_counts[url] += 1

            if server_failure_counts[url] >= FAILURE_THRESHOLD:
                if server_down_since[url] is None:
                    server_down_since[url] = current_time
                    logging.warning(f"{url} confirmed consistently down. Starting {INITIAL_DOWN_ALERT_DELAY_MINUTES}-minute alert delay countdown.")
                else:
                    time_down = current_time - server_down_since[url]
                    logging.info(f"{url} is still down (approx. {int(time_down / 60)}m {int(time_down % 60)}s).")

                if server_down_since[url] is not None:
                    time_down = current_time - server_down_since[url]
                    initial_alert_delay_seconds = INITIAL_DOWN_ALERT_DELAY_MINUTES * 60

                    if time_down >= initial_alert_delay_seconds and server_last_alert_sent[url] is None:
                        subject = f"CRITICAL: Server Down Alert - {url}"
                        body = (f"The server '{url}' has been continuously down for at least "
                                f"{INITIAL_DOWN_ALERT_DELAY_MINUTES} minutes.")
                        send_email(subject, body, receiver, sender_email, sender_password)
                        server_last_alert_sent[url] = current_time
                        logging.warning(f"Initial alert sent for {url} at {time.strftime('%Y-%m-%d %H:%M:%S')}")

                    elif server_last_alert_sent[url] is not None:
                        time_since_last_alert = current_time - server_last_alert_sent[url]
                        subsequent_alert_interval_seconds = SUBSEQUENT_DOWN_ALERT_INTERVAL_MINUTES * 60

                        if time_since_last_alert >= subsequent_alert_interval_seconds:
                            subject = f"REMINDER: Server Still Down - {url}"
                            body = (f"The server '{url}' is still down. It has been down for approximately "
                                    f"{int(time_down / 60)} minutes and {int(time_down % 60)} seconds.")
                            send_email(subject, body, receiver, sender_email, sender_password)
                            server_last_alert_sent[url] = current_time
                            logging.warning(f"Subsequent alert sent for {url} at {time.strftime('%Y-%m-%d %H:%M:%S')}")

            else:
                logging.info(f"{url} is down (consecutive failures: {server_failure_counts[url]}/{FAILURE_THRESHOLD}). Re-checking soon...")

            time.sleep(RECHECK_INTERVAL)

        else: 
            if server_failure_counts[url] >= FAILURE_THRESHOLD and server_last_alert_sent[url] is not None:
                subject = f"RESOLVED: Server Back Up - {url}"
                down_duration = current_time - server_down_since[url]
                body = (f"The server '{url}' is now back up. It was down for approximately "
                        f"{int(down_duration / 60)} minutes and {int(down_duration % 60)} seconds.")
                send_email(subject, body, receiver, sender_email, sender_password)
                logging.info(f"Recovery alert sent for {url} at {time.strftime('%Y-%m-%d %H:%M:%S')}")

            server_failure_counts[url] = 0
            server_down_since[url] = None
            server_last_alert_sent[url] = None
            logging.info(f"{url} is up. Next check in {MONITOR_INTERVAL} seconds.")
            time.sleep(MONITOR_INTERVAL)

if __name__ == "__main__":
    logging.info("Starting server monitoring application.")

    threads = []
    for url in URLS:
        thread = threading.Thread(target=monitor_server, args=(url, RECEIVER_EMAIL, SENDER_EMAIL, SENDER_PASSWORD), daemon=True)
        threads.append(thread)
        thread.start()
        logging.info(f"Started monitoring thread for: {url}")

    last_reboot_check_time = time.time()
    reboot_interval_seconds = REBOOT_INTERVAL_MINUTES * 60

    try:
        while True:
            current_time = time.time()
            if current_time - last_reboot_check_time >= reboot_interval_seconds:
                logging.info(f"Rebooting the Raspberry Pi as {REBOOT_INTERVAL_MINUTES} minutes have passed.")
                os.system("sudo reboot")

            time.sleep(1) 
    except KeyboardInterrupt:
        logging.info("Interrupted. Exiting.")
    except Exception as e:
        logging.error(f"An unexpected error occurred in the main thread: {e}", exc_info=True)
    finally:
        logging.info("Server monitoring application shutting down.")
