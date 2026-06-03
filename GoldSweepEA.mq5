//+------------------------------------------------------------------+
//|                                                   GoldSweepEA.mq5 |
//|        XAUUSD intraday "Asia-sweep + MSS reversal" Expert Advisor |
//|                                                                  |
//|  Strategy (NY morning session, London-NY overlap):               |
//|    1. Asia session prints a clear high/low.                       |
//|    2. London RESPECTS that level (fails to continue past it).     |
//|    3. NY morning SWEEPS the Asia high (or low) by a small amount. |
//|    4. Price shifts market structure (MSS) back the other way.     |
//|    5. Enter the reversal on high (tick) volume.                   |
//|    6. Breakeven at +$10, then a trailing stop manages the trade.   |
//|    PDH/PDL (previous D1 high/low) are used as TP targets.         |
//|                                                                  |
//|  NOTE: Spot gold has no real traded volume - the "volume" filter  |
//|        uses TICK volume (number of price changes) as a proxy.     |
//|  TEST ON A DEMO ACCOUNT FIRST. Not financial advice.              |
//+------------------------------------------------------------------+
#property copyright "GoldSweepEA"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

//==================================================================
//  INPUTS
//==================================================================
input group "=== Time / Sessions (all hours in NEW YORK / ET) ==="
input int    InpServerToETOffset = -7;   // Hours to ADD to broker server time to get ET (check Experts log!)
input int    InpDayResetHourET   = 17;   // Internal session reset hour ET (CME close ~17:00)
input int    InpAsiaStartHour     = 20;  // Asia session start hour ET
input int    InpAsiaStartMin      = 0;
input int    InpAsiaEndHour       = 0;   // Asia session end hour ET (0 = midnight)
input int    InpAsiaEndMin        = 0;
input int    InpLondonStartHour   = 2;   // London window start hour ET
input int    InpLondonStartMin    = 0;
input int    InpLondonEndHour     = 5;   // London window end hour ET
input int    InpLondonEndMin      = 0;
input int    InpNYStartHour       = 8;   // NY trade window start hour ET
input int    InpNYStartMin        = 0;
input int    InpNYEndHour         = 10;  // NY trade window end hour ET
input int    InpNYEndMin          = 30;

input group "=== Setup detection ==="
input int    InpSweepBufferPoints   = 50;   // Sweep beyond Asia level (points) to count as a "raid"
input int    InpLondonBreakBuffer   = 30;   // London tolerance past Asia level (points) before setup is voided
input bool   InpEnableShorts        = true; // Fade Asia-HIGH sweeps (sell)
input bool   InpEnableLongs         = true; // Fade Asia-LOW sweeps (buy)

input group "=== Volume (tick) filter ==="
input bool   InpUseVolumeFilter     = true; // Require a tick-volume spike on the MSS bar
input int    InpVolLookback         = 20;   // Bars used for the average tick volume
input double InpVolMultiplier       = 1.3;  // MSS bar volume must exceed avg * this

input group "=== Risk / position sizing ==="
enum LotMode { LOT_FIXED=0, LOT_RISK_PCT=1 };
input LotMode InpLotMode            = LOT_RISK_PCT; // Lot sizing mode
input double InpFixedLot            = 0.10;  // Fixed lot (LOT_FIXED mode / fallback)
input double InpRiskPercent         = 0.5;   // Risk % of balance per trade (LOT_RISK_PCT)
input double InpMaxRiskMoney        = 50.0;  // HARD CAP: never risk more than this ($) per trade
input int    InpSLBufferPoints      = 100;   // Stop-loss padding beyond the sweep wick (points)
enum TPMode { TP_PDH_PDL=0, TP_FIXED_RR=1 };
input TPMode InpTPMode              = TP_PDH_PDL; // Take-profit target mode
input double InpRewardRatio         = 2.0;   // Reward:risk (TP_FIXED_RR / PDL fallback)
input double InpMinRewardRatio      = 1.0;   // Skip the setup if TP gives less than this reward:risk

