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
        'bitstamp_exporter': {
            'prom_folder': '/var/lib/node_exporter',
            'interval': 60,
            'api_key': None,
            'api_secret': None,
            'export': 'text',
            'listen_port': 9307,
        },
    }
    config_file = '/etc/bitstamp_exporter/bitstamp_exporter.yaml'
    cfg = {}
    if os.path.isfile(config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
    if cfg.get('bitstamp_exporter'):
        if cfg['bitstamp_exporter'].get('prom_folder'):
            settings['bitstamp_exporter']['prom_folder'] = cfg['bitstamp_exporter']['prom_folder']
        if cfg['bitstamp_exporter'].get('interval'):
            settings['bitstamp_exporter']['interval'] = cfg['bitstamp_exporter']['interval']
        if cfg['bitstamp_exporter'].get('api_key'):
            settings['bitstamp_exporter']['api_key'] = cfg['bitstamp_exporter']['api_key']
        if cfg['bitstamp_exporter'].get('api_secret'):
            settings['bitstamp_exporter']['api_secret'] = cfg['bitstamp_exporter']['api_secret']
        if cfg['bitstamp_exporter'].get('export') in ['text', 'http']:
            settings['bitstamp_exporter']['export'] = cfg['bitstamp_exporter']['export']
        if cfg['bitstamp_exporter'].get('listen_port'):
            settings['bitstamp_exporter']['listen_port'] = cfg['bitstamp_exporter']['listen_port']


class BitstampCollector:
    rates = {}
    accounts = {}
    hasApiCredentials = False
    markets = None

    def __init__(self):
        self.bitstamp = ccxt.bitstamp({'nonce': ccxt.bitstamp.milliseconds})
        if (settings['bitstamp_exporter'].get('api_key') and (settings['bitstamp_exporter'].get('api_secret'))):
            self.bitstamp.apiKey = settings['bitstamp_exporter'].get('api_key')
            self.bitstamp.secret = settings['bitstamp_exporter'].get('api_secret')
            self.hasApiCredentials = True

    def _getTickers(self):
        """
        Gets the price ticker.
        """
        log.debug('Loading Markets')
        self.bitstamp.loadMarkets(True)

        if self.bitstamp.has['fetchTickers']:
            log.debug('Loading Tickers')
            tickers = self.bitstamp.fetch_tickers()
        elif self.bitstamp.has['fetchCurrencies']:
            tickers = {}
            for symbol in self.bitstamp.symbols:
                log.debug('Loading Symbol {}'.format(symbol))
                try:
                    tickers.update({
                        symbol: {
                            'last': self.bitstamp.fetch_ticker(symbol)['last']
                        }
                    })
                except (ccxt.ExchangeNotAvailable) as e:
                    log.warning('{}'.format(e))
                time.sleep(1)  # don't hit the rate limit
        else:
            tickers = {}
            if not self.markets:
                log.debug('Fetching markets')
                self.markets = self.bitstamp.fetch_markets()
            for market in self.markets:
                symbol = market.get('symbol')
                log.debug('Loading Symbol {}'.format(symbol))
                try:
                    tickers.update({
                        symbol: {
                            'last': self.bitstamp.fetch_ticker(symbol)['last']
                        }
                    })
                except (ccxt.ExchangeNotAvailable) as e:
                    log.warning('{}'.format(e))
                time.sleep(1)  # don't hit the rate limit

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
            accounts = self.bitstamp.fetch_balance()
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
                    'bitstamp'
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
                            'bitstamp'
                        ]
                    )

        for m in metrics.values():
            yield m


def _collect_to_text():
    e = BitstampCollector()
    while True:
        write_to_textfile('{0}/bitstamp_exporter.prom'.format(settings['bitstamp_exporter']['prom_folder']), e)
        time.sleep(int(settings['bitstamp_exporter']['interval']))


def _collect_to_http():
    REGISTRY.register(BitstampCollector())
    start_http_server(int(settings['bitstamp_exporter']['listen_port']))
    while True:
        time.sleep(int(settings['bitstamp_exporter']['interval']))


if __name__ == '__main__':
    _settings()
    log.debug('Loaded settings: {}'.format(settings))
    if settings['bitstamp_exporter']['export'] == 'text':
        _collect_to_text()
    if settings['bitstamp_exporter']['export'] == 'http':
        _collect_to_http()
