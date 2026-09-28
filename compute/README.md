# compute: the first open Fab City Index calculation

```bash
python3 compute/fabcity_index.py --selftest   # no network; must reproduce Hamburg's 37
python3 compute/fabcity_index.py              # fetches Eurostat, writes results/fabcity-index-2019.json
```

Standard-library Python only. This is the worked example the method page says is owed. It takes Niels Boeing's
Hamburg recipe (*The Fab City Index*, Springer 2024, ch. 9, CC-BY), states it as code, checks it reproduces
his published score, and re-derives as much of it as open data allows. Nothing here is on the site yet.

## The recipe

Boeing split a city's economy into 16 macro-sectors. For each one he compared **local production value** with
**local consumption spending** (NACE industries matched to COICOP consumption groups) and capped the result at
100%. He then weighted the sectors in per mille by the consumer price index basket, or by his own estimate
where no consumption data exists, and summed. For Hamburg in 2019 that gave **37**. His table (p. 124) is
transcribed in [`boeing2024.json`](boeing2024.json). Its columns sum to the printed 664.05 + 335.95 = 1000,
and the self-test holds them to that.

Two small corrections to the table as printed: construction is NACE **F**41–F43, printed "C41–C43"; and Fig. 9.1
shows different values for chemicals, metals and machinery (80/35/80%) from the table (90/50/90%). The
table's values are the ones that give 37, so they are the reference.

## The open version

Boeing's inputs were mostly Statistikamt Nord series, which are not an open API. The open version models each
sector for a region from Eurostat national totals:

- **production** = national production value per industry × the region's share of national employment in it
  (`sbs_na_ind_r2` V12120 and V16110, `sbs_r_nuts06_r2` V16110)
- **consumption** = national household spending per COICOP group × the region's share of population, net of
  VAT (`nama_10_co3_p3`, `demo_r_d2jan`)
- **ratio** = production ÷ consumption, capped at 1. The uncapped `raw_ratio` is kept alongside.

Neither side is a regional measurement: both are **modelled**, and every result says so. Five sectors can be
re-derived this way: food, textiles, pharmaceuticals, IT equipment and other goods. They carry 328 of the
1,000 per mille. Four cannot, and the script records why. Metals and machinery are set against investment,
not household spending. Car making (C29) is suppressed for Hamburg. Repair needs detail nobody publishes.
The other seven sectors (energy, water, farmland, wood, mining, construction, waste) are not
production-vs-consumption sectors at all. They carry Boeing's values, flagged as carried.

Where a sector's concordance differs from Boeing's table, the output says how. Pharmaceuticals only, because
his C19–C22 against all of COICOP 06 sets refinery output against hospital services. IT equipment only,
because COICOP 08 is mostly telecom services.

## Results, 2019

| | Index | What it is |
| --- | --- | --- |
| Boeing's inputs, this arithmetic | **37.3** | reproduces the published 37 |
| Hamburg, open sectors substituted | **36.7** | 328‰ re-derived from Eurostat, the rest carried from Boeing |
| Goods capacity, Hamburg (DE60) | 34.6 | the five open sectors only, German HICP weights |
| Goods capacity, Cataluña (ES51) | 91.0 | same sectors, Spanish HICP weights |
| Goods capacity, Île-de-France (FR10) | 99.6 | same sectors, French HICP weights; pharma has no data (national C21 suppressed) |

## What it shows, and what it does not

**Hamburg comes out at 36.7 against 37, but not because the sectors agree.** The open model puts food at 37%
(Boeing 54%), other goods at 29% (63%) and IT at 100% (20%). The differences largely cancel. IT is the
clearest case: Hamburg's C26 production value exceeds local spending on devices, but Boeing marked it down
because those firms make semiconductors, not phones. A NACE-to-COICOP match cannot see that. So this
reproduces the method, not his judgement calls, and two thirds of the weight is still his.

**The goods figures measure capacity, not self-supply.** Cataluña's pharmaceutical production is 4× its own
consumption; Île-de-France's IT equipment 8.8×, which almost certainly includes a headquarters effect, since
firms report employment where they are registered. Regions that make goods for their country and for export
cap at 100%, although their residents may buy almost none of it. Utopies put Paris's self-sufficiency at
**8.7%** (2018), against a 99.6 here. Boeing's own framing was "potential production capacity compared to its
demand" (p. 121), and at city scale that is a different quantity from self-supply.

