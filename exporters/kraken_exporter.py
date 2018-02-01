#!/usr/bin/env python3

import logging
import time
import os
import yaml
import sys
import requests
import json
import ccxt
from prometheus_client import write_to_textfile, start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily, CounterMetricFamily

log = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=os.environ.get("LOGLEVEL", "INFO"))

settings = {}


def _settings():
    global settings

    settings = {
        'kraken_exporter': {
            'prom_folder': '/var/lib/node_exporter',
            'interval': 60,
            'api_key': None,
            'api_secret': None,
            'export': 'text',
            'listen_port': 9303,
        },
    }
    config_file = '/etc/kraken_exporter/kraken_exporter.yaml'
    cfg = {}
    if os.path.isfile(config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
    if cfg.get('kraken_exporter'):
        if cfg['kraken_exporter'].get('prom_folder'):
            settings['kraken_exporter']['prom_folder'] = cfg['kraken_exporter']['prom_folder']
        if cfg['kraken_exporter'].get('interval'):
            settings['kraken_exporter']['interval'] = cfg['kraken_exporter']['interval']
        if cfg['kraken_exporter'].get('api_key'):
            settings['kraken_exporter']['api_key'] = cfg['kraken_exporter']['api_key']
        if cfg['kraken_exporter'].get('private_key'):
            settings['kraken_exporter']['private_key'] = cfg['kraken_exporter']['private_key']
        if cfg['kraken_exporter'].get('export') in ['text', 'http']:
            settings['kraken_exporter']['export'] = cfg['kraken_exporter']['export']
        if cfg['kraken_exporter'].get('listen_port'):
            settings['kraken_exporter']['listen_port'] = cfg['kraken_exporter']['listen_port']


class KrakenCollector:
    rates = {}
    accounts = {}
    hasApiCredentials = False

    def __init__(self):
        self.kraken = ccxt.kraken()
        if (settings['kraken_exporter'].get('api_key') and (settings['kraken_exporter'].get('private_key'))):
            self.kraken.apiKey = settings['kraken_exporter'].get('api_key')
            self.kraken.secret = settings['kraken_exporter'].get('private_key')
            self.hasApiCredentials = True

    def _getTickers(self):
        """
        Gets the price ticker.
        """
        self.kraken.loadMarkets(True)

        tickers = self.kraken.fetch_tickers()

        for ticker in tickers:
            currencies = ticker.split('/')
            pair = {
                'source_currency': currencies[0],
                'target_currency': currencies[1],
                'value': float(tickers[ticker]['last']),
            }

            self.rates.update({
                '{}'.format(ticker): pair
            })

        log.debug('Found the following ticker rates: {}'.format(self.rates))

    def _getAccounts(self):
        if self.hasApiCredentials:
            accounts = self.kraken.fetch_balance()
            self.accounts = {}
            if accounts.get('free'):
                for currency in accounts['free']:
                    if not self.accounts.get(currency):
                        self.accounts.update({currency: {}})
                    self.accounts[currency].update({'free': accounts['free'][currency]})
            if accounts.get('used'):
                for currency in accounts['used']:
                    if not self.accounts.get(currency):
                        self.accounts.update({currency: {}})
                    self.accounts[currency].update({'used': accounts['used'][currency]})

        log.debug('Found the following accounts: {}'.format(self.accounts))

    def collect(self):
        metrics = {
            'exchange_rate': GaugeMetricFamily(
                'exchange_rate',
                'Current exchange rates',
                labels=['source_currency', 'target_currency', 'exchange']
            ),
            'account_balance': GaugeMetricFamily(
                'account_balance',
                'Account Balance',
                labels=['source_currency', 'currency', 'account', 'type']
            ),
        }
        self._getTickers()
        for rate in self.rates:
            metrics['exchange_rate'].add_metric(
                value=self.rates[rate]['value'],
                labels=[
                    self.rates[rate]['source_currency'],
                    self.rates[rate]['target_currency'],
                    'kraken'
                ]
            )

        self._getAccounts()
        for currency in self.accounts:
            for account_type in self.accounts[currency]:  # free / used
                if (self.accounts[currency][account_type] > 0):
                    metrics['account_balance'].add_metric(
                        value=(self.accounts[currency][account_type]),
                        labels=[
                            currency,
                            currency,
                            account_type,
                            'kraken'
                        ]
                    )

        for m in metrics.values():
            yield m


def _collect_to_text():
    e = KrakenCollector()
    while True:
        write_to_textfile('{0}/kraken_exporter.prom'.format(settings['kraken_exporter']['prom_folder']), e)
        time.sleep(int(settings['kraken_exporter']['interval']))


def _collect_to_http():
    REGISTRY.register(KrakenCollector())
    start_http_server(int(settings['kraken_exporter']['listen_port']))
    while True:
        time.sleep(int(settings['kraken_exporter']['interval']))


if __name__ == '__main__':
    _settings()
    log.debug('Loaded settings: {}'.format(settings))
    if settings['kraken_exporter']['export'] == 'text':
        _collect_to_text()
    if settings['kraken_exporter']['export'] == 'http':
        _collect_to_http()
