import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from jobs.relay import sweep_stuck, tick
from jobs.transports import get_transport

SWEEP_EVERY_S = 60


class Command(BaseCommand):
    help = 'Publish pending jobs from the outbox to the configured transport (local or sqs).'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true',
                            help='Run one tick and one sweep, wait for local jobs to finish, then exit.')

    def handle(self, *args, **opts):
        transport = get_transport()
        self.stdout.write(f'relay: transport={settings.JOB_TRANSPORT} interval={settings.RELAY_INTERVAL_S}s')
        last_sweep = None
        try:
            while True:
                close_old_connections()
                try:
                    n = tick(transport)
                    if n:
                        self.stdout.write(f'relay: published {n}')
                    if last_sweep is None or time.monotonic() - last_sweep > SWEEP_EVERY_S:
                        swept = sweep_stuck()
                        if any(swept.values()):
                            self.stdout.write(f'relay: sweep {swept}')
                        last_sweep = time.monotonic()
                except Exception as e:  # e.g. a database blip: a long-running relay must survive it
                    if opts['once']:
                        raise
                    self.stderr.write(f'relay: error {e!r}; retrying')
                if opts['once']:
                    return
                time.sleep(settings.RELAY_INTERVAL_S)
        except KeyboardInterrupt:
            self.stdout.write('relay: stopping')
        finally:
            # --once: let local handlers finish. Ctrl-C or a crash: don't hang on a backlog; whatever is
            # abandoned is still in the outbox or under a lease, and the next relay picks it up.
            transport.close(wait=bool(opts['once']))