**That is the case for trade data.** Separating what a place makes for itself from what it makes for others
needs to know what leaves and what arrives: regional imports and exports, or a regional input-output table.
None of that exists openly below country level for these regions. It is recorded as the Index's most
important gap in [awesome-fabcity-data#42](https://github.com/fabcity/awesome-fabcity-data/issues/42).

## Trash out: the waste half of PITO

`compute/waste.py` reads the four open waste sources filed in awesome-fabcity-data and reports, per city,
waste generated per capita, **residual waste per capita** (the proposed "trash out" measure, #42) and the
recovery share. The recovery share is also Boeing's input for macro-sector 16, which he scored for Hamburg as a
24.8% recycling share.

| City | Year | Generated kg/cap | Residual kg/cap | Recovery | What it counts |
| --- | --- | --- | --- | --- | --- |
| Barcelona | 2019 · 2024 | 483.6 · 446.8 | 295.8 · 258.5 | 38.8% · 42.1% | collected municipal waste; recovery = separate collection |
| **Catalonia (region)** | 2019 · 2024 | 527.2 · 498.7 | 290.5 · 253.4 | 44.9% · 49.2% | Barcelona's measure summed over every municipality (948); Environmental\|Region's waste row |
| Paris | 2019 · 2024 | 464 · 436 | 341 · 308 | 26.5% · 29.4% | household waste only; recovery = sorted streams |
| Santiago (comuna) | 2019 · 2022 | 429.8 · 220.6 | not recorded · 216.8 | not recorded · 1.7% | tonnes declared (209 kt · 116 kt) per INE's projected population |
| **Región Metropolitana (region)** | 2019 · 2022 | 454.3 · 433.4 | not recorded · 392.7 | not recorded · 1.7% | the same, summed over the region's comunas by code; 2022 has 282 kt with no treatment recorded |
| Hamburg | 2019 · 2024 | 430.4 · 417.4 | 255.5 · 250.1 | 40.0% · 39.4% | public collection (Statistikamt Nord Q II 9); residual = Haus- und Sperrmüll; recovery = separate collection |

Catalonia is the first **region** in the pipeline. Eurostat has no regional waste table, so it is the Generalitat's
municipal data summed server-side. The dataset has no Catalonia total row, so nothing is counted twice, and the
population sum (8,012,231 in 2024) is kept so it can be checked against the official figure.

Santiago's per-capita figures divide RETC's declared tonnes by **INE Chile's population projections** (base 2017),
committed as a small extract in [`data/`](data/) because INE's server delivers a few KB/s.
`python3 compute/waste.py --extract-ine` rebuilds it from the source. INE's own terms put its data under
**CC BY-SA 4.0**, which is share-alike: the per-capita figures are shared under that licence too. (datos.gob.cl
labels the same series "cc-nc", which contradicts the publisher.) Recovery and residual are shares of the
tonnes whose treatment **is** recorded; tonnes with none are reported as `treatment_not_recorded_t`, outside both.
Comuna Santiago's 2022 figure is half its 2019 one because fewer operators declared, not because of less waste.

**These rows are not comparable yet.** Each counts a different thing, and the table says what. Santiago sends
98% of what it declares to sanitary landfill, and so does its region. Its 2019 file records no treatment at all, which is "not
recorded", not 0%: the self-test pins that. Its total nearly halves between 2019 and 2022, which is a change in
who declares, not in the waste. Hamburg's split comes from Statistikamt Nord's Q II 9 workbook, published on Hamburg's Transparenzportal under
dl-de/by-2.0; the report's own notice permits extracts only, and the registry records both. Its 2019 separate
collection is 40.0%, while Boeing scored sector 16 as a 24.8% recycling share, a different measure, so his value stays
carried in the index rather than being replaced by a number that means something else.

### The national benchmark

Each city row names its `country`. `waste.national()` reads Eurostat's national tables
(awesome-fabcity-data#46) for the same years: municipal waste generated, **generated minus recycled** (the
national counterpart of residual waste), the official recycling rate, and waste **exported and imported** in
tonnes, the "trash out" flow at the border.

| Country | Year | Generated kg/cap | Generated − recycled | Recycling rate | Waste exported · imported (t) | Net export |
| --- | --- | --- | --- | --- | --- | --- |
| Germany | 2019 · 2024 | 609 · 628 | 203 · 208 | 66.7% · 66.9% | 16.0 Mt · 15.5 Mt (2024) | +0.5 Mt |
| Spain | 2019 · 2024 | 472 · 456 | 293 · 262 | 38.0% · 42.5% | 3.5 Mt · 7.2 Mt (2024) | −3.7 Mt |
| France | 2019 · 2024 | 555 · 530 | 327 · 313 | 41.0% · 40.9% | 13.0 Mt · 4.5 Mt (2024) | +8.5 Mt |

Barcelona (258.5) and Catalonia (253.4) sit just under Spain's 262, and Paris (308) just under France's 313. The
city rows count **separate collection**, the national rows count **recycling**, so the gap is not all
performance. Hamburg's public collection, 417.4 kg/cap, is far below Germany's national 628. That is most likely scope,
not performance: the city series counts only what the public collection gathers, and the national series is broader
(not verified line by line). Hamburg's residual, 250.1 kg, is close to Barcelona's 258.5 and Catalonia's 253.4. Chile has no Eurostat
equivalent, so Santiago's rows have no national benchmark yet. A missing trade value leaves the export,
import and net figures empty, never a partial sum.

## Gateway flows: goods in and out through the ports and airports

`compute/trade.py` fills Economic|Bioregion's gateway row: goods handled by the territory's ports and airports, in
tonnes, **inwards and outwards reported separately**. Ports come from Eurostat `mar_mg_aa_pwhd`
(`economic/region/eurostat-maritime-goods-by-port`) and airports from `avia_gooa`
(`economic/region/eurostat-air-freight-by-airport`). Sea and air are separate rows and are never added together.

| Territory | Port | Year | Inwards | Outwards |
| --- | --- | --- | --- | --- |
| Barcelona | Barcelona (`ES_2ESBCN`) | 2019 · 2024 | 29.9 · 29.9 Mt | 24.8 · 25.7 Mt |
| Hamburg | Hamburg (`DE_1DEHAM`) | 2019 · 2024 | 68.1 · 56.4 Mt | 49.0 · 40.6 Mt |
| Paris | HAROPA, Le Havre and Rouen (`FR_1FR001`) | 2024 | 48.0 Mt | 28.7 Mt |
| Barcelona | El Prat airport (`ES_LEBL`) | 2019 · 2024 | 68,684 · 87,094 t | 74,459 · 95,432 t |
| Hamburg | Hamburg airport (`DE_EDDH`) | 2019 · 2024 | 12,346 · 16,254 t | 15,035 · 13,603 t |
| Paris | Charles de Gaulle + Orly (`FR_LFPG`, `FR_LFPO`) | 2019 · 2024 | 1,016,345 · 960,704 t | 1,178,406 · 1,023,906 t |
| Boston | none | | no data: US Census trade by port needs an API key this pipeline does not hold | |
| Santiago | none | | no data yet: Chile's customs declarations are monthly RAR/ZIP files, not read yet | |

**This is throughput, not consumption.** Hamburg's port handles about 57 Mt coming in for 1.9 million people, and
much of it is transhipment or cargo for a hinterland far beyond the city (this pipeline has not measured the share).
That is why Boeing left trade out of his index. HAROPA is Paris's sea gateway on the Seine, not a port in Paris, and it only exists as one
series from 2021, when Le Havre and Rouen merged, so Paris has no 2019 figure. Airports count freight and mail unloaded (inwards) and loaded
(outwards). By weight they are small: Barcelona's airport moved 0.18 Mt in 2024 against 55.5 Mt by sea. By value they
are not small, and a tonnage row cannot show that. Charles de Gaulle is a cargo hub, so part of its tonnage is
transferred between aircraft and never enters Paris (this pipeline has not measured how much). Paris's air row sums its two airports, and if either one
misses a direction, that direction is empty rather than a partial sum. Road and rail are not read yet. A direction the port did not report stays empty, never zero.
The module reports tonnes and never a ratio: turning gateway tonnage into a share of what a place consumes needs the
regional trade data recorded as the Index's most important gap (awesome-fabcity-data#42).

## Regional trade: what the territory exports and imports

`trade.regional()` fills Economic|Region's external-trade row from Idescat's `comest` table 18132 (AEAT customs
records, key-free JSON-stat; registry `economic/region/idescat-comerc-exterior`). It reports **imports and exports
in euros and in tonnes, each separately**, and never draws a balance.

| Territory | Year | Imports | Exports |
| --- | --- | --- | --- |
| Province of Barcelona | 2019 | 74.3 bn EUR · 31.4 Mt | 57.1 bn EUR · 21.4 Mt |
| Province of Barcelona | 2024 (provisional) | 87.4 bn EUR · 25.3 Mt | 77.2 bn EUR · 19.8 Mt |
| Catalonia | 2019 | 92.6 bn EUR · 56.8 Mt | 73.9 bn EUR · 34.3 Mt |
| Catalonia | 2024 (provisional) | 111.4 bn EUR · 51.2 Mt | 100.3 bn EUR · 32.1 Mt |
| Land Hamburg | 2019 (final) | 67.5 bn EUR | 53.4 bn EUR |
| Land Hamburg | 2024 (final) | 73.9 bn EUR | 56.1 bn EUR |
| Paris (département 75) | 2024 | 41.8 bn EUR | 28.3 bn EUR |
| Île-de-France | 2024 | 192.4 bn EUR | 141.8 bn EUR |
| Boston metro area | 2019 (revised) | not published | 23.5 bn USD |
| Boston metro area | 2024 (revised) | not published | 29.9 bn USD |

**It counts something different from the gateway row.** Customs trade is goods crossing the Spanish border, attributed
to the declarant's province wherever they physically entered. Port throughput is what a port handled, including
transit and Spanish coastal traffic. Neither can be subtracted from the other. Trade with the rest of Spain is not in
either. Idescat flags 2024 and 2025 as
provisional, and so do the rows. Idescat names no licence, only Spain's statutory reuse conditions, and whether those
count as open is still a maintainer's call (awesome-fabcity-data#51).

**Hamburg** comes from `trade.hamburg()`, which reads Statistikamt Nord's annual report G III 1 / G III 3 (registry
`economic/region/statistikamt-nord-aussenhandel-hamburg`, dl-de-by-2.0 on the Transparenzportal). The file is found
through the portal's CKAN, because the names drift. Each edition holds two years, and its header flags each year `a`
(may still change through revision) or `b` (final). So a year's figure is read from the **next** year's edition,
where it is final, and only falls back to its own edition, flagged provisional. Hamburg's 2019 imports read 66.6 bn
EUR in the 2019 edition and 67.5 bn in the 2020 edition. It is **values only**, and the two directions follow
different concepts: imports are general trade, which includes goods entering customs warehouses whose destination is
not yet known, and exports are special trade, goods made or last processed in Hamburg. Their difference is not a
trade balance, which is Boeing's reason for leaving trade out of Hamburg's 37.

**Paris** comes from `trade.paris()`, which reads French customs' annual regional file for Île-de-France
(`region_03_A.zip`, the same plain GET the download page's own script builds; registry
`economic/region/dgddi-commerce-exterieur-regional`). It sums the file's département x product x country rows,
for Paris (75) and for the region. Two things were checked against the site, not assumed. The values are **euros**
(the column header is right and the file's readme, which says thousands, is wrong): the region's sums equal the
published totals to the thousand. And the file has no aggregate rows to double-count. It carries **only the last
three calendar years** (2023–2025), so Paris has no 2019 figure, and the output says so. The file does not flag
provisional years, so the rows leave that empty rather than guess. Trade is attributed to the declaring firm's
establishment, so a département with head offices, as Paris has, can show trade made elsewhere. Rows carry DGDDI's
required citation, « source : douanes françaises, résultats de [mois année] ». Idescat's licence caveat (#51)
applies here too: reuse on statutory conditions, and Licence Ouverte is not named.

**Boston** comes from `trade.boston()`, which reads the Census Bureau's U.S. Exports by Metropolitan Area (registry
`economic/region/census-metro-area-exports`, US public domain). Each year's Q4 workbook carries that year's annual
total and the previous year's, and the previous year is revised in the next workbook (Boston 2019: 23,505.8 then
23,508.2 million USD). So a year is read from the next year's workbook, and only falls back to its own, flagged
provisional as a first release. A workbook not published yet is a 404, which the fetch no longer retries. It is
**exports only, in US dollars**: no imports are published below state level, the state series needs an API key this
pipeline does not hold, and dollars are never converted to euros here. Exports are attributed to the exporter of
record's location, not to where the goods were made.

