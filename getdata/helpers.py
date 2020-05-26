from .globals import bitcoin

BTC = 100_000_000


def get_txo_amount(txid, output_n):
    tx = bitcoin.getrawtransaction(txid, True)
    return int(tx["vout"][output_n]["value"] * BTC)
