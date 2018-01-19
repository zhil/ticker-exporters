#!/usr/bin/env python3

import logging
import time
import os
import yaml
import sys
import requests
import json
from prometheus_client import write_to_textfile, start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily, CounterMetricFamily

log = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=os.environ.get("LOGLEVEL", "INFO"))

settings = {}


def _settings():
    global settings

    settings = {
        'ripple_exporter': {
            'prom_folder': '/var/lib/node_exporter',
            'interval': 60,
            'url': 'https://data.ripple.com',
            'addresses': [],
            'export': 'text',
            'listen_port': 9306,
        },
    }
    config_file = '/etc/ripple_exporter/ripple_exporter.yaml'
    cfg = {}
    if os.path.isfile(config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
    else:
        log.warning('Config file not found')
    if cfg.get('ripple_exporter'):
        if cfg['ripple_exporter'].get('prom_folder'):
            settings['ripple_exporter']['prom_folder'] = cfg['ripple_exporter']['prom_folder']
        if cfg['ripple_exporter'].get('interval'):
            settings['ripple_exporter']['interval'] = cfg['ripple_exporter']['interval']
        if cfg['ripple_exporter'].get('url'):
            settings['ripple_exporter']['url'] = cfg['ripple_exporter']['url']
        if cfg['ripple_exporter'].get('addresses'):
            settings['ripple_exporter']['addresses'] = cfg['ripple_exporter']['addresses']
        if cfg['ripple_exporter'].get('export') in ['text', 'http']:
            settings['ripple_exporter']['export'] = cfg['ripple_exporter']['export']
        if cfg['ripple_exporter'].get('listen_port'):
            settings['ripple_exporter']['listen_port'] = cfg['ripple_exporter']['listen_port']


class RippleCollector:
    accounts = {}

    def _get_balance(self, address):
        url = '{}/v2/accounts/{}/balances'.format(
            settings['ripple_exporter']['url'],
            address
        )
        log.debug('URL: {}'.format(url))

        try:
            r = requests.get(url).json()
            log.debug('Response: {}'.format(r))
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ReadTimeout
        ) as e:
            log.warning("Can't connect to {}. The error received follows.".format(
                settings['ripple_exporter']['url']
            ))
            log.warning(e)

        if r.get('result') == 'success' and r.get('balances'):
            for balance in r.get('balances'):
                log.debug('Registering balance {balance} for the currency {currency} - account {account}'.format(
                    balance=balance['value'],
                    currency=balance['currency'],
                    account=address
                ))
                self.accounts.update({
                    address: {
                        'value': float(balance['value']),
                        'currency': balance['currency'],
                        'type': 'ripple',
                    }
                })
        else:
            log.warning('Could not retrieve balance. The result follows.')
            log.warning('{}: {}'.format(r.get('result'), r.get('message')))

    def collect(self):
        metrics = {
            'account_balance': GaugeMetricFamily(
                'account_balance',
                'Account Balance',
                labels=['source_currency', 'currency', 'account', 'type']
            ),
        }
        for address in settings['ripple_exporter']['addresses']:
            self._get_balance(address=address)
        for account in self.accounts:
            metrics['account_balance'].add_metric(
                value=self.accounts[account]['value'],
                labels=[
                    self.accounts[account]['currency'],
                    self.accounts[account]['currency'],
                    account,
                    self.accounts[account]['type']
                ]
            )

        for m in metrics.values():
            yield m


def _collect_to_text():
    e = RippleCollector()
    while True:
        write_to_textfile('{0}/ripple_exporter.prom'.format(settings['ripple_exporter']['prom_folder']), e)
        time.sleep(int(settings['ripple_exporter']['interval']))


def _collect_to_http():
    REGISTRY.register(RippleCollector())
    start_http_server(int(settings['ripple_exporter']['listen_port']))
    while True:
        time.sleep(int(settings['ripple_exporter']['interval']))


if __name__ == '__main__':
    settings()
    log.debug('Loaded settings: {}'.format(settings))
    if settings['ripple_exporter']['export'] == 'text':
        _collect_to_text()
    if settings['ripple_exporter']['export'] == 'http':
        _collect_to_http()