Santiago has no open source (#50). Each is listed in the output with that reason. `_pick` now reads JSON-stat whose index and values
are arrays (Idescat) as well as objects (Eurostat), and `_status` reads the provisional flag.

## Hamburg with trade taken out (2022)

`hamburg_trade_adjusted()` answers "what does trade do to Hamburg's number". The recipe's production side for the five
open sectors is **modelled** (national production times Hamburg's employment share), and Hamburg's measured exports
abroad are larger than that modelled production for food, textiles and other goods. Subtracting one from the other
gives nonsense. So this variant replaces the model with **measured** turnover from Statistikamt Nord's manufacturing
report E I 1 (registry `economic/region/statistikamt-nord-verarbeitendes-gewerbe-hamburg`): turnover from own
production and the part of it sold abroad, by WZ division.

| Sector | Made in Hamburg | Sold abroad | Local consumption | Capacity | Trade-adjusted |
| --- | --- | --- | --- | --- | --- |
| Food and beverages (C10, C11) | 3,316 M | 1,448 M | 5,015 M | 0.66 | 0.37 |
| Pharmaceuticals (C21) | 780 M | 95 M | 888 M | 0.88 | 0.77 |
| IT equipment (C26) | 887 M | 694 M | 748 M | 1.00 (1.19) | 0.26 |
| Other goods (C32; C23 partly suppressed) | 1,131 M | 667 M | 3,473 M | 0.33 | 0.13 |
| Textiles and clothing | suppressed | | 1,624 M | carried | carried |

With the other eleven sectors carrying Boeing's 2019 ratios, Hamburg's index is **41.1 on measured capacity and
32.2 with sales abroad taken out**: trade alone moves it by 8.9 points on 278 of the 1,000 weight points. The
measured capacity is higher than the modelled 36.7 because Hamburg's plants outproduce their employment share (food:
3,316 M measured against 1,563 M modelled for 2019).

**Read it as an upper bound on self-supply.** Sales to the rest of Germany still count as local, and nothing open
measures them. E I 1 covers plants with 20 or more people. Turnover is sales, not production
value, though own-production turnover leaves out goods bought in and resold. A division counts only where both its
turnover and its foreign turnover are published, so both ratios cover the same plants. Imports are not used: they are
general trade, including goods passing through warehouses.

**Why 2022, and a licence note.** 2022 is the latest year with both inputs: Germany's household spending by purpose
on Eurostat ends there, and E I 1 has no 2019 or 2020 annual edition. So this sits beside Boeing's 2019 figure and
does not replace it. E I 1 is not open by the registry's rule (its imprint permits extracts with attribution and
reserves other rights, and it is not on the Transparenzportal). Tomas Diez decided on 2026-09-27 to use it under those
terms, and every row carries that licence.

