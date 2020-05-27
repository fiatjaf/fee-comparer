from .globals import bitcoin

BTC = 100_000_000


def get_txo_amount(txid, output_n):
    tx = bitcoin.getrawtransaction(txid, True)
    return int(tx["vout"][output_n]["value"] * BTC)


def normalize_value(value):
    return round(round(value ** (1 / 4.5)) ** 4.5)
