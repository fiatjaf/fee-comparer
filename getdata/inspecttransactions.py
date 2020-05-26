import random
import datetime
import requests
from statistics import mean, quantiles

from .globals import bitcoin, SPARK_URL, SPARK_TOKEN
from .helpers import get_txo_amount, BTC


def inspecttransactions(db):
    # get a list of nodes
    r = requests.post(
        SPARK_URL,
        headers={"X-Access": SPARK_TOKEN},
        json={"method": "listnodes"},
        verify=False,
    )
    nodes = [node["nodeid"] for node in r.json()["nodes"]]

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

    total_payments = []
    overpaid_payments = []

    # start scanning blocks until we find the date we want
    for block_number in range(scan_since, tip):
        print("block", block_number)
        block_hash = bitcoin.getblockhash(block_number)
        block = bitcoin.getblock(block_hash)
        block_date = datetime.datetime.fromtimestamp(block["time"]).date()
        if block_date < current_day:
            continue
        if block_date > current_day:
            break

        # here we know we're in the correct day
        print("  correct day")
        txs = bitcoin.getblock(block_hash, 2)["tx"][1:]  # exclude coinbase
        for tx in txs:
            # exclude bizarre transactions, coinjoin and so on
            if len(tx["vout"]) > 50:
                continue

            # get the total transaction fee
            inputsum = sum(
                [get_txo_amount(vin["txid"], vin["vout"]) for vin in tx["vin"]]
            )
            outputsum = sum([int(vout["value"] * BTC) for vout in tx["vout"]])
            total_fee = inputsum - outputsum

            # exclude transactions that don't pay anyone (?)
            if outputsum == 0:
                continue

            # exclude very obvious change outputs
            vouts = []
            for vout in tx["vout"]:
                sat = int(vout["value"] * BTC)
                if (
                    len(tx["vout"]) > 1
                    and outputsum > 100000
                    and (sat / outputsum) > 0.90
                ):
                    print("  excluding change ", sat, outputsum)
                    continue
                vouts.append(vout)

            # the fee for each payment is the tx fee divided by the number of payments
            chain_fee = total_fee / len(vouts)

            # each vout is treated as a different payment, total fee is splitted
            for vout in vouts:
                sat = int(vout["value"] * BTC)
                total_payments.append(sat)

                # estimate lightning fee by calculating random routes to 3 destinations
                ln_fees = []
                for i in range(7):
                    target = random.choice(nodes)
                    r = requests.post(
                        SPARK_URL,
                        headers={"X-Access": SPARK_TOKEN},
                        json={
                            "method": "getroute",
                            "params": [target, f"{sat}sat", 0],
                        },
                        verify=False,
                    )
                    if not r.ok:
                        continue

                    fee_msat = r.json()["route"][0]["msatoshi"] - (sat * 1000)
                    ln_fees.append(fee_msat)

                    if len(ln_fees) >= 3:
                        break

                if not ln_fees:
                    # didn't find any route, so forget about this payment
                    continue

                ln_fee = mean(ln_fees)

                print(
                    f"{tx['txid']}:{vout['n']}", sat, chain_fee, int(ln_fee / 1000),
                )

                if ln_fee / 1000 < chain_fee:
                    overpaid_payments.append((sat, chain_fee, ln_fee))

    # reached the end, calculate values for the day
    db.execute(
        """
      INSERT INTO days
        (day,
         total_n, total_amount, overpaid_n, overpaid_amount,
         overpaid_chain_fee, overpaid_ln_fee,
         overpaid_quant_amount, overpaid_quant_chain_fee, overpaid_quant_ln_fee, overpaid_quant_diff)
      VALUES (
        $1,
        $2, $3, $4, $5,
        $6, $7,
        $8, $9, $10
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
