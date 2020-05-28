CREATE TABLE days (
  day date PRIMARY KEY,
  total_n int NOT NULL, -- total payments considered (excluding change)
  total_amount numeric(15) NOT NULL,
  overpaid_n int NOT NULL, -- payments that could have been cheaper on lightning
  overpaid_amount numeric(15) NOT NULL,
  overpaid_chain_fee numeric(12) NOT NULL,
  overpaid_ln_fee numeric(12, 3) NOT NULL,
  overpaid_quant_amount numeric(15)[] NOT NULL,
  overpaid_quant_chain_fee numeric(12)[] NOT NULL,
  overpaid_quant_ln_fee numeric(12, 3)[] NOT NULL,
  overpaid_quant_diff numeric(15, 3)[] NOT NULL
);
GRANT SELECT ON days TO web_anon;