input group "=== Trade management ==="
input double InpBreakevenMoney      = 10.0;  // Move SL to breakeven once floating profit reaches this ($)
input int    InpBreakevenBufferPoints = 10;  // Points locked beyond entry at breakeven (covers spread; 0 = exact)
input bool   InpUseTrailing         = true;  // Enable trailing stop
enum TrailMode { TRAIL_MONEY=0, TRAIL_POINTS=1 };
input TrailMode InpTrailMode        = TRAIL_MONEY; // Trailing distance mode
input double InpTrailMoneyActivate  = 10.0;  // Profit ($) before money-trailing engages (TRAIL_MONEY)
input double InpTrailMoneyDistance  = 10.0;  // Trail this many $ behind current price (TRAIL_MONEY)
input int    InpTrailActivatePoints = 150;   // Profit (points) before trailing engages (TRAIL_POINTS)
input int    InpTrailDistancePoints = 100;   // Trail distance behind price (points) (TRAIL_POINTS)
input int    InpTrailStepPoints     = 20;    // Minimum SL improvement step (points)
input bool   InpUsePartialTP        = true;  // Take partial profit at InpPartialAtRR
input double InpPartialAtRR          = 1.0;  // R-multiple at which to take the partial
input double InpPartialPercent       = 50.0; // % of the position to close at the partial

input group "=== Guards ==="
input int    InpMaxTradesPerDay     = 2;     // Max entries per session day
input int    InpMaxLossesPerDay     = 2;     // Halt trading for the day after this many losing trades
input bool   InpCloseTerminalOnMaxLoss = false; // Close MetaTrader when loss limit hit (else just warn + halt)
input double InpDailyProfitTarget   = 100.0; // Close all + halt once day P/L reaches +$ (0 = off)
input double InpMaxDailyLoss        = 100.0; // Close all + halt once day P/L reaches -$ (0 = off)
input int    InpSessionCloseHourET  = 12;    // Force-close all positions at this ET hour...
input int    InpSessionCloseMinET   = 30;    // ...and minute (e.g. 12:30 ET)
input bool   InpSkipMonday          = true;  // No trades on Monday
input bool   InpSkipFriday          = true;  // No trades on Friday
input int    InpMaxSpreadPoints     = 60;    // Skip entries if spread exceeds this (points)
input int    InpSlippagePoints      = 20;    // Max deviation on order send (points)
input long   InpMagicNumber         = 778899;// EA magic number
input string InpComment             = "GoldSweepEA";

//==================================================================
//  GLOBALS
//==================================================================
CTrade   trade;
double   g_point;
int      g_digits;
double   g_stopsLevel;   // broker minimum stop distance (price)

int      g_sessionDay = -1;

// Captured levels (price)
double   g_asiaHigh = 0.0, g_asiaLow = 0.0;
bool     g_asiaDone = false;
double   g_londonHigh = 0.0, g_londonLow = 0.0;
double   g_pdh = 0.0, g_pdl = 0.0;

// Short setup state
bool     g_shortSwept = false;       // Asia high has been raided
double   g_shortExtreme = 0.0;       // highest high since the sweep (for SL)
double   g_shortSwingLow = 0.0;      // protected low; close below = MSS down
bool     g_shortDone = false;        // setup consumed for the day

// Long setup state
bool     g_longSwept = false;
double   g_longExtreme = 0.0;        // lowest low since the sweep (for SL)
double   g_longSwingHigh = 0.0;      // protected high; close above = MSS up
bool     g_longDone = false;

int      g_tradesToday = 0;
int      g_lossesToday = 0;
bool     g_lossAlerted = false;
double   g_realizedToday = 0.0;   // realized price-based P/L this session day
bool     g_haltedToday = false;   // no more entries this session day
double   g_entryRisk = 0.0;       // initial SL distance (price) of the open trade (for R-multiples)
bool     g_partialDone = false;   // partial TP already taken on the current position
datetime g_lastBarTime = 0;

//==================================================================
//  INIT
//==================================================================
int OnInit()
{
   g_point      = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   g_digits     = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   g_stopsLevel = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * g_point;

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);

   datetime et = ToET(TimeCurrent());
   PrintFormat("GoldSweepEA started on %s. Server time=%s  ->  ET=%s (offset %+d h). "
               "VERIFY this ET value matches New York before live trading.",
               _Symbol, TimeToString(TimeCurrent(), TIME_DATE|TIME_MINUTES),
               TimeToString(et, TIME_DATE|TIME_MINUTES), InpServerToETOffset);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) {}

