# Decisions

A log of the decisions behind this package. Each entry records the context, the rule, the
evidence, the alternatives that were tested and the known limits. Where alternatives were
tested, the pass criteria were written down before the test and not changed afterwards.
Rejected rules stay in this file with the evidence against them.

## Context: why a pinned price is a problem

A pending cash takeover offer pins a stock's price to the offer. Daily moves shrink to a
fraction of their usual size, and the announcement premium stays in any trailing one-year
window. Measured on its own price history, such a stock looks unusually calm and unusually
profitable. What it actually offers is a deal spread: small, steady gains with a rare large
loss if the deal fails.

Index providers keep a target in the index until the deal closes, which can take more than a
year. Index membership therefore does not remove it from a universe.

## D1 — Detect pending takeovers from SEC filings (rejected 2 Nov 2026)

### Proposal

Read each company's SEC filing history point in time and flag it from the day a signed takeover
agreement or a formal tender offer for it is public until the deal completes or is terminated.
Tell target and acquirer apart only by one-sided evidence (tender-offer headers, registration of
new shares, merger proxy). Send unspecific or contradictory evidence to a person.

### Evidence

A run on 324 US stocks on 2 Nov 2026 produced 36 flags:

| Flag | Count | Finding |
|---|---|---|
| DEFA14A in the last 30 days | 8 | proxy season, unrelated to deals |
| 8-K item 1.01 in the last 30 days | 13 | material agreements, mostly credit and note agreements |
| Only 425, role open | 10 | mostly acquirers and spin-offs, for example an exchange offer |
| Classified as target | 5 | 2 plausible (one cash deal, one cash-and-stock deal), 2 false (an issuer tender and a reorganisation proxy, both from 2024), 1 only by manual decision |

### Why it was rejected

- **Noise.** 31 of 36 flags needed a person, and of 5 stocks classified as targets 2 were wrong.
- **Wrong side.** In a fixed-ratio stock deal announced on 2 Nov 2026 the acquirer named itself as
  subject company of its 425 filing and was first classified as the target.
- **Late.** A cash deal announced on 5 Oct 2026 had no merger proxy four weeks later and was not
  flagged. Filings follow the press release by days to weeks.
- **No end.** A filing says that a deal exists, not whether it still determines the price.
  Competing bids, a falling acquirer share, a deal at risk: the stock moves again, but the rule
  would keep flagging it until completion.
- **Not reproducible.** The rule depends on judgement (which offer is binding enough, which role is
  meant) that cannot be made in a historical study. Every manual review would need a fixed default,
  and that default would be the actual rule.

The filing reader is not part of this package.

## D2 — Flag price pinning from the price series alone (adopted 2 Nov 2026)

### Rule

1. For a day t, using closes **before** t:
   `ratio = median(|r|, last 20 daily returns) / median(|r|, last 252 daily returns)`.
2. If `ratio <= 0.30`, the stock is flagged as pinned on t. No confirmation over several days.
3. The flag clears as soon as the ratio is above 0.30 again. Nobody decides.
4. With fewer than 253 closes the measure does not apply.

`pricepinning.check` implements these steps. `pricepinning.pinning_frame` returns the daily
series behind them.

### Why the median

An announcement jump inflates a standard deviation for as long as it stays in the window. The
median of absolute returns ignores a single jump, so the short window shows the quiet days that
follow it after about half its length.

### Calibration

Data: 324 US large caps, daily closes, evaluated from 1 Jan 2025 to 30 Oct 2026. Genuine cases:
two cash takeovers announced on 25 Jun 2026 (stock A) and 5 Oct 2026 (stock B). Both deals were
pending at the time of writing, so the stocks are not named.

| | Ratio |
|---|---|
| Stock A after the announcement, median | 0.12 |
| Stock B on 30 Oct 2026 | 0.18 |
| Rest of the universe, 0.1 % quantile of all stock-days | 0.38 |
| Rest of the universe, 1 % quantile | 0.50 |

Threshold choice (20/252 days):

| Threshold | First day flagged, stock A | First day flagged, stock B | Other stocks ever flagged | Share of stock-days |
|---|---|---|---|---|
| 0.30 | +9 trading days | +14 trading days | 10 | 0.017 % |
| 0.35 | +9 trading days | +10 trading days | 20 | 0.041 % |

The threshold sits in a wide gap between the two groups. 0.30 halves the false signals at the
cost of four days for stock B.

A cash-and-stock deal announced in July 2025 never came near the threshold (0.52 at its lowest
after the announcement, 1.10 on 30 Oct 2026). Its price still moves with the acquirer's share, so
its measured risk is real. The same is expected for a pure stock deal.

### Check on a wider database

