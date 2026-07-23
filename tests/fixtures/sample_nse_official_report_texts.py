"""Real NSE report excerpts used as parser fixtures.

Every row below was downloaded live from NSE on 2026-07-23 (trade date
2026-07-22) and trimmed — nothing is invented, so these fixtures pin the
parsers to the genuine formats, quirks included (leading spaces, `-`
delivery fields, empty strike/option columns on futures, `NO RECORDS`
placeholder rows, "No Fresh Positions" ban marker).
"""

SAMPLE_CASH_BHAVCOPY_WITH_DELIVERY_CSV = """\
SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER
20MICRONS, EQ, 22-Jul-2026, 211.01, 209.96, 211.62, 205.10, 211.49, 211.15, 209.40, 201717, 422.39, 3517, 89309, 44.27
1018GS2026, GS, 22-Jul-2026, 104.00, 106.60, 106.60, 103.50, 104.25, 104.25, 103.67, 10863, 11.26, 14, 6773, 62.35
AAREYDRUGS, BE, 22-Jul-2026, 77.53, 76.50, 77.01, 75.98, 75.98, 75.98, 76.10, 19649, 14.95, 38, -, -
"""

SAMPLE_FO_BHAVCOPY_CSV = """\
TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4

2026-07-22,2026-07-22,FO,NSE,STO,67233,,ABCAPITAL,,2026-08-25,2026-08-25,350.00,PE,ABCAPITAL26AUG350PE,1.50,1.80,1.50,1.65,1.80,1.60,400.60,1.65,93000,18600,7,7630650.00,6,F1,3100,,,,,

2026-07-22,2026-07-22,FO,NSE,IDO,80310,,NIFTY,,2027-03-30,2027-03-30,30000.00,PE,NIFTY27MAR30000PE,0.00,0.00,0.00,5754.50,5754.50,5754.50,23996.25,4848.10,130,0,0,0.00,0,F1,65,,,,,

2026-07-22,2026-07-22,FO,NSE,IDF,58067,,BANKNIFTY,,2026-08-25,2026-08-25,,,BANKNIFTY26AUGFUT,58201.00,58201.00,57351.00,57469.20,57450.00,58239.20,57126.80,57469.20,619980,120240,7976,13778694180.00,5956,F1,30,,,,,

2026-07-22,2026-07-22,FO,NSE,STF,58086,,ABCAPITAL,,2026-08-25,2026-08-25,,,ABCAPITAL26AUGFUT,411.50,413.40,401.75,403.00,402.80,411.30,400.60,403.00,3627000,1472500,1070,1348838055.00,922,F1,3100,,,,,
"""

SAMPLE_FO_BAN_LIST_CSV = """\
Securities in Ban For Trade Date 23-JUL-2026:
1,KAYNES
"""

SAMPLE_BULK_DEALS_CSV = """\
Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price,Remarks
22-JUL-2026,AASTHA,Aastha Spintex Limited,IRAGE BROKING SERVICES LLP,BUY,160009,118.96,-
22-JUL-2026,AASTHA,Aastha Spintex Limited,SETU SECURITIES PVT LTD,SELL,300053,107.10,-
"""

SAMPLE_BLOCK_DEALS_NO_RECORDS_CSV = """\
Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price
NO RECORDS,,,,,,
"""

SAMPLE_MWPL_POSITION_LIMIT_CSV = """\
Date, ISIN, Scrip Name, NSE Symbol, MWPL, Open Interest, Future Equivalent Open Interest, Limit for Next Day
22-JUL-2026,INE918Z01012,KAYNES TECHNOLOGY IND LTD,KAYNES,4679418,6212400,3750756.456332,No Fresh Positions
22-JUL-2026,INE466L01038,360 ONE WAM LIMITED,360ONE,51083894,10166000,5336596.467485,43193102
"""

SAMPLE_NSE_HTML_ERROR_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head><title>Access Denied</title></head>
<body>resource not found</body>
</html>
"""
