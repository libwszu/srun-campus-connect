"""Interruptible monitoring with a shared lock for sign-in operations."""

import threading

from .client import SrunClient, SrunError, check_connectivity


def run_monitor(settings, stop, emit, auth_lock=None):
    auth_lock = auth_lock or threading.Lock()
    failures = 0
    emit("log", "Monitoring started.", {})
    try:
        while not stop.is_set():
            online = check_connectivity(settings.profile)
            failures = 0 if online else failures + 1
            emit("status", "Online" if online else "Offline", {})
            emit("log", "Network is online." if online else "Consecutive failures: {count}", {"count": failures})
            if not online and failures >= 2 and settings.auto_login:
                if not settings.username or not settings.password:
                    emit("log", "Credentials missing; automatic sign-in skipped.", {})
                elif auth_lock.acquire(blocking=False):
                    try:
                        for attempt in range(1, settings.reconnect_retries + 1):
                            if stop.is_set():
                                break
                            emit("log", "Automatic sign-in attempt {attempt}/{total}.", {"attempt": attempt, "total": settings.reconnect_retries})
                            client = SrunClient(settings.profile, settings.username, settings.password)
                            try:
                                client.login()
                                emit("log", "Signed in successfully.", {})
                            except SrunError as error:
                                emit("error", str(error), {})
                            finally:
                                client.close()
                            if stop.wait(settings.retry_delay):
                                break
                            if check_connectivity(settings.profile):
                                failures = 0
                                emit("status", "Online", {})
                                emit("log", "Network is online.", {})
                                break
                    finally:
                        auth_lock.release()
            emit("log", "Next check in {seconds} seconds.", {"seconds": settings.check_interval})
            if stop.wait(settings.check_interval):
                break
    finally:
        emit("log", "Monitoring stopped.", {})
        emit("stopped", "Idle", {})
