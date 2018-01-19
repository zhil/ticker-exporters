#!/usr/bin/env python3

import logging
import time
import os
import yaml
import sys
import requests
import json
import base64
import hashlib
import hmac
from prometheus_client import write_to_textfile, start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily, CounterMetricFamily

log = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=os.environ.get("LOGLEVEL", "INFO"))

settings = {}


def _settings():
    global settings

    settings = {
        'bitfinex_exporter': {
            'prom_folder': '/var/lib/node_exporter',
            'interval': 60,
            'api_key': None,
            'api_secret': None,
            'export': 'text',
            'listen_port': 9300,
            'url': 'https://api.bitfinex.com',
        },
    }
    config_file = '/etc/bitfinex_exporter/bitfinex_exporter.yaml'
    cfg = {}
    if os.path.isfile(config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
    if cfg.get('bitfinex_exporter'):
        if cfg['bitfinex_exporter'].get('prom_folder'):
            settings['bitfinex_exporter']['prom_folder'] = cfg['bitfinex_exporter']['prom_folder']
        if cfg['bitfinex_exporter'].get('interval'):
            settings['bitfinex_exporter']['interval'] = cfg['bitfinex_exporter']['interval']
        if cfg['bitfinex_exporter'].get('api_key'):
            settings['bitfinex_exporter']['api_key'] = cfg['bitfinex_exporter']['api_key']
        if cfg['bitfinex_exporter'].get('api_secret'):
            settings['bitfinex_exporter']['api_secret'] = cfg['bitfinex_exporter']['api_secret']
        if cfg['bitfinex_exporter'].get('url'):
            settings['bitfinex_exporter']['url'] = cfg['bitfinex_exporter']['url']
        if cfg['bitfinex_exporter'].get('export') in ['text', 'http']:
            settings['bitfinex_exporter']['export'] = cfg['bitfinex_exporter']['export']
        if cfg['bitfinex_exporter'].get('listen_port'):
            settings['bitfinex_exporter']['listen_port'] = cfg['bitfinex_exporter']['listen_port']


class BitfinexCollector:
    symbols = []
    rates = {}
    accounts = {}

    def __init__(self):
        self._getSymbols()

    def _nonce(self):
        """
        Returns a nonce
        Used in authentication
        """
        return str(int(round(time.time() * 1000)))

    def _headers(self, path, nonce, body):
        signature = "/api" + path + nonce + body
        log.debug("Signing: {}".format(signature))
        signature = hmac.new(
            bytes(settings['bitfinex_exporter']['api_secret'], 'utf-8'),
            bytes(signature, 'utf-8'),
            hashlib.sha384
        ).hexdigest()

        return {
            "bfx-nonce": nonce,
            "bfx-apikey": settings['bitfinex_exporter']['api_key'],
            "bfx-signature": signature,
            "content-type": "application/json"
        }

    def _getSymbols(self):
        """
        Gets the list of symbols

        Unfortunately, this only works over the v1 API
        """
        self.symbols = []
        path = "/v1/symbols"
        r = requests.get(settings['bitfinex_exporter']['url'] + path, verify=True)
        if r and r.status_code == 200:
            for symbol in r.json():
                if symbol.upper() not in self.symbols:
                    self.symbols.append(symbol.upper())
        else:
            log.warning('Could not retrieve symbols. Response follows.')
            log.warning(r.headers)
            log.warning(r.json())

        log.debug('Found the following symbols: {}'.format(self.symbols))

    def _getAccountBalances(self):
        nonce = self._nonce()
        rawBody = json.dumps({})
        path = "/v2/auth/r/wallets"
        headers = self._headers(path, nonce, rawBody)

        log.debug(settings['bitfinex_exporter']['url'] + path)
        log.debug('Headers: {}'.format(headers))

        r = requests.post(settings['bitfinex_exporter']['url'] + path, headers=headers, data=rawBody, verify=True)

        if r and r.status_code == 200:
            for account in r.json():
                if isinstance(account, list):
                    self.accounts.update({
                        '{}-{}'.format(account[0], account[1]): {
                            'balance': account[2],
                            'currency': account[1],
                            'account': account[0],
                        }
                    })
                else:
                    log.warning('Invalid object in response.')
                    log.warning(account)
        else:
            log.warning('Could not retrieve data. Response follows.')
            log.warning(r.headers)
            log.warning(r.text)

    def _getExchangeRates(self):
        self._getSymbols()
        if self.symbols:
            get_symbols = []
            for symbol in self.symbols:
                get_symbols.append('t{}'.format(symbol))
            symbols_string = ','.join(get_symbols)
            path = "/v2/tickers"

            log.debug('Symbols: {}'.format(symbols_string))
            r = requests.get(
                settings['bitfinex_exporter']['url'] + path,
                params={'symbols': symbols_string},
                verify=True
            )

            if r and r.status_code == 200:
                for ticker in r.json():
                    if isinstance(ticker, list):
                        source_currency = ticker[0][1:4]
                        target_currency = ticker[0][-3:]
                        self.rates.update({
                            '{}-{}'.format(source_currency, target_currency): {
                                'source_currency': source_currency,
                                'target_currency': target_currency,
                                'value': ticker[7],
                            }
                        })
                    else:
                        log.warning('Invalid object in response for ticker.')
                        log.warning(ticker)
            else:
                log.warning('Could not retrieve ticker data. Response follows.')
                log.warning(r.headers)
                log.warning(r.text)
        log.debug('Found the following ticker rates: {}'.format(self.rates))

    def collect(self):
        metrics = {
            'exchange_rate': GaugeMetricFamily(
                'exchange_rate',
                'Current exchange rates',
                labels=['source_currency', 'target_currency', 'exchange']
            ),
        }

        if settings['bitfinex_exporter'].get('api_key'):
            metrics.update({'account_balance': GaugeMetricFamily(
                'account_balance',
                'Account Balance',
                labels=['source_currency', 'currency', 'account', 'type']
            )})
            self._getAccountBalances()
            for account in self.accounts:
                metrics['account_balance'].add_metric(
                    value=(self.accounts[account]['balance']),
                    labels=[
                        self.accounts[account]['currency'],
                        self.accounts[account]['currency'],
                        self.accounts[account]['account'],
                        'bitfinex'
                    ]
                )

        self._getExchangeRates()
        for rate in self.rates:
            metrics['exchange_rate'].add_metric(
                value=self.rates[rate]['value'],
                labels=[
                    self.rates[rate]['source_currency'],
                    self.rates[rate]['target_currency'],
                    'bitfinex'
                ]
            )

        for m in metrics.values():
            yield m


def _collect_to_text():
    while True:
        e = BitfinexCollector()
        write_to_textfile('{0}/bitfinex_exporter.prom'.format(settings['bitfinex_exporter']['prom_folder']), e)
        time.sleep(int(settings['bitfinex_exporter']['interval']))


def _collect_to_http():
    REGISTRY.register(BitfinexCollector())
    start_http_server(int(settings['bitfinex_exporter']['listen_port']))
    while True:
        time.sleep(int(settings['bitfinex_exporter']['interval']))


if __name__ == '__main__':
    _settings()
    log.debug('Loaded settings: {}'.format(settings))
    if settings['bitfinex_exporter']['export'] == 'text':
        _collect_to_text()
    if settings['bitfinex_exporter']['export'] == 'http':
        _collect_to_http()
