#!/usr/bin/env python3

import logging
import time
import os
import yaml
import sys
import ccxt
from prometheus_client import write_to_textfile, start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily, CounterMetricFamily

log = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=os.environ.get("LOGLEVEL", "INFO"))

settings = {}


def _settings():
    global settings

    settings = {
        'gdax_exporter': {
            'prom_folder': '/var/lib/node_exporter',
            'interval': 60,
            'api_key': None,
            'api_secret': None,
            'export': 'text',
            'listen_port': 9302,
        },
    }
    config_file = '/etc/gdax_exporter/gdax_exporter.yaml'
    cfg = {}
    if os.path.isfile(config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
    if cfg.get('gdax_exporter'):
        if cfg['gdax_exporter'].get('prom_folder'):
            settings['gdax_exporter']['prom_folder'] = cfg['gdax_exporter']['prom_folder']
        if cfg['gdax_exporter'].get('interval'):
            settings['gdax_exporter']['interval'] = cfg['gdax_exporter']['interval']
        if cfg['gdax_exporter'].get('api_key'):
            settings['gdax_exporter']['api_key'] = cfg['gdax_exporter']['api_key']
        if cfg['gdax_exporter'].get('api_secret'):
            settings['gdax_exporter']['api_secret'] = cfg['gdax_exporter']['api_secret']
        if cfg['gdax_exporter'].get('export') in ['text', 'http']:
            settings['gdax_exporter']['export'] = cfg['gdax_exporter']['export']
        if cfg['gdax_exporter'].get('listen_port'):
            settings['gdax_exporter']['listen_port'] = cfg['gdax_exporter']['listen_port']


class GdaxCollector:
    rates = {}
    accounts = {}
    hasApiCredentials = False
    markets = None

    def __init__(self):
        self.gdax = ccxt.gdax({'nonce': ccxt.gdax.milliseconds})
        if (settings['gdax_exporter'].get('api_key') and (settings['gdax_exporter'].get('api_secret'))):
            self.gdax.apiKey = settings['gdax_exporter'].get('api_key')
            self.gdax.secret = settings['gdax_exporter'].get('api_secret')
            self.hasApiCredentials = True

    def _getTickers(self):
        """
        Gets the price ticker.
        """
        log.debug('Loading Markets')
        markets_loaded = False
        while markets_loaded is False:
            try:
                self.gdax.loadMarkets(True)
                markets_loaded = True
            except (ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as e:
                log.warning('{}'.format(e))
                time.sleep(1)

        if self.gdax.has['fetchTickers']:
            log.debug('Loading Tickers')
            tickers = self.gdax.fetch_tickers()
        elif self.gdax.has['fetchCurrencies']:
            tickers = {}
            for symbol in self.gdax.symbols:
                log.debug('Loading Symbol {}'.format(symbol))
                try:
                    tickers.update({
                        symbol: {
                            'last': self.gdax.fetch_ticker(symbol)['last']
                        }
                    })
                except (ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as e:
                    log.warning('{}'.format(e))
                time.sleep(1)  # don't hit the rate limit
        else:
            tickers = {}
            if not self.markets:
                log.debug('Fetching markets')
                self.markets = self.gdax.fetch_markets()
            for market in self.markets:
                symbol = market.get('symbol')
                log.debug('Loading Symbol {}'.format(symbol))
                try:
                    tickers.update({
                        symbol: {
                            'last': self.gdax.fetch_ticker(symbol)['last']
                        }
                    })
                except (ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as e:
                    log.warning('{}'.format(e))
                time.sleep(1)  # don't hit the rate limit

        for ticker in tickers:
            currencies = ticker.split('/')
            if len(currencies) == 2 and tickers[ticker].get('last'):
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
            accounts = {}
            try:
                accounts = self.gdax.fetch_balance()
                self.accounts = {}
            except (ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as e:
                log.warning('{}'.format(e))
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
                    'gdax'
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
                            'gdax'
                        ]
                    )

        for m in metrics.values():
            yield m


def _collect_to_text():
    e = GdaxCollector()
    while True:
        write_to_textfile('{0}/gdax_exporter.prom'.format(settings['gdax_exporter']['prom_folder']), e)
        time.sleep(int(settings['gdax_exporter']['interval']))


def _collect_to_http():
    REGISTRY.register(GdaxCollector())
    start_http_server(int(settings['gdax_exporter']['listen_port']))
    while True:
        time.sleep(int(settings['gdax_exporter']['interval']))


if __name__ == '__main__':
    _settings()
    log.debug('Loaded settings: {}'.format(settings))
    if settings['gdax_exporter']['export'] == 'text':
        _collect_to_text()
    if settings['gdax_exporter']['export'] == 'http':
        _collect_to_http()
