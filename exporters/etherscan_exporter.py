#!/usr/bin/env python3

import logging
import time
import os
import yaml
import sys
import requests
import json
from operator import itemgetter
from prometheus_client import write_to_textfile, start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily, CounterMetricFamily

log = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=os.environ.get("LOGLEVEL", "INFO"))

settings = {}


def _settings():
    global settings

    settings = {
        'etherscan_exporter': {
            'prom_folder': '/var/lib/node_exporter',
            'interval': 60,
            'api_key': False,
            'export': 'text',
            'listen_port': 9308,
            'url': 'https://api.etherscan.io/api',
            'addresses': [],
            'tokens': [],
        },
    }
    config_file = '/etc/etherscan_exporter/etherscan_exporter.yaml'
    cfg = {}
    if os.path.isfile(config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
    if cfg.get('etherscan_exporter'):
        if cfg['etherscan_exporter'].get('prom_folder'):
            settings['etherscan_exporter']['prom_folder'] = cfg['etherscan_exporter']['prom_folder']
        if cfg['etherscan_exporter'].get('interval'):
            settings['etherscan_exporter']['interval'] = cfg['etherscan_exporter']['interval']
        if cfg['etherscan_exporter'].get('api_key'):
            settings['etherscan_exporter']['api_key'] = cfg['etherscan_exporter']['api_key']
        if cfg['etherscan_exporter'].get('url'):
            settings['etherscan_exporter']['url'] = cfg['etherscan_exporter']['url']
        if cfg['etherscan_exporter'].get('export') in ['text', 'http']:
            settings['etherscan_exporter']['export'] = cfg['etherscan_exporter']['export']
        if cfg['etherscan_exporter'].get('listen_port'):
            settings['etherscan_exporter']['listen_port'] = cfg['etherscan_exporter']['listen_port']
        if cfg['etherscan_exporter'].get('addresses'):
            settings['etherscan_exporter']['addresses'] = cfg['etherscan_exporter']['addresses']
        if cfg['etherscan_exporter'].get('tokens'):
            settings['etherscan_exporter']['tokens'] = cfg['etherscan_exporter']['tokens']


class EtherscanCollector:
    accounts = {}
    tokens = {}

    def _get_tokens(self):
        # Ensure that we don't get blocked
        time.sleep(1)
        for account in self.accounts:
            for token in settings['etherscan_exporter']['tokens']:
                request_data = {
                    'module': 'account',
                    'action': 'tokenbalance',
                    'contractaddress': token['contract'],
                    'address': account,
                    'tag': 'latest',
                    'apikey': settings['etherscan_exporter']['api_key'],
                }
                decimals = 18
                if token.get('decimals', -1) >= 0:
                    decimals = int(token['decimals'])
                log.debug('{} decimals for {}'.format(decimals, token['short']))
                try:
                    r = requests.get(settings['etherscan_exporter']['url'], params=request_data).json()
                except (
                    requests.exceptions.ConnectionError,
                    requests.exceptions.ReadTimeout,
                    requests.packages.urllib3.exceptions.ReadTimeoutError
                ) as e:
                    log.warning(e)
                    r = {}
                if r.get('result') and int(r['result']) > 0:
                    self.tokens.update({
                        '{}-{}'.format(account, token['short']): {
                            'account': account,
                            'name': token['name'],
                            'name_short': token['short'],
                            'contract_address': token['contract'],
                            'value': int(r['result']) / (10**decimals) if decimals > 0 else int(r['result'])
                        }
                    })
        log.debug('Tokens: {}'.format(self.tokens))

    def _get_balances(self):
        request_data = {
            'module': 'account',
            'action': 'balancemulti',
            'address': ','.join(settings['etherscan_exporter']['addresses']),
            'tag': 'latest',
            'apikey': settings['etherscan_exporter']['api_key'],
        }
        log.debug('Request data: {}'.format(request_data))
        try:
            r = requests.get(settings['etherscan_exporter']['url'], params=request_data).json()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ReadTimeout,
            requests.packages.urllib3.exceptions.ReadTimeoutError
        ) as e:
            log.warning(e)
            r = {}
        if r.get('message') == 'OK' and r.get('result'):
            for result in r.get('result'):
                self.accounts.update({
                    result['account']: float(result['balance'])/(1000000000000000000)
                })
        log.debug('Accounts: {}'.format(self.accounts))

    def collect(self):
        metrics = {
            'account_balance': GaugeMetricFamily(
                'account_balance',
                'Account Balance',
                labels=['source_currency', 'currency', 'account', 'type']
            ),
        }
        self._get_balances()
        for account in self.accounts:
            metrics['account_balance'].add_metric(
                value=(self.accounts[account]),
                labels=[
                    'ETH',
                    'ETH',
                    account,
                    'etherscan'
                ]
            )

        self._get_tokens()
        for token in self.tokens:
            metrics['account_balance'].add_metric(
                value=(self.tokens[token]['value']),
                labels=[
                    self.tokens[token]['name_short'],
                    self.tokens[token]['name_short'],
                    self.tokens[token]['account'],
                    'etherscan'
                ]
            )
        for m in metrics.values():
            yield m


def _collect_to_text():
    while True:
        e = EtherscanCollector()
        write_to_textfile('{0}/etherscan_exporter.prom'.format(settings['etherscan_exporter']['prom_folder']), e)
        time.sleep(int(settings['etherscan_exporter']['interval']))


def _collect_to_http():
    REGISTRY.register(EtherscanCollector())
    start_http_server(int(settings['etherscan_exporter']['listen_port']))
    while True:
        time.sleep(int(settings['etherscan_exporter']['interval']))


if __name__ == '__main__':
    _settings()
    log.debug('Loaded settings: {}'.format(settings))
    if settings['etherscan_exporter']['export'] == 'text':
        _collect_to_text()
    if settings['etherscan_exporter']['export'] == 'http':
        _collect_to_http()
