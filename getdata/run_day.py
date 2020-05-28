import random
import datetime
import requests
import math
from multiprocessing import Pool
from statistics import quantiles
from pprint import pprint as pp

from .globals import bitcoin
from .dijkstra import Graph
from .helpers import get_txo_amount, BTC


def run_day(db):
    # discover the day we're in and which blocks we must scan
    db.execute("SELECT max(day) FROM days")
    (last_day,) = db.fetchone()
    if not last_day:
        last_day = datetime.date.today() - datetime.timedelta(days=2)
    current_day = last_day + datetime.timedelta(days=1)
    blocks_to_rewind = (datetime.date.today() - current_day).days * 200 + 144
    tip = bitcoin.getblockchaininfo()["headers"]
    scan_since = tip - blocks_to_rewind

    print(
        f"today: {datetime.date.today()}, tip: {tip}, last day: {last_day}, getting data for day: {current_day}, scanning since: {scan_since}"
    )

    # get a list of nodes
    r = requests.get(
        "https://ln.bigsun.xyz/api/nodes?select=pubkey&order=openchannels.desc",
        headers={"Range": "250-1250"},
    )
    global nodes
    nodes = [item["pubkey"] for item in r.json()]

    # load the channel graph
    global graph
    graph = Graph.load()

    # get a generic function to estimate fee
    global estimate_lightning_fee
    estimate_lightning_fee = get_fee_estimator()

    for i in range(1, 8):
        sat = 4 * 10 ** i
        print(
            "estimate:",
            sat,
            estimate_lightning_fee(sat),
            f"{int(100 * estimate_lightning_fee(sat) / sat)}%",
        )

    # get the list of blocks we're interested in
    blocks_for_the_day = []
    for block_number in range(scan_since, tip):
        block_hash = bitcoin.getblockhash(block_number)
        block = bitcoin.getblock(block_hash)
        block_date = datetime.datetime.fromtimestamp(block["time"]).date()
        if block_date < current_day:
            continue
        if block_date > current_day:
            break

        # here we know we're in the correct day
        blocks_for_the_day.append(block_hash)

    total_payments = []
    overpaid_payments = []

    print(
        f"found {len(blocks_for_the_day)} blocks from {blocks_for_the_day[0]} to {blocks_for_the_day[-1]}"
    )
    with Pool(processes=12) as pool:
        results = pool.imap_unordered(run_block, blocks_for_the_day)

        for total, overpaid in results:
            total_payments += total
            overpaid_payments += overpaid

    # reached the end, calculate values for the day
    pp(
        (
            current_day,
            len(total_payments),
            sum(total_payments),
            len(overpaid_payments),
            sum([p[0] for p in overpaid_payments]),
            sum([p[1] for p in overpaid_payments]),
            sum([p[2] for p in overpaid_payments]),
            quantiles([p[0] for p in overpaid_payments], n=10),
            quantiles([p[1] for p in overpaid_payments], n=10),
            quantiles([p[2] for p in overpaid_payments], n=10),
            quantiles([p[1] - p[2] for p in overpaid_payments], n=10),
        )
    )

    db.execute(
        """
      INSERT INTO days
        (day,
         total_n, total_amount, overpaid_n, overpaid_amount,
         overpaid_chain_fee, overpaid_ln_fee,
         overpaid_quant_amount, overpaid_quant_chain_fee, overpaid_quant_ln_fee, overpaid_quant_diff
        )
      VALUES (
        %s,
        %s, %s, %s, %s,
        %s, %s,
        %s, %s, %s, %s
      )
    """,
        (
            current_day,
            len(total_payments),
            sum(total_payments),
            len(overpaid_payments),
            sum([p[0] for p in overpaid_payments]),
            sum([p[1] for p in overpaid_payments]),
            sum([p[2] for p in overpaid_payments]),
            quantiles([p[0] for p in overpaid_payments], n=10),
            quantiles([p[1] for p in overpaid_payments], n=10),
            quantiles([p[2] for p in overpaid_payments], n=10),
            quantiles([p[1] - p[2] for p in overpaid_payments], n=10),
        ),
    )


def run_block(block_hash):
    total_payments = []
    overpaid_payments = []

    block_data = bitcoin.getblock(block_hash, 2)
    print("starting block", block_data["height"])

    txs = block_data["tx"][1:]  # exclude coinbase
    for tx in txs:
        # exclude bizarre transactions, coinjoin and so on
        if len(tx["vout"]) > 50:
            continue

        # get the total transaction fee
        inputsum = sum([get_txo_amount(vin["txid"], vin["vout"]) for vin in tx["vin"]])
        outputsum = sum([int(vout["value"] * BTC) for vout in tx["vout"]])
        total_fee = inputsum - outputsum

        # exclude transactions that don't pay anyone (?)
        if outputsum == 0:
            continue

        vouts = []
        for vout in tx["vout"]:
            sat = int(vout["value"] * BTC)

            # exclude zero or very small outputs
            if sat < 100:
                continue

            # exclude very obvious change outputs
            if len(tx["vout"]) > 1 and outputsum > 100000 and (sat / outputsum) > 0.90:
                continue

            vouts.append(vout)

        if len(vouts) == 0:
            continue

        # the fee for each payment is the tx fee divided by the number of payments
        chain_fee = int(total_fee / len(vouts))

        # each vout is treated as a different payment, total fee is splitted
        for vout in vouts:
            sat = int(vout["value"] * BTC)

            total_payments.append(sat)
            ln_fee = estimate_lightning_fee(sat)

            print(
                block_data["height"],
                f"{tx['txid']}:{vout['n']}",
                sat,
                chain_fee,
                ln_fee,
            )

            if ln_fee and ln_fee < chain_fee:
                overpaid_payments.append((sat, chain_fee, ln_fee))

    return total_payments, overpaid_payments


def get_fee_estimator():
    # estimate multiple fees considering large payments, take the greatest of them
    # segregate absolute and relative fee
    # to build a function we can reuse with any quantity

    estimator_limits = [4 * 10 ** i for i in range(1, 8)]
    fee_params = []

    for limit in estimator_limits:
        absolute_fees = []
        relative_fees = []

        for i in range(20):
            source = random.choice(nodes)
            target = random.choice(nodes)
            price, absolute_fee, relative_fee, _ = graph.dijkstra(source, target, limit)
            if price == math.inf or price == 0:
                # no route found
                continue

            absolute_fees.append(absolute_fee)
            relative_fees.append(relative_fee)

        fee_params.append((max(absolute_fees), max(relative_fees) / limit))

    for limit, (absolute_fee, relative_fee) in zip(estimator_limits, fee_params):
        print(f"estimate(<= {limit}): {absolute_fee} + {relative_fee} * sat")

    def estimate(sat):
        for limit, (absolute_fee, relative_fee) in zip(estimator_limits, fee_params):
            if sat <= limit:
                return absolute_fee + relative_fee * sat
        else:
            return None

    return estimate