//------------------------------------------------------------------
//  Trade events: count losing closes, enforce the daily loss limit
//------------------------------------------------------------------
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(trans.deal == 0) return;
   if(!HistoryDealSelect(trans.deal)) return;

   if(HistoryDealGetInteger(trans.deal, DEAL_MAGIC) != InpMagicNumber) return;
   if(HistoryDealGetString(trans.deal, DEAL_SYMBOL) != _Symbol) return;

   long entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_INOUT) return; // only closes

   double profit = HistoryDealGetDouble(trans.deal, DEAL_PROFIT); // price-based P/L only
   g_realizedToday += profit;                                     // track day P/L (price-based)

   if(profit >= 0.0) return; // not a losing trade

   g_lossesToday++;
   PrintFormat("Losing trade closed (P/L %.2f). Losses today: %d/%d. Day P/L=%.2f",
               profit, g_lossesToday, InpMaxLossesPerDay, g_realizedToday);

   if(g_lossesToday >= InpMaxLossesPerDay && !g_lossAlerted)
   {
      g_lossAlerted = true;
      g_haltedToday = true;
      string msg = StringFormat("GoldSweepEA: %d losing trades today - trading HALTED for the session.",
                                g_lossesToday);
      Print(msg);
      Alert(msg);
      if(InpCloseTerminalOnMaxLoss)
      {
         Print("InpCloseTerminalOnMaxLoss=true -> closing MetaTrader.");
         TerminalClose(0);
      }
   }
}

//==================================================================
//  MAIN
//==================================================================
void OnTick()
{
   // --- session day rollover ---
   int sd = SessionDayId();
   if(sd != g_sessionDay)
   {
      ResetDay();
      g_sessionDay = sd;
   }

   // --- daily targets / session cutoff (may force-close + halt) ---
   CheckDailyStops();

   // --- manage any open position every tick ---
   ManageOpenPosition();

   // --- reset the partial-TP flag whenever we are flat ---
   if(!HasOpenPosition()) g_partialDone = false;

   // --- run the bar-driven logic only on a new M5 bar ---
   datetime bt = iTime(_Symbol, PERIOD_M5, 0);
   if(bt == g_lastBarTime) return;
   g_lastBarTime = bt;

   OnNewBar();
}

//------------------------------------------------------------------
//  Daily profit target, max daily loss, and session time cutoff.
//  Active only during the trading portion of the ET day so it never
//  trips overnight / during the next session's Asia tracking.
//------------------------------------------------------------------
void CheckDailyStops()
{
   int nowMin = ETMinutes(ToET(TimeCurrent()));
   bool activePart = (nowMin >= ToMinutes(InpNYStartHour, InpNYStartMin) &&
                      nowMin <  ToMinutes(InpDayResetHourET, 0));
   if(!activePart) return;

   double floating = HasOpenPosition() ? PositionGetDouble(POSITION_PROFIT) : 0.0;
   double dayPL    = g_realizedToday + floating;

   string reason = "";
   if(nowMin >= ToMinutes(InpSessionCloseHourET, InpSessionCloseMinET))
      reason = "session time cutoff";
   else if(InpDailyProfitTarget > 0.0 && dayPL >= InpDailyProfitTarget)
      reason = StringFormat("daily profit target hit (%.2f)", dayPL);
   else if(InpMaxDailyLoss > 0.0 && dayPL <= -InpMaxDailyLoss)
      reason = StringFormat("max daily loss hit (%.2f)", dayPL);

   if(reason == "") return;

   if(HasOpenPosition())
      trade.PositionClose(_Symbol);

   if(!g_haltedToday)
   {
      g_haltedToday = true;
      PrintFormat("Trading HALTED for the session - %s.", reason);
   }
}

