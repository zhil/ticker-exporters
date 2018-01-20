#!/usr/bin/env python3

import logging
import time
import os
import yaml
import sys
import requests
import json
from binance.client import Client as Binance
from prometheus_client import write_to_textfile, start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily, CounterMetricFamily

log = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=os.environ.get("LOGLEVEL", "INFO"))

settings = {}


def settings():
    global settings

    settings = {
        'binance_exporter': {
            'prom_folder': '/var/lib/node_exporter',
            'interval': 30,
            'export': 'text',
            'listen_port': 9308,
            'api_key': '',
            'api_secret': '',
        },
    }
    config_file = '/etc/binance_exporter/binance_exporter.yaml'
    cfg = {}
    if os.path.isfile(config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
    if cfg.get('binance_exporter'):
        if cfg['binance_exporter'].get('prom_folder'):
            settings['binance_exporter']['prom_folder'] = cfg['binance_exporter']['prom_folder']
        if cfg['binance_exporter'].get('interval'):
            settings['binance_exporter']['interval'] = cfg['binance_exporter']['interval']
        if cfg['binance_exporter'].get('export') in ['text', 'http']:
            settings['binance_exporter']['export'] = cfg['binance_exporter']['export']
        if cfg['binance_exporter'].get('listen_port'):
            settings['binance_exporter']['listen_port'] = cfg['binance_exporter']['listen_port']
        if cfg['binance_exporter'].get('api_key'):
            settings['binance_exporter']['api_key'] = cfg['binance_exporter']['api_key']
        if cfg['binance_exporter'].get('api_secret'):
            settings['binance_exporter']['api_secret'] = cfg['binance_exporter']['api_secret']


class BinanceCollector:
    rates = {}
    accounts = {}

    def __init__(self):
        self.client = Binance(settings['binance_exporter']['api_key'], settings['binance_exporter']['api_secret'])

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
        for ticker in self.client.get_all_tickers():
            pair = ticker.get('symbol')
            value = ticker.get('price')
            source_currency = pair[:-3]
            target_currency = pair[-3:]
            if pair[-4:] == 'USDT':
                source_currency = pair[:-4]
                target_currency = pair[-4:]
            self.rates.update({pair: {
                'source_currency': self._translate(source_currency),
                'target_currency': self._translate(target_currency),
                'value': float(value),
            }})

        log.debug('Found the following ticker rates: {}'.format(self.rates))

    def _getAccounts(self):
        accounts = self.client.get_account()
        for account in accounts.get('balances'):
            """ Only show the accounts that actually have a value """
            if (
                float(account['free']) > 0
                or float(account['locked']) > 0
            ):
                self.accounts.update({
                    account['asset']: float(account['free'])
                })
            elif self.accounts.get(account['asset']):
                del self.accounts[account['asset']]

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
        self._getExchangeRates()
        for rate in self.rates:
            metrics['exchange_rate'].add_metric(
                value=self.rates[rate]['value'],
                labels=[
                    self.rates[rate]['source_currency'],
                    self.rates[rate]['target_currency'],
                    'binance',
                ]
            )
        self._getAccounts()
        for currency in self.accounts:
            metrics['account_balance'].add_metric(
                value=self.accounts[currency],
                labels=[
                    currency,
                    currency,
                    'binance',
                    'binance',
                ]
            )
        for m in metrics.values():
            yield m


def _collect_to_text():
    e = BinanceCollector()
    while True:
        write_to_textfile('{0}/binance_exporter.prom'.format(settings['binance_exporter']['prom_folder']), e)
        time.sleep(int(settings['binance_exporter']['interval']))


def _collect_to_http():
    REGISTRY.register(BinanceCollector())
    start_http_server(int(settings['binance_exporter']['listen_port']))
    while True:
        time.sleep(int(settings['binance_exporter']['interval']))


if __name__ == '__main__':
    settings()
    log.debug('Loaded settings: {}'.format(settings))
    if settings['binance_exporter']['export'] == 'text':
        _collect_to_text()
    if settings['binance_exporter']['export'] == 'http':
        _collect_to_http()
