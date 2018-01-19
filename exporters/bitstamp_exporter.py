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


def settings():
    global settings

    settings = {
        'bitstamp_exporter': {
            'prom_folder': '/var/lib/node_exporter',
            'interval': 60,
            'export': 'text',
            'listen_port': 9307,
            'url': 'https://www.bitstamp.net/api',
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
        if cfg['bitstamp_exporter'].get('url'):
            settings['bitstamp_exporter']['url'] = cfg['bitstamp_exporter']['url']
        if cfg['bitstamp_exporter'].get('export') in ['text', 'http']:
            settings['bitstamp_exporter']['export'] = cfg['bitstamp_exporter']['export']
        if cfg['bitstamp_exporter'].get('listen_port'):
            settings['bitstamp_exporter']['listen_port'] = cfg['bitstamp_exporter']['listen_port']


class BitstampCollector:
    symbols = [
        'btcusd',
        'btceur',
        'eurusd',
        'xrpusd',
        'xrpeur',
        'xrpbtc',
        'ltcusd',
        'ltceur',
        'ltcbtc',
        'ethusd',
        'etheur',
        'ethbtc',
        'bchusd',
        'bcheur',
        'bchbtc',
    ]
    rates = {}

    def _getExchangeRates(self):
        for symbol in self.symbols:
            time.sleep(1)  # We don't want to spam the API with requests
            path = "/v2/ticker/{symbol}/".format(symbol=symbol)

            try:
                r = requests.get(settings['bitstamp_exporter']['url'] + path, verify=True)
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout
            ) as e:
                log.warning("Can't connect to {}. The error received follows.".format(
                    settings['bitstamp_exporter']['url']
                ))
                log.warning(e)
                r = False

            if r and r.status_code == 200:
                try:
                    ticker = r.json()
                    self.rates.update({
                        symbol: {
                            'source_currency': symbol[:3].upper(),
                            'target_currency': symbol[-3:].upper(),
                            'value': float(ticker['last']),
                        }
                    })
                    log.debug('Got the ticker: {}'.format(ticker))
                except (json.decoder.JSONDecodeError) as e:
                    log.warning('There was a problem retrieving the data.')
                    log.warning(r.headers)
                    log.warning(r.text)
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
        self._getExchangeRates()
        for rate in self.rates:
            metrics['exchange_rate'].add_metric(
                value=self.rates[rate]['value'],
                labels=[
                    self.rates[rate]['source_currency'],
                    self.rates[rate]['target_currency'],
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
    settings()
    log.debug('Loaded settings: {}'.format(settings))
    if settings['bitstamp_exporter']['export'] == 'text':
        _collect_to_text()
    if settings['bitstamp_exporter']['export'] == 'http':
        _collect_to_http()