//------------------------------------------------------------------
//  New closed-bar processing (uses bar index 1 = last closed bar)
//------------------------------------------------------------------
void OnNewBar()
{
   double high1  = iHigh(_Symbol, PERIOD_M5, 1);
   double low1   = iLow(_Symbol, PERIOD_M5, 1);
   double close1 = iClose(_Symbol, PERIOD_M5, 1);
   datetime t1   = iTime(_Symbol, PERIOD_M5, 1);
   datetime et1  = ToET(t1);

   // ---- accumulate Asia range ----
   if(InWindowET(et1, InpAsiaStartHour, InpAsiaStartMin, InpAsiaEndHour, InpAsiaEndMin))
   {
      if(g_asiaHigh == 0.0 || high1 > g_asiaHigh) g_asiaHigh = high1;
      if(g_asiaLow  == 0.0 || low1  < g_asiaLow ) g_asiaLow  = low1;
   }
   else if(g_asiaHigh > 0.0 && !g_asiaDone &&
           ETMinutes(et1) >= ToMinutes(InpAsiaEndHour, InpAsiaEndMin))
   {
      // Asia just finished -> lock the range
      g_asiaDone = true;
   }

   // ---- accumulate London range ----
   if(InWindowET(et1, InpLondonStartHour, InpLondonStartMin, InpLondonEndHour, InpLondonEndMin))
   {
      if(g_londonHigh == 0.0 || high1 > g_londonHigh) g_londonHigh = high1;
      if(g_londonLow  == 0.0 || low1  < g_londonLow ) g_londonLow  = low1;
   }

   // ---- NY trade window: hunt for the setup ----
   if(g_asiaDone &&
      InWindowET(et1, InpNYStartHour, InpNYStartMin, InpNYEndHour, InpNYEndMin))
   {
      // never run setup logic while a trade is open -> guarantees one position at a time
      if(InpEnableShorts && !HasOpenPosition()) ProcessShort(high1, low1, close1);
      if(InpEnableLongs  && !HasOpenPosition()) ProcessLong(high1, low1, close1);
   }
}

//------------------------------------------------------------------
//  SHORT: sweep Asia HIGH, London respected it, MSS down -> sell
//------------------------------------------------------------------
void ProcessShort(double high1, double low1, double close1)
{
   if(g_shortDone) return;

   // London-failure filter: London must NOT have run meaningfully above Asia high
   if(g_londonHigh > g_asiaHigh + InpLondonBreakBuffer * g_point) return;

   double sweepLevel = g_asiaHigh + InpSweepBufferPoints * g_point;

   if(!g_shortSwept)
   {
      if(high1 > sweepLevel)
      {
         g_shortSwept   = true;
         g_shortExtreme = high1;   // SL reference
         g_shortSwingLow= low1;    // protected low to break for MSS
      }
      return;
   }

   // already swept -> look for MSS down
   if(high1 > g_shortExtreme)
   {
      // new high: raid extends, reset the protected swing low
      g_shortExtreme  = high1;
      g_shortSwingLow = low1;
      return;
   }

   if(close1 < g_shortSwingLow)
   {
      // market-structure shift down confirmed
      if(VolumeOk())
         OpenShort();
      g_shortDone = true;   // consume the setup either way
   }
   else
   {
      g_shortSwingLow = MathMin(g_shortSwingLow, low1);
   }
}

//------------------------------------------------------------------
//  LONG: sweep Asia LOW, London respected it, MSS up -> buy
//------------------------------------------------------------------
void ProcessLong(double high1, double low1, double close1)
{
   if(g_longDone) return;

   if(g_londonLow < g_asiaLow - InpLondonBreakBuffer * g_point) return;

   double sweepLevel = g_asiaLow - InpSweepBufferPoints * g_point;

   if(!g_longSwept)
   {
      if(low1 < sweepLevel)
      {
         g_longSwept     = true;
         g_longExtreme   = low1;
         g_longSwingHigh = high1;
      }
      return;
   }

   if(low1 < g_longExtreme)
   {
      g_longExtreme   = low1;
      g_longSwingHigh = high1;
      return;
   }

   if(close1 > g_longSwingHigh)
   {
      if(VolumeOk())
         OpenLong();
      g_longDone = true;
   }
   else
   {
      g_longSwingHigh = MathMax(g_longSwingHigh, high1);
   }
}

