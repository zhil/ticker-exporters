#!/usr/bin/env python3

import logging
import time
import os
import yaml
import sys
import requests
import json
from stellar_base.address import Address
from prometheus_client import write_to_textfile, start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily, CounterMetricFamily

log = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=os.environ.get("LOGLEVEL", "INFO"))

settings = {}


def settings():
    global settings

    settings = {
        'stellar_exporter': {
            'prom_folder': '/var/lib/node_exporter',
            'interval': 30,
            'export': 'text',
            'listen_port': 9309,
            'accounts': [],
        },
    }
    config_file = '/etc/stellar_exporter/stellar_exporter.yaml'
    cfg = {}
    if os.path.isfile(config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
    if cfg.get('stellar_exporter'):
        if cfg['stellar_exporter'].get('prom_folder'):
            settings['stellar_exporter']['prom_folder'] = cfg['stellar_exporter']['prom_folder']
        if cfg['stellar_exporter'].get('interval'):
            settings['stellar_exporter']['interval'] = cfg['stellar_exporter']['interval']
        if cfg['stellar_exporter'].get('export') in ['text', 'http']:
            settings['stellar_exporter']['export'] = cfg['stellar_exporter']['export']
        if cfg['stellar_exporter'].get('listen_port'):
            settings['stellar_exporter']['listen_port'] = cfg['stellar_exporter']['listen_port']
        if isinstance(cfg['stellar_exporter'].get('accounts'), list):
            settings['stellar_exporter']['accounts'] = cfg['stellar_exporter']['accounts']


class StellarCollector:
    accounts = {}

    def _getAccounts(self):
        for account in settings['stellar_exporter']['accounts']:
            a = Address(address=account, network='public')
            a.get()
            for balance in a.balances:
                if balance.get('asset_code'):
                    currency = balance.get('asset_code')
                elif balance.get('asset_type') == 'native':
                    currency = 'XLM'
                else:
                    currency = balance.get('asset_type')
                self.accounts.update({
                    '{}-{}'.format(account, currency): {
                        'account': account,
                        'currency': currency,
                        'balance': float(balance.get('balance'))
                    }
                })

        log.debug('Found the following accounts: {}'.format(self.accounts))

    def collect(self):
        metrics = {
            'account_balance': GaugeMetricFamily(
                'account_balance',
                'Account Balance',
                labels=['source_currency', 'currency', 'account', 'type']
            ),
        }
        self._getAccounts()
        for a in self.accounts:
            metrics['account_balance'].add_metric(
                value=self.accounts[a]['balance'],
                labels=[
                    self.accounts[a]['currency'],
                    self.accounts[a]['currency'],
                    self.accounts[a]['account'],
                    'stellar',
                ]
            )
        for m in metrics.values():
            yield m


def _collect_to_text():
    e = StellarCollector()
    while True:
        write_to_textfile('{0}/stellar_exporter.prom'.format(settings['stellar_exporter']['prom_folder']), e)
        time.sleep(int(settings['stellar_exporter']['interval']))


def _collect_to_http():
    REGISTRY.register(StellarCollector())
    start_http_server(int(settings['stellar_exporter']['listen_port']))
    while True:
        time.sleep(int(settings['stellar_exporter']['interval']))


if __name__ == '__main__':
    settings()
    log.debug('Loaded settings: {}'.format(settings))
    if settings['stellar_exporter']['export'] == 'text':
        _collect_to_text()
    if settings['stellar_exporter']['export'] == 'http':
        _collect_to_http()
