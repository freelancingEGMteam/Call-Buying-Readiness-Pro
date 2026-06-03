# GoldSweepEA — XAUUSD Intraday Sweep + MSS Reversal (MT5)

An MetaTrader 5 Expert Advisor that autotrades **spot gold (XAUUSD)** during the
London–New York overlap, using the institutional "liquidity sweep then reversal"
model.

> ⚠️ **Not financial advice. Trade on a DEMO account first.** Spot gold has no
> centralized traded volume, so the "volume" filter uses **tick volume** (number
> of price changes) as a proxy. Backtest in the Strategy Tester and forward-test
> on demo before risking real money.

---

## The setup it trades

1. **Asia** session prints a clear high and low (default 20:00–00:00 ET).
2. **London** *respects* that level — it fails to continue past the Asia high/low
   (the "London fails to continue higher" condition).
3. **New York morning** (08:00–10:30 ET) **sweeps** the Asia high (or low) by a
   small buffer — a liquidity raid / stop hunt.
4. Price then **shifts market structure (MSS)** back the other way (a close beyond
   the protected swing point).
5. The EA enters the reversal **on a tick-volume spike**:
   - Sweep of **Asia high** → **SELL**
   - Sweep of **Asia low** → **BUY**
6. **10-minute time-stop**: if the trade isn't in profit after 10 minutes, it's
   closed. Once floating profit reaches **$10** the stop jumps to **breakeven**,
   and a **trailing stop** rides the rest of the move.
7. **PDH / PDL** (previous **D1** high/low) are used as **take-profit targets** —
   these are separate from the Asia range, which is only the entry trigger.

### Risk rules baked in
- **Hard cap: never risk more than `$50` per trade** (`InpMaxRiskMoney`). If even
  the minimum lot would risk more, the trade is skipped.
- **Only one position open at a time.**
- Daily trade cap, spread filter, broker stop-level handling.

---

## Install

1. Copy `GoldSweepEA.mq5` into your terminal's `MQL5/Experts/` folder
   (MetaTrader 5 → **File → Open Data Folder → MQL5 → Experts**).
2. Open it in **MetaEditor** and press **Compile** (F7). There should be no errors.
3. In MT5, open a **XAUUSD M5** chart and drag the EA onto it.
4. Enable **Algo Trading** (the toolbar button) and allow live trading in the
   EA dialog.

> The EA trades whatever symbol the chart uses (`_Symbol`), so attach it to your
> broker's gold symbol — `XAUUSD`, `GOLD`, `XAUUSD.m`, etc.

---

## ⏰ Most important setting: the ET time offset

All session times are in **New York / ET**. Brokers run on their own server time
(often GMT+2/+3). On attach, the EA prints a line to the **Experts** log like:

```
Server time=2026.06.03 15:00  ->  ET=2026.06.03 08:00 (offset -7 h). VERIFY ...
```

Adjust **`InpServerToETOffset`** until the printed ET matches actual New York time.
- Typical value for a **GMT+3** broker in **US summer (EDT)** is **-7**.
- In **US winter (EST)** it's usually one hour different. **There is no automatic
  DST handling — set this manually** and re-check when clocks change.

---

## Key inputs

| Input | Meaning |
|---|---|
| `InpServerToETOffset` | Hours to add to server time to get ET (**calibrate this!**) |
| `InpDayResetHourET` | Internal session reset hour (default 17:00 ET / CME close) |
| `InpAsia* / InpLondon* / InpNY*` | Session window hours (ET) |
| `InpSweepBufferPoints` | How far past the Asia level counts as a sweep |
| `InpLondonBreakBuffer` | London tolerance before the setup is voided |
| `InpEnableShorts / InpEnableLongs` | Trade direction(s) |
| `InpUseVolumeFilter / InpVolMultiplier` | Tick-volume spike requirement on the MSS bar |
| `InpLotMode` | `LOT_FIXED` or `LOT_RISK_PCT` |
| `InpRiskPercent` | Risk % of balance per trade (risk mode) |
| `InpMaxRiskMoney` | **Hard $ risk cap per trade (default 50)** |
| `InpTPMode` | `TP_PDH_PDL` (target prev-day levels) or `TP_FIXED_RR` |
| `InpTimeStopMinutes` | Close-if-not-profitable timer (default 10) |
| `InpBreakevenMoney` | Move SL to breakeven once floating profit hits this $ (default 10) |
| `InpBreakevenBufferPoints` | Points locked beyond entry at breakeven (covers spread) |
| `InpUseTrailing` + trail points | Trailing-stop behaviour (continues after breakeven) |
| `InpMaxTradesPerDay`, `InpMaxSpreadPoints` | Guards |

> **Points note:** values are in broker *points*. On a 2-digit gold feed,
> 100 points = $1.00 of price. If your broker quotes gold with 3 digits, scale
> the point-based inputs up by 10.

---

## Tuning checklist
- Calibrate `InpServerToETOffset` first (see above).
- Verify your broker's gold **digits** and adjust point-based inputs.
- Run the **Strategy Tester** (M5, "Every tick based on real ticks", with realistic
  spread) across several months before going live.
- Start on **demo**, smallest size, and confirm entries fire in the NY window.