//==================================================================
//  ORDER ENTRY
//==================================================================
void OpenShort()
{
   if(!PreTradeChecks()) return;

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl  = g_shortExtreme + InpSLBufferPoints * g_point;

   // ensure SL respects broker minimum distance
   if(sl - bid < g_stopsLevel) sl = bid + g_stopsLevel;

   double risk = sl - bid;
   if(risk <= 0) return;

   double tp = 0.0;
   if(InpTPMode == TP_PDH_PDL && g_pdl > 0.0 && g_pdl < bid - g_stopsLevel)
      tp = g_pdl;
   else
      tp = bid - InpRewardRatio * risk;
   if(bid - tp < g_stopsLevel) tp = bid - g_stopsLevel;

   // minimum reward:risk filter
   if((bid - tp) < InpMinRewardRatio * risk)
   {
      PrintFormat("Skip SHORT: reward:risk %.2f < min %.2f", (bid - tp) / risk, InpMinRewardRatio);
      return;
   }

   double lots = CalcLots(risk);
   if(lots <= 0) return;

   if(trade.Sell(lots, _Symbol, 0.0, NormalizeDouble(sl, g_digits), NormalizeDouble(tp, g_digits), InpComment))
   {
      g_tradesToday++;
      g_entryRisk   = risk;
      g_partialDone = false;
      PrintFormat("SHORT %.2f lots @%.2f SL=%.2f TP=%.2f (sweep high %.2f)",
                  lots, bid, sl, tp, g_shortExtreme);
   }
   else
      PrintFormat("SHORT order failed: retcode=%d", trade.ResultRetcode());
}

void OpenLong()
{
   if(!PreTradeChecks()) return;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double sl  = g_longExtreme - InpSLBufferPoints * g_point;

   if(ask - sl < g_stopsLevel) sl = ask - g_stopsLevel;

   double risk = ask - sl;
   if(risk <= 0) return;

   double tp = 0.0;
   if(InpTPMode == TP_PDH_PDL && g_pdh > 0.0 && g_pdh > ask + g_stopsLevel)
      tp = g_pdh;
   else
      tp = ask + InpRewardRatio * risk;
   if(tp - ask < g_stopsLevel) tp = ask + g_stopsLevel;

   // minimum reward:risk filter
   if((tp - ask) < InpMinRewardRatio * risk)
   {
      PrintFormat("Skip LONG: reward:risk %.2f < min %.2f", (tp - ask) / risk, InpMinRewardRatio);
      return;
   }

   double lots = CalcLots(risk);
   if(lots <= 0) return;

   if(trade.Buy(lots, _Symbol, 0.0, NormalizeDouble(sl, g_digits), NormalizeDouble(tp, g_digits), InpComment))
   {
      g_tradesToday++;
      g_entryRisk   = risk;
      g_partialDone = false;
      PrintFormat("LONG %.2f lots @%.2f SL=%.2f TP=%.2f (sweep low %.2f)",
                  lots, ask, sl, tp, g_longExtreme);
   }
   else
      PrintFormat("LONG order failed: retcode=%d", trade.ResultRetcode());
}

//------------------------------------------------------------------
//  Pre-trade gating: one position, daily cap, spread
//------------------------------------------------------------------
bool PreTradeChecks()
{
   if(g_haltedToday)                        return false;  // loss/profit/cutoff halt
   if(HasOpenPosition())                   return false;
   if(g_tradesToday >= InpMaxTradesPerDay)  return false;
   if(g_lossesToday >= InpMaxLossesPerDay)  return false;  // daily loss limit reached

   // weekday filter (ET trading day)
   MqlDateTime mdt;
   TimeToStruct(ToET(TimeCurrent()), mdt);
   if(InpSkipMonday && mdt.day_of_week == MONDAY) return false;
   if(InpSkipFriday && mdt.day_of_week == FRIDAY) return false;

   double spread = (SymbolInfoDouble(_Symbol, SYMBOL_ASK) -
                    SymbolInfoDouble(_Symbol, SYMBOL_BID)) / g_point;
   if(spread > InpMaxSpreadPoints)
   {
      PrintFormat("Skip entry: spread %.0f > max %d", spread, InpMaxSpreadPoints);
      return false;
   }
   return true;
}

