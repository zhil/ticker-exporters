#!/usr/bin/env python3

import logging
import time
import os
import yaml
import sys
import requests
import json
from quoine.client import Quoinex
from prometheus_client import write_to_textfile, start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily, CounterMetricFamily

log = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=os.environ.get("LOGLEVEL", "INFO"))

settings = {}


def settings():
    global settings

    settings = {
        'quoine_exporter': {
            'prom_folder': '/var/lib/node_exporter',
            'interval': 30,
            'export': 'text',
            'listen_port': 9305,
            'api_key': '',
            'api_secret': '',
        },
    }
    config_file = '/etc/quoine_exporter/quoine_exporter.yaml'
    cfg = {}
    if os.path.isfile(config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
    if cfg.get('quoine_exporter'):
        if cfg['quoine_exporter'].get('prom_folder'):
            settings['quoine_exporter']['prom_folder'] = cfg['quoine_exporter']['prom_folder']
        if cfg['quoine_exporter'].get('interval'):
            settings['quoine_exporter']['interval'] = cfg['quoine_exporter']['interval']
        if cfg['quoine_exporter'].get('export') in ['text', 'http']:
            settings['quoine_exporter']['export'] = cfg['quoine_exporter']['export']
        if cfg['quoine_exporter'].get('listen_port'):
            settings['quoine_exporter']['listen_port'] = cfg['quoine_exporter']['listen_port']
        if cfg['quoine_exporter'].get('api_key'):
            settings['quoine_exporter']['api_key'] = cfg['quoine_exporter']['api_key']
        if cfg['quoine_exporter'].get('api_secret'):
            settings['quoine_exporter']['api_secret'] = cfg['quoine_exporter']['api_secret']


class QuoineCollector:
    rates = {}
    accounts = {}
    urls = {
        'quoinex': 'https://api.quoine.com',
        'qryptos': 'https://api.qryptos.com'
    }

    def __init__(self):
        self.client = Quoinex(settings['quoine_exporter']['api_key'], settings['quoine_exporter']['api_secret'])

    def _translate(self, currency):
        r = currency
        if currency == 'DASH':
            r = 'DSH'
        if currency == 'XBT':
            r = 'BTC'
        if currency == 'DOGE':
            r = 'XDG'
        if currency == 'STR':
            r = 'XLM'
        return r

    def _getExchangeRates(self):
        for url in self.urls:
            self.client.API_URL = self.urls[url]
            for ticker in self.client.get_products():
                if ticker.get('last_traded_price'):
                    if url not in self.rates:
                        self.rates.update({url: {}})
                    self.rates[url].update({
                        ticker.get('currency_pair_code'): {
                            'source_currency': self._translate(ticker.get('base_currency')),
                            'target_currency': self._translate(ticker.get('quoted_currency')),
                            'value': float(ticker.get('last_traded_price')),
                            'exchange': url,
                        }
                    })
                else:
                    log.debug('Skipping {} - no last_traded_price found.'.format(ticker.get('currency_pair_code')))

        log.debug('Found the following ticker rates: {}'.format(self.rates))

    def _getAccounts(self):
        for url in self.urls:
            self.client.API_URL = self.urls[url]
            for account in self.client.get_account_balances():
                if not self.accounts.get(url):
                    self.accounts[url] = {}
                self.accounts[url].update({
                    account['currency']: float(account['balance'])
                })

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
        self._getExchangeRates()
        for exchange in self.rates:
            for rate in self.rates[exchange]:
                metrics['exchange_rate'].add_metric(
                    value=self.rates[exchange][rate]['value'],
                    labels=[
                        self.rates[exchange][rate]['source_currency'],
                        self.rates[exchange][rate]['target_currency'],
                        exchange,
                    ]
                )
        self._getAccounts()
        for exchange in self.accounts:
            for currency in self.accounts[exchange]:
                metrics['account_balance'].add_metric(
                    value=self.accounts[exchange][currency],
                    labels=[
                        currency,
                        currency,
                        exchange,
                        exchange,
                    ]
                )
        for m in metrics.values():
            yield m


def _collect_to_text():
    e = QuoineCollector()
    while True:
        write_to_textfile('{0}/quoine_exporter.prom'.format(settings['quoine_exporter']['prom_folder']), e)
        time.sleep(int(settings['quoine_exporter']['interval']))


def _collect_to_http():
    REGISTRY.register(QuoineCollector())
    start_http_server(int(settings['quoine_exporter']['listen_port']))
    while True:
        time.sleep(int(settings['quoine_exporter']['interval']))


if __name__ == '__main__':
    settings()
    log.debug('Loaded settings: {}'.format(settings))
    if settings['quoine_exporter']['export'] == 'text':
        _collect_to_text()
    if settings['quoine_exporter']['export'] == 'http':
        _collect_to_http()