**The same on the open goods alone**, weighted by Germany's 2022 HICP basket and comparable with Barcelona below:
59.4 on capacity, 32.2 trade-adjusted.

## Barcelona with trade taken out (2019 and 2022)

`barcelona_trade_adjusted()` does the same for Catalonia (ES51, Barcelona's region) from Idescat's industrial survey
(registry `economic/region/idescat-eie-destinacio-vendes`, based on INE's Structural Business Statistics). It gives
turnover by activity group split into Spain, the rest of the EU and the rest of the world, for every year from 1999, so
this one sits on **Boeing's year, 2019**, as well as on 2022 for comparison with Hamburg.

| Catalonia, 2019 | Made in Catalonia | Sold abroad | Local consumption | Capacity | Trade-adjusted |
| --- | --- | --- | --- | --- | --- |
| Food and beverages (incl. tobacco) | 30,090 M | 7,990 M | 14,823 M | 1.00 (2.03) | 1.00 (1.49) |
| Textiles and clothing | 4,558 M | 1,956 M | 4,391 M | 1.00 (1.04) | 0.59 |
| Pharmaceuticals | 7,166 M | 3,673 M | 1,782 M | 1.00 (4.02) | 1.00 (1.96) |
| IT equipment | 6,117 M | 2,814 M | 845 M | 1.00 (7.24) | 1.00 (3.91) |
| Other goods (incl. furniture) | 5,251 M | 1,571 M | 5,232 M | 1.00 | 0.70 |

| Open goods index | Capacity | Trade-adjusted |
| --- | --- | --- |
| Catalonia 2019 | 100.0 | 86.6 |
| Catalonia 2022 | 100.0 | 91.3 |
| Hamburg 2022 | 59.4 | 32.2 |

**Trade barely moves Catalonia, and that says more about the data than about Catalonia.** Even with sales abroad taken
out, Catalan industry sells more food, pharmaceuticals and electronics than Catalan households buy. What is not
exported mostly goes to the rest of Spain, and Idescat's split counts the rest of Spain as local. So this is a much
looser upper bound than Hamburg's, where exports abroad are most of what leaves. Measuring what stays in Catalonia needs
interregional trade, which no open source in the registry has yet.

There is **no full index for Barcelona** on purpose. Boeing's other eleven ratios, which Hamburg's full index carries,
are Hamburg's own energy, water, farmland and so on. Carrying them into Catalonia's number would dress Hamburg up as
Barcelona. The goods index covers 366 of the 1,000 weight points in 2019. Two groups are wider than Boeing's sectors:
beverages come with tobacco, and "other goods" includes furniture. Idescat names no licence, only Spain's statutory
reuse terms, as for its trade data.

## São Paulo and Recife with trade taken out (2019)

`brazil_trade_adjusted()` reads the two cities as their states, because Brazil publishes no city figures for
production or spending: São Paulo state, and Pernambuco for Recife (registry #65). Production is IBGE's industrial
survey (PIA-Empresa, SIDRA table 1849, gross value of production by CNAE division, local units with 5 or more people;
nothing suppressed). Exports are ComexStat's, by **state of production** and ISIC division, converted at the central
bank's 2019 average rate (3.9461 R$ per US$). Consumption is IBGE's household budget survey 2017-18 (POF): spending
per family per month, times 12, times the number of families. The goods index is weighted by each state's own
spending on the five sectors.

| 2019, goods index | Capacity | Trade-adjusted |
| --- | --- | --- |
| São Paulo (state) | 100.0 | 100.0 |
| Recife (Pernambuco) | 72.5 | 72.4 |

| Pernambuco, 2019 | Made | Exported | Household spending | Capacity |
| --- | --- | --- | --- | --- |
| Food and beverages | 19,298 M R$ | 480 M | 14,583 M | 1.00 (1.32) |
| Textiles and clothing | 1,878 M | 31 M | 5,632 M | 0.33 |
| Pharmaceuticals | 1,224 M | 1 M | 3,830 M | 0.32 |
| Electronics (phones only on the spending side) | 28 M | 3 M | 1,222 M | 0.02 |
| Other goods | 2,738 M | 71 M | 2,226 M | 1.00 (1.23) |

**Exports hardly move either state**: they are a small share of what Brazilian industry makes (São Paulo's food, the
largest, is 21%). The number that matters is the one this cannot see, sales to the rest of Brazil. São Paulo state
supplies much of the country, so its 100 is capacity, not self-supply. Recife's 72 is the more telling figure:
Pernambuco makes more food and "other goods" than its households buy, and almost none of its clothing, medicines or
electronics. Exports are products by state of production, a proxy for the same firms' sales abroad. POF puts TVs and
computers inside appliances, with fridges, so electronics spending is phones only and that sector's capacity is
overstated. Spending is in 2017-18 reais against 2019 production (prices rose about 4%). ComexStat is used as open
government data under Decreto 8.777/2016, by Tomas Diez's decision, though its site footer reads CC BY-ND.

## Who has what

| City | Trade-adjusted goods index | What it rests on | What is missing |
| --- | --- | --- | --- |
| Hamburg | 32.2 (2022) | E I 1 turnover and foreign turnover, same plants | sales to the rest of Germany; E I 1 is used under its own terms (#61) |
| Barcelona | 86.6 (2019), 91.3 (2022) | Idescat turnover by destination | sales to the rest of Spain (Idescat's material-flow account has them in tonnes, #64) |
| São Paulo | 100.0 (2019) | IBGE production, ComexStat exports, POF | sales to the rest of Brazil; city figures |
| Recife | 72.4 (2019) | the same, for Pernambuco | the same |
| Paris | none | | measured production with its export share for Île-de-France (#63) |
| Bali | none yet | BPS website tables, usable by decision: large/medium industry to 2021, exports by HS chapter | micro and small industry by division (the larger part), the export share, 2022+ |
| Boston, Santiago | none | | measured production by industry for the metro or region |

## Next

1. Replace carried sectors with open data where it exists: the renewable share of electricity and farmland.
   Waste now has open data for Barcelona, Paris and Santiago; Hamburg's recovery split does not.
2. Santiago is the one pilot without regional trade: the Banco Central's terms are revocable, and INE Chile's
   regional export tables were not reachable (#50). Idescat's transport-mode split (MOD_TRANS) can also put Barcelona's sea and air trade beside its
   gateway rows. A trade-adjusted variant still needs a methodology (item 3).
3. Settle what the Index should report, capacity or self-supply. That is a methodology decision (FCI 3.0 §7),
   not a data one.

Data: Eurostat, reuse authorised with acknowledgement (Commission Decision 2011/833/EU). Method: Boeing (2024), CC-BY 4.0.

## Material use: the planetary comparison

`trade.materials()` reads Catalonia's domestic material consumption (DMC) from Idescat's material flow accounts,
table 16006 (registry `economic/region/idescat-compte-fluxos-materials`), into `material_flows`: 7.20 t per person in
2019 and 5.51 in 2023. It is the one per-person figure in the pipeline with a published per-person safe level, about
6-8 t by 2050 (UNEP IRP 2011, Bringezu 2015), so a place's report sets the two side by side. DMC counts imports by
their own weight, not the raw materials used to make them, so for an importing region it is a floor on its footprint:
under the safe range it proves nothing, and the report says "not conclusive".

## From results to the site: `api.mjs`

The site build (`build.sh`) runs `node api.mjs`, which maps these results to cells and indicators (its `MEASURED`
section is the only place that does) and scores every place with the pages' own `js/fci-score.js`. It writes
`/api/v0/index.json`, `index.csv`, `places/<slug>.json` and `measured.json`. A result that `api.mjs` does not map
reaches no page. Today the Economic|Region goods index is the only cell score (Barcelona, Hamburg, São Paulo,
Recife); waste and material use are indicators the report follows, not inputs to the FCI.

## Santiago with trade taken out: ENIA and the EPF

`santiago_trade_adjusted()` reads Santiago as the **Región Metropolitana** (region 13). Its inputs are INE Chile's:
- **ENIA** industrial survey microdata: each establishment's gross value of production (K009) and its export income (K003), so production and exports cover the same plants.
- **EPF** household budget survey: Gran Santiago's mean spending per household by COICOP group, turned into spending per person and scaled to the region's population with INE's projections.

| Year | Spending survey | Goods capacity | Trade-adjusted |
| --- | --- | --- | --- |
| 2019 | VIII EPF (2016–17) | 87.3 | 83.7 |
| 2022 | IX EPF (2021–22) | 79.7 | 71.6 |

**It is an upper bound on self-supply.** Sales to the rest of Chile count as local, as they do for the other regions.

**The two years are not a trend.** They rest on different spending surveys, in their own prices. The surveys also use different product classifications: IX moved phones and computers into 08.1 and redrew group 09.

**Some ENIA figures need handling:**
- About 5% of rows report in thousand US$ and are converted at the World Bank's annual rate: 702.9 CLP/US$ in 2019 and 873.3 in 2022.
- INE hides a few rows' industry by cutting CIIU4 to the section, "C". Those rows are counted, not assigned: 1 row in 2019, worth 19.5 bn CLP.
- With it, the 2019 divisions sum to INE's published regional total, 19,549.5 bn CLP, within 0.01%.
- IT and electronics (division 26) is 8 establishments in 2022.

**Other goods caps at 100% in 2022.** It includes cement and concrete (C23), which households mostly buy through construction.

**Licence and access.** INE publishes under CC BY-SA 4.0, so these figures are share-alike. INE's server drops connections for minutes at a time, so the pipeline reads a committed extract, `data/ine-chile-enia-epf-extract.json`. Rebuild it with `python3 compute/trade.py --extract-cl`.

**Customs cross-check (not an input).** Chile's customs export declarations (`aduanas-chile-registros-comercio-exterior`) record each line's region of origin. Region 13's 2019 ordinary goods exports, operation 200, total US$6.72 bn. That figure excludes services exports (operations 202 and 211) and seven lines, US$442.5 M in total, whose value per kilogram is more than 100 times their tariff code's median. One of those lines is US$353.6 M for 3,753 handbags.