//==================================================================
//  POSITION MANAGEMENT (partial + breakeven + trailing)
//==================================================================
void ManageOpenPosition()
{
   if(!PositionSelect(_Symbol)) return;
   if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) return;

   long   type    = PositionGetInteger(POSITION_TYPE);
   double open    = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl      = PositionGetDouble(POSITION_SL);
   double tp      = PositionGetDouble(POSITION_TP);
   double bid     = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask     = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   // ----- partial take-profit at InpPartialAtRR -----
   if(InpUsePartialTP && !g_partialDone && g_entryRisk > 0.0)
   {
      double target = (type == POSITION_TYPE_BUY)
                      ? open + InpPartialAtRR * g_entryRisk
                      : open - InpPartialAtRR * g_entryRisk;
      bool hit = (type == POSITION_TYPE_BUY) ? (bid >= target) : (ask <= target);
      if(hit)
      {
         double vol      = PositionGetDouble(POSITION_VOLUME);
         double minLot   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
         double closeVol = NormalizeLot(vol * InpPartialPercent / 100.0);
         if(closeVol >= minLot && (vol - closeVol) >= minLot)
         {
            if(trade.PositionClosePartial(_Symbol, closeVol))
               PrintFormat("Partial TP: closed %.2f of %.2f lots at %.1fR", closeVol, vol, InpPartialAtRR);
         }
         g_partialDone = true; // don't retry, even if the volume was too small to split
      }
   }

   // ----- move to breakeven once floating profit hits the $ threshold -----
   if(InpBreakevenMoney > 0.0 && PositionGetDouble(POSITION_PROFIT) >= InpBreakevenMoney)
   {
      double buf = InpBreakevenBufferPoints * g_point;
      if(type == POSITION_TYPE_BUY)
      {
         double be = open + buf;
         if((sl < be - 1e-8) && (bid - be >= g_stopsLevel))
         {
            if(trade.PositionModify(_Symbol, NormalizeDouble(be, g_digits), tp))
               sl = be;   // keep local copy in sync for the trailing block below
         }
      }
      else // SELL
      {
         double be = open - buf;
         if((sl == 0.0 || sl > be + 1e-8) && (be - ask >= g_stopsLevel))
         {
            if(trade.PositionModify(_Symbol, NormalizeDouble(be, g_digits), tp))
               sl = be;
         }
      }
   }

   // ----- trailing stop (continues from breakeven) -----
   if(!InpUseTrailing) return;

   double step = InpTrailStepPoints * g_point;

   // resolve activation + trail distance (price) from the selected mode
   bool   active = false;
   double dist   = 0.0;
   if(InpTrailMode == TRAIL_MONEY)
   {
      active = (PositionGetDouble(POSITION_PROFIT) >= InpTrailMoneyActivate);
      dist   = MoneyToPriceDistance(InpTrailMoneyDistance);
   }
   else
   {
      double profitPts = (type == POSITION_TYPE_BUY) ? (bid - open) / g_point
                                                     : (open - ask) / g_point;
      active = (profitPts >= InpTrailActivatePoints);
      dist   = InpTrailDistancePoints * g_point;
   }
   if(!active || dist <= 0.0) return;

   if(type == POSITION_TYPE_BUY)
   {
      double newSL = bid - dist;
      if(newSL > open && (sl == 0.0 || newSL - sl >= step) && bid - newSL >= g_stopsLevel)
         trade.PositionModify(_Symbol, NormalizeDouble(newSL, g_digits), tp);
   }
   else if(type == POSITION_TYPE_SELL)
   {
      double newSL = ask + dist;
      if(newSL < open && (sl == 0.0 || sl - newSL >= step) && newSL - ask >= g_stopsLevel)
         trade.PositionModify(_Symbol, NormalizeDouble(newSL, g_digits), tp);
   }
}

//------------------------------------------------------------------
//  Convert a $ amount into a price distance for the OPEN position
//  (position must already be selected by the caller)
//------------------------------------------------------------------
double MoneyToPriceDistance(double money)
{
   if(money <= 0.0) return 0.0;
   double lots      = PositionGetDouble(POSITION_VOLUME);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(lots <= 0.0 || tickValue <= 0.0 || tickSize <= 0.0) return 0.0;
   double valuePerPrice = lots * tickValue / tickSize; // $ per 1.0 of price move
   if(valuePerPrice <= 0.0) return 0.0;
   return money / valuePerPrice;
}

//==================================================================
//  HELPERS
//==================================================================
bool HasOpenPosition()
{
   if(!PositionSelect(_Symbol)) return false;
   return (PositionGetInteger(POSITION_MAGIC) == InpMagicNumber);
}

bool VolumeOk()
{
   if(!InpUseVolumeFilter) return true;
   long vols[];
   if(CopyTickVolume(_Symbol, PERIOD_M5, 1, InpVolLookback + 1, vols) <= InpVolLookback)
      return true; // not enough data -> don't block
   double sum = 0.0;
   for(int i = 1; i <= InpVolLookback; i++) sum += (double)vols[i];
   double avg = sum / InpVolLookback;
   return ((double)vols[0] >= avg * InpVolMultiplier);
}