The same measure on 3,958 price series with at least one year of history, several markets,
2000 to 30 Oct 2026:

- 34 clear cases (a jump of more than 10 %, then at least 10 days below the threshold), 15 of
  them in series that have since ended. The measure flagged them 11 trading days after the jump
  (median; 9 to 17 for the middle half).
- Several ended series stop almost exactly at a public cash offer price, for example 209.70
  against an offer of 210 (Electronic Arts) and 209.90 against 210 (Chart Industries).
- False signals are more frequent there than among large caps (about 0.1 % of stock-days in
  2025) and peak after crises (0.8 % in 2009, 0.5 % in 2010): calm measured against an inflated
  crisis year.

### Long deals

The measure loses its reference after about 126 trading days of pinning. By then more than half
of the one-year window consists of quiet days, the one-year median falls with it, and the ratio
moves back towards 1. Electronic Arts (cash offer announced September 2025, completed August
2026) ended at a ratio of 0.70 and was not flagged on any of its last 60 trading days. Chart
Industries (July 2025 to July 2026) ended at 1.18.

Four fixes were tested against criteria set before the run:

- the five long cases (Electronic Arts, Chart Industries, DigitalBridge, NXP Semiconductors and
  one cash deal still pending at the time of writing) stay flagged until completion;
- no flag on a stock without a known deal lasts longer than 63 trading days;
- flagged stock-days rise by at most half compared with the measure above;
- an absolute level, if any, gives the same result between 0.45 % and 0.55 %.

None passed (see rejected alternatives). **Decision:** the rule stays unchanged and the gap is documented as a known limit.

### Rejected alternatives

- **Event detection from SEC filings.** See D1.
- **Short window of 10 days.** Reacts faster in principle, but the noise floor drops: 66 other
  stocks fell below 0.25 at least once (3 with 20 days), and the cash-and-stock target above
  would have been flagged on 6 consecutive days in July 2025.
- **Confirmation over 5 days in a row.** False signals are rare and short already. The
  confirmation would mainly delay the genuine cases by another week.
- **Price-range condition** (max/min of the last 21 closes). Removes signals after a crash
  rebound, but misses a fresh target as long as the announcement jump is inside the range window.
- **Standard deviation instead of median.** Stays high for weeks after the jump.
- **Hold with a frozen reference.** Once the ratio falls below 0.30, keep that day's one-year
  median and clear the flag only when the 20-day median exceeds half of it. Closes the long-deal
  gap (Electronic Arts, Chart Industries, DigitalBridge flagged until completion; NXP's 2016 cash
  offer cleared when it was raised in 2018), but after crises it flags stocks without any deal
  for months, because the frozen reference is a crisis year: up to 546 trading days in the wide
  database, and 13 large caps for 43 to 103 trading days in 2009. Flagged stock-days rise
  2.6-fold.
- **Frozen three-year reference.** Fails both ways: Electronic Arts is cleared after 96 trading
  days, and a turbulent past inflates the reference as well (64 flags longer than 63 days, one of
  817).
- **Frozen reference plus an absolute level** (clear when the 20-day median of absolute returns
  exceeds 0.50 %). Closest to the target, but it failed three of the four criteria: flagged
  stock-days +59 %, NXP flagged for 48 instead of 313 days between 0.45 % and 0.50 %, single
  flags without a known deal of 65 to 72 days. The level is fitted to this database and depends
  on a stock's normal volatility.
- **Manual release after a fixed number of days.** Cannot be reproduced in a historical study,
  so the flags after crises remain there.

### Known limits

- **Lag.** 9 to 14 trading days between the announcement and the first flag (median 11 in the
  wider database).
- **Long deals.** A stock pinned for more than about 126 trading days is no longer flagged (see
  above). Accepted as the smaller error: it affects few stocks, while every tested fix flagged
  stocks without a deal after crises. How often this matters depends on what the flag is used
  for, and it should be measured on data that includes delisted stocks.
- **Low volatility.** A pinned target looks like an ideal low-volatility stock. Uses that rank on
  volatility are the most exposed to the lag and the long-deal gap.
- **Two genuine cases in the calibration.** The universe contains current members only, so
  earlier targets that have already left it are missing. The calibration measures false signals
  well and detection on two cases only; the wider database adds 34.
- **False signals** come in three forms: calm after a market-wide volatility spike (April 2025
  inflated the one-year median), holiday weeks, and quiet phases of a sector. They are short and
  affect about 0.02 % of large-cap stock-days.
- **Competing bids** keep the price moving, so the stock is not flagged. Intended: the price
  still carries information.
- **Unadjusted closes** show dividend drops as small negative returns. The median is insensitive
  to them.
