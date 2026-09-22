"""Arithmetic audit of manually transcribed visible screenshot parameters, no OCR."""
from pathlib import Path
import json,math
ROOT=Path(__file__).resolve().parent
COUNTS=[24,38,9,34,28,13,26,27,23,25,30,11,15,12,4,1,10,17,3,20,16,6,23,8,7]
PCTS=[31.08,50,10.81,44.59,36.49,16.22,33.78,35.14,29.73,32.43,39.19,13.51,18.92,14.86,4.05,1,12.16,21.62,2.70,25.68,20.27,6.76,29.73,9.46,8.11]

def main():
    rows=[{'displayed_count':c,'displayed_total':76,'displayed_percent':p,'raw_count_percent':100*c/76,
           'candidate_adjusted_percent':max(1.,100*(c-1)/74),'adjusted_matches_rounding':round(max(1.,100*(c-1)/74),2)==p} for c,p in zip(COUNTS,PCTS)]
    n=76;k=74;p=k/n;z=1.959963984540054;den=1+z*z/n;mid=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    doc={'source':'user-supplied QQQWave image; manual visual transcription, no OCR',
         'visible_settings':{'instrument':'QQQ','aggregation':'1 day','daily_aggregations':200,'forward_aggregations':5,
              'weekday_matching_selected':True,'HL_matching_selected':False,'reference':721.45001,'minavg_display':715.69,'tooltip_percent':97.37,
              'as_of_display':'2026-09-20 11:19:43 New York','start_aggregation':'2026-09-18','fractal_dataset_start':'2025-12-02','fractal_dataset_end':'2026-09-18',
              'forecast_dates':['2026-09-21','2026-09-25'],'bull_extreme':767.41,'bear_extreme':682.92},
         'unknown':['vendor formula','definition of MinAvg','bear conditioning rules','derivation of 76','overlap treatment','whether tooltip uses same denominator','whether IV options data is actually input'],
         'count_rows':rows,'possible_display_rule':'max(1%,100*(count-1)/(total-2)); all 25 visible rows match to 2 decimals. Hypothesis, not documented vendor formula; upper clipping not observable.',
         'minavg_move_percent':(715.69/721.45001-1)*100,'hypothetical_74_of_76_percent':100*k/n,
         'hypothetical_independent_Wilson_95_percent':[100*(mid-half),100*(mid+half)],
         'Wilson_qualification':'Illustration only if tooltip really means 74/76 independent trials. Neither count nor independence established for tooltip.',
         'fee_example':{'notional':3.6*2748.67,'initial_margin_at_150x':3.6*2748.67/150,'five_usd_bps_notional':5/(3.6*2748.67)*10000,
                        'five_usd_percent_margin':5/(3.6*2748.67/150)*100,'one_way_round_trip_unknown':True}}
    (ROOT/'SCREENSHOT_ANALYSIS.json').write_text(json.dumps(doc,indent=2)+'\n')
    print('All visible adjusted rows match:',all(x['adjusted_matches_rounding'] for x in rows))
if __name__=='__main__':main()