double CalcLots(double riskPriceDistance)
{
   if(riskPriceDistance <= 0.0) return 0.0;

   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double lossPerLot = (tickValue > 0.0 && tickSize > 0.0)
                       ? (riskPriceDistance / tickSize) * tickValue
                       : 0.0;

   // ---- desired size by mode ----
   double lots = InpFixedLot;
   if(InpLotMode == LOT_RISK_PCT && lossPerLot > 0.0)
   {
      double riskMoney = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPercent / 100.0;
      lots = riskMoney / lossPerLot;
   }

   // ---- HARD $ cap (applies to every mode) ----
   if(InpMaxRiskMoney > 0.0)
   {
      if(lossPerLot <= 0.0)
      {
         // can't measure money risk on this symbol -> refuse rather than over-risk
         Print("Cannot compute per-lot risk (missing tick value/size) - trade skipped");
         return 0.0;
      }
      double maxByMoney = InpMaxRiskMoney / lossPerLot;
      if(lots > maxByMoney) lots = maxByMoney;
   }

   lots = NormalizeLot(lots);

   // ---- final verification: even the floored lot must respect the $ cap ----
   if(InpMaxRiskMoney > 0.0 && lossPerLot > 0.0 &&
      lots * lossPerLot > InpMaxRiskMoney + 1e-8)
   {
      PrintFormat("Min lot %.2f would risk $%.2f > cap $%.2f - trade skipped",
                  lots, lots * lossPerLot, InpMaxRiskMoney);
      return 0.0;
   }
   return lots;
}

double NormalizeLot(double lots)
{
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0.0) step = 0.01;
   lots = MathFloor(lots / step) * step;
   if(lots < minLot) lots = minLot;
   if(lots > maxLot) lots = maxLot;
   return NormalizeDouble(lots, 2);
}

//------------------------------------------------------------------
//  Daily reset + PDH/PDL capture
//------------------------------------------------------------------
void ResetDay()
{
   g_asiaHigh = 0.0; g_asiaLow = 0.0; g_asiaDone = false;
   g_londonHigh = 0.0; g_londonLow = 0.0;
   g_shortSwept = false; g_shortDone = false; g_shortExtreme = 0.0; g_shortSwingLow = 0.0;
   g_longSwept  = false; g_longDone  = false; g_longExtreme  = 0.0; g_longSwingHigh = 0.0;
   g_tradesToday = 0;
   g_lossesToday = 0;
   g_lossAlerted = false;
   g_realizedToday = 0.0;
   g_haltedToday = false;

   // Previous completed daily candle = PDH / PDL
   g_pdh = iHigh(_Symbol, PERIOD_D1, 1);
   g_pdl = iLow(_Symbol, PERIOD_D1, 1);

   PrintFormat("--- New session day. PDH=%.2f PDL=%.2f ---", g_pdh, g_pdl);
}

//------------------------------------------------------------------
//  Time utilities (ET = server time + offset)
//------------------------------------------------------------------
datetime ToET(datetime serverTime)
{
   return serverTime + (datetime)(InpServerToETOffset * 3600);
}

int ETMinutes(datetime et)
{
   MqlDateTime m;
   TimeToStruct(et, m);
   return m.hour * 60 + m.min;
}

int ToMinutes(int hour, int minute) { return hour * 60 + minute; }

// Session-day id, anchored to InpDayResetHourET so Asia->London->NY share one id
int SessionDayId()
{
   datetime shifted = ToET(TimeCurrent()) - (datetime)(InpDayResetHourET * 3600);
   MqlDateTime m;
   TimeToStruct(shifted, m);
   return m.year * 10000 + m.mon * 100 + m.day;
}

// True if ET time falls within [start,end). Handles windows wrapping midnight.
bool InWindowET(datetime et, int sh, int sm, int eh, int em)
{
   int t     = ETMinutes(et);
   int start = ToMinutes(sh, sm);
   int end   = ToMinutes(eh, em);
   if(end == 0) end = 24 * 60;          // treat 00:00 end as midnight
   if(start < end) return (t >= start && t < end);
   return (t >= start || t < end);      // wrapped window
}
//+------------------------------------------------------------------+
