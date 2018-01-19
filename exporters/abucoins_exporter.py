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
        'abucoins_exporter': {
            'prom_folder': '/var/lib/node_exporter',
            'interval': 60,
            'api_key': False,
            'api_secret': False,
            'api_passphrase': False,
            'export': 'text',
            'listen_port': 9299,
            'url': 'https://api.abucoins.com',
        },
    }
    config_file = '/etc/abucoins_exporter/abucoins_exporter.yaml'
    cfg = {}
    if os.path.isfile(config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
    if cfg.get('abucoins_exporter'):
        if cfg['abucoins_exporter'].get('prom_folder'):
            settings['abucoins_exporter']['prom_folder'] = cfg['abucoins_exporter']['prom_folder']
        if cfg['abucoins_exporter'].get('interval'):
            settings['abucoins_exporter']['interval'] = cfg['abucoins_exporter']['interval']
        if cfg['abucoins_exporter'].get('api_key'):
            settings['abucoins_exporter']['api_key'] = cfg['abucoins_exporter']['api_key']
        if cfg['abucoins_exporter'].get('api_secret'):
            settings['abucoins_exporter']['api_secret'] = cfg['abucoins_exporter']['api_secret']
        if cfg['abucoins_exporter'].get('api_passphrase'):
            settings['abucoins_exporter']['api_passphrase'] = cfg['abucoins_exporter']['api_passphrase']
        if cfg['abucoins_exporter'].get('url'):
            settings['abucoins_exporter']['url'] = cfg['abucoins_exporter']['url']
        if cfg['abucoins_exporter'].get('export') in ['text', 'http']:
            settings['abucoins_exporter']['export'] = cfg['abucoins_exporter']['export']
        if cfg['abucoins_exporter'].get('listen_port'):
            settings['abucoins_exporter']['listen_port'] = cfg['abucoins_exporter']['listen_port']


class AbuCoins(requests.auth.AuthBase):
    def __init__(self, api_key, secret_key, passphrase):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase

    def __call__(self, request):
        timestamp = str(int(time.time()))  # eg. 1512516837
        # timestamp = eg. 1512516837
        # request.method = eg. POST
        # request.path_url = eg. /orders
        message = timestamp + request.method + request.path_url
        if request.body:  # if present
            message = message + request.body.decode()  # decode raw bytes

        hmac_key = base64.b64decode(self.secret_key)
        signature = hmac.new(hmac_key, message.encode('utf-8'), hashlib.sha256)
        signature_base64 = base64.b64encode(signature.digest())

        request.headers.update({
            'AC-ACCESS-KEY': self.api_key,
            'AC-ACCESS-PASSPHRASE': self.passphrase,
            'AC-ACCESS-SIGN': signature_base64,
            'AC-ACCESS-TIMESTAMP': timestamp,
            })
        return request


class AbucoinsCollector:
    symbols = []
    rates = {}

    def __init__(self):
        self.authenticator = AbuCoins(
            api_key=settings['abucoins_exporter']['api_key'],
            secret_key=settings['abucoins_exporter']['api_secret'],
            passphrase=settings['abucoins_exporter']['api_passphrase']
        )
        self._getSymbols()

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

    def _getSymbols(self):
        """
        Gets the list of traded symbols
        """
        path = '/products'

        try:
            r = requests.get(settings['abucoins_exporter']['url'] + path, verify=True)  # Doesn't need authentication
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ReadTimeout,
            requests.packages.urllib3.exceptions.ReadTimeoutError
        ) as e:
            log.warning(e)
            r = False
        if r and r.status_code == 200:
            for symbol in r.json():
                self.symbols.append(symbol['id'])

        log.debug('Found the following symbols: {}'.format(self.symbols))

    def _getExchangeRates(self):
        for symbol in self.symbols:
            path = "/products/{symbol}/ticker".format(symbol=symbol)
            try:
                r = requests.get(settings['abucoins_exporter']['url'] + path, verify=True)
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout,
                requests.packages.urllib3.exceptions.ReadTimeoutError
            ) as e:
                log.warning(e)
                r = False
            if r and r.status_code == 200:
                ticker = r.json()
                currencies = symbol.split('-')
                self.rates.update({
                    symbol: {
                        'source_currency': self._translate(currencies[0]),
                        'target_currency': self._translate(currencies[1]),
                        'value': float(ticker['price']),
                    }
                })
        log.debug('Found the following ticker rates: {}'.format(self.rates))

    def collect(self):
        metrics = {
            'exchange_rate': GaugeMetricFamily(
                'exchange_rate',
                'Current exchange rates',
                labels=['source_currency', 'target_currency', 'exchange']
            ),
        }
        self._getExchangeRates()
        for rate in self.rates:
            metrics['exchange_rate'].add_metric(
                value=self.rates[rate]['value'],
                labels=[
                    self.rates[rate]['source_currency'],
                    self.rates[rate]['target_currency'],
                    'abucoins'
                ]
            )

        for m in metrics.values():
            yield m


def _collect_to_text():
    while True:
        e = AbucoinsCollector()
        write_to_textfile('{0}/abucoins_exporter.prom'.format(settings['abucoins_exporter']['prom_folder']), e)
        time.sleep(int(settings['abucoins_exporter']['interval']))


def _collect_to_http():
    REGISTRY.register(AbucoinsCollector())
    start_http_server(int(settings['abucoins_exporter']['listen_port']))
    while True:
        time.sleep(int(settings['abucoins_exporter']['interval']))


if __name__ == '__main__':
    _settings()
    log.debug('Loaded settings: {}'.format(settings))
    if settings['abucoins_exporter']['export'] == 'text':
        _collect_to_text()
    if settings['abucoins_exporter']['export'] == 'http':
        _collect_to_http()
