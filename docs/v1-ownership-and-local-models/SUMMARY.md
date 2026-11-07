# Fab City Index, a v1 proposal for review

Tomas Diez, Fab City, 7 November 2026

## What I'm asking

I'd like the review to look at two things the Index doesn't measure yet. Who owns the machines a city can make
things with? Where does the AI in those workshops run, on hardware and models the place controls, or on a service
somewhere else that nobody there can open?

A city can have fab labs everywhere and still own none of them. A lab can design locally and send every model
call to a company on another continent. Either way the capacity to make sits in the place, but the decisions about
it don't, and today the Index can't tell the difference.

## The two measures

- **Production capacity owned locally:** of the machines mapped in a place, the share owned by local public bodies,
  cooperatives, residents or firms owned in the place.
- **Nodes running models under local control:** of the design and production workshops a place reports, the
  share whose AI runs on their own hardware, or on open models they can inspect and retrain.

Both are numbers between 0 and 1, and both lose weight as they age, the way the measured cells of the Index do
today (full weight for two years, nothing at twelve).

## How they enter the score

The Index is DIDO × (1 − PITO) × ρ. DIDO is what a place senses, shares and can make, PITO is what it imports and
throws away, ρ is whether anyone acts on what it learns. None of that changes, and neither does the four by five
matrix or its v0 weights.

The change is inside DIDO, in five cells. Today each cell is a yes or a no, there is open data for it or
there isn't. In the two economic cells at neighbourhood and city scale, social at city scale and
governance at city and region scale, the yes or no would keep most of the weight and the new shares would take the
rest. Each indicator a cell already lists counts the same, so a new one takes between a seventh and a quarter of
its cell.

## What happens to the scores

They go down first. Until a place reports, the new shares count as nothing, the same rule the Index already uses
for missing data, and the coverage page shows them as unmeasured in every place. On today's data 41 of the 61
places lose some DIDO, 0.03 on average. Barcelona, the only place with open data in all five cells, loses the most,
0.084, and its index goes from 0.454 to 0.393. Boston and São Paulo swap fourth and fifth place. A place that
reports full local ownership and local models, in cells where it already has open data, gets its current score
back. The Index already treats a missing number as something a place hasn't shown yet, and the proposal keeps to
that.

## Where the numbers would come from

From the labs and cities themselves. Each would report its workshops, how many machines, who owns them, where
their models run, and when. The fab lab directory and the open hardware maps say where machines are but not who
owns them, we checked every record on 7 November, and nothing anywhere says where a lab's models run. Until reports
arrive these measures stay empty, and the Index says so instead of guessing.

## What I'd like the reviewers to decide

1. Whether the weight inside a cell should follow the cell's list of indicators, as proposed, or be set by hand.
2. Whether the age rule, which today only works on PITO, should work inside DIDO too.
3. Whether a place can be called complete without these two measures.
4. How to count machines whose owner is unknown, and workshops that run no AI at all. The proposal leaves both
   out of the share, so neither raises it nor lowers it.
5. Whether a count of labs from the fablabs.io directory may enter a score. Its records aren't openly licensed,
   and our decision of 14 October only covers showing the directory on the map.

## Paris, Hamburg and the count of places

Paris (37.58, Utopies 2018) and Hamburg (37.00, Boeing 2024) are results of other studies. The proposal doesn't
recompute or change them.

The site counts 61 Fab City places, from the coverage tracker. The June 2026 partner briefing counts 56 pledged and
46 active. Our June documents give the 56, from the Foundation's registry, and none of them gives the 46. I haven't
changed either number, the review should just know they differ, and we still have to decide which one the Index
follows.

The full placement report, the method text and the code are on the branch `index-v1-ownership-and-local-models`.

all the best
Tomas
