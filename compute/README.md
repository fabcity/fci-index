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
| Hamburg | 2019 · 2024 | 425.8 · 413.6 | n/a | n/a | Urban Audit total only, no split |

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
who declares, not in the waste. Hamburg's recovery split exists only in Statistikamt Nord PDFs, so its sector
16 still carries Boeing's value.

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
performance. Hamburg's Urban Audit total, 413.6 kg/cap, is far below Germany's national 628. That is more
likely a difference in what each source counts than a city making a third less waste. Chile has no Eurostat
equivalent, so Santiago's rows have no national benchmark yet. A missing trade value leaves the export,
import and net figures empty, never a partial sum.

## Next

1. Replace carried sectors with open data where it exists: the renewable share of electricity and farmland.
   Waste now has open data for Barcelona, Paris and Santiago; Hamburg's recovery split does not.
2. Add a trade-adjusted variant once regional exports exist for a pilot, starting with Destatis by
   federal state or DataComex by province.
3. Settle what the Index should report, capacity or self-supply. That is a methodology decision (FCI 3.0 §7),
   not a data one.

Data: Eurostat, reuse authorised with acknowledgement (Commission Decision 2011/833/EU). Method: Boeing (2024), CC-BY 4.0.
