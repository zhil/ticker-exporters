# ticker-exporters

Allows exporting ticker and account data, for gathering with [Prometheus](https://prometheus.io).

Merge/Pull requests are welcomed, I reserve however the right to accept/deny them.

## Supported:
> Note! Some exporters require API credentials.

Make sure that the API keys you configure are **read only** keys!

### Account Balance Only:
*   [etherscan / ETH](https://etherscan.io) - API credentials required
*   [Ripple / XRP](https://xrpcharts.ripple.com/)

### Ticker Data Only:
*   [GDAX](https://www.gdax.com)
*   [Kraken](https://www.kraken.com)

### Both Account Balance and Ticker Data
*   [BitFinex](https://www.bitfinex.com) - API credentials required for account balance
*   [Quoine](https://www.quoine.com) (with the two brands [Quoinex](https://trade.quoinex.com) and [Qryptos](https://trade.qryptos.com)) - API credentials required for account balance
*   [Poloniex](https://poloniex.com) - API credentials required for account balance

## Requirements
*   python3 (I use 3.5.2 on Ubuntu 16.04)
*   pip3 (I use 8.1.1, since it was installed with `apt`)
*   every exporter has a `*_requirements.txt` file. Install the modules with `pip3 install -r file__requirements.txt`

## Configuration
All the exporters try to load the configuration file located in `/etc/*_exporter/*.exporter.yaml`. For example, the
`bitfinex_exporter` will look for `/etc/bitfinex_exporter/bitfinex_exporter.yaml`

### Configuration File Structure
```yaml
type_exporter:
  option1: value
  option2: value
  option3:
    - list item 1
    - list item 2
```

### Common Options
The following options are supported by all exporters:
```yaml
  prom_folder: /var/lib/node_exporter
  interval: 60
  export: text
  listen_port: 9302
  url: https://api_url_comes_here
```

*   `prom_folder` (string) - for write_to_textfile - the folder on the HDD where the node_exporter looks for the .prom files
*   `interval` (integer / string) - the data gathering interval in seconds
*   `export` (string) - switch for `text`/`html` - use `node_exporter` to collect the metrics or open a port for http connection from prometheus
*   `listen_port` (integer / string) - the TCP port to open, if `export` has been set to `text`
*   `url` (string) - allows for override of the default API URL

### Additional Options Specific for Each Exporter
#### `bitfinex_exporter` + `poloniex_exporter` + `quoine_exporter`
*   `api_key` (string) - the API key from the exchange
*   `api_secret` (string) - the API secret from the exchange

#### `etherscan_exporter`
*   `api_key` (string) - the etherscan API key
*   `addresses` (list of strings) - the list of ETH addresses for which to collect the balance
*   `tokens` (list of dictionaries) - the list of *contract addresses*. The exporter will check for every address listed above if any of the contract addresses listed here has a token balance

Example for the OmiseGO token:
```yaml
etherscan_exporter:
  addresses:
    - 0x90833394db1b53f08b9d97dab8beff69fcf3ba49
  tokens:
    - contract: '0xd26114cd6EE289AccF82350c8d8487fedB8A0C07'
      name: 'OmiseGO'
      short: 'OMG'
      decimals: 18
    - contract: '0xab95e915c123fded5bdfb6325e35ef5515f1ea69'
      name: 'XENON'
      short: 'XNN'
      decimals: 18
```

#### `kraken_exporter`
*   `timeout` (integer / string) - timeout in seconds for the requests to the API

#### `ripple_exporter`
*   `addresses` (list of strings) - the list of ETH addresses for which to collect the balance

## `systemd` Unit File Example
```
[Unit]
Description=Prometheus Bitfinex Exporter

[Service]
ExecStart=/usr/local/sbin/bitfinex_exporter.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

## Donations
*   ETH: 0x90833394db1b53f08b9d97dab8beff69fcf3ba49
