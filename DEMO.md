# The five-minute video

Plain language throughout. Assume the viewer has never heard of agentic
commerce, does not know what a checkout API is, and will decide in the first
twenty seconds whether to keep watching. Total runtime 4:55.

Everything below is a real click on a real screen. No slides, no mock-ups.

---

## How to read the dashboard, in one page

Learn these five things and you can narrate any screen without hesitating.

**A "shopping attempt" is one AI agent trying to buy one thing.** It has a
budget, a spending limit its owner gave it, and a shop to buy from. Two hundred
attempts is two hundred separate tries.

**Green dot = the money came back. Grey dot = nothing was lost, it bought
first time. Red dot = the money is gone.**

**Every attempt is tagged `treatment` or `control`.** Treatment means Handshake
was allowed to step in. Control means we deliberately did nothing, so we can
prove the recovery was us and not luck. This is the same method a medical trial
uses.

**The left sidebar is the two halves of the product.** *Recovery* wins back
sales that already failed. *Prevention* stops them failing in the first place.
*History* is every run ever stored, re-checked when you open it.

**The kill switch at the bottom left is a human's off switch.** One click and
the system stops spending money, mid-run, no matter what it has concluded.

Say those out loud once before you record. If you can explain the green dot and
the control tag, the rest of the screen explains itself.

---

## Before you record

Record against the deployed URL, so a judge watches the same thing they can
open themselves: **https://handshake-console.onrender.com**

```bash
./verify.sh          # locally, once: 62 tests, the batch, the scan, the chain
```

Then:

1. Load the URL and leave the tab open. The free instance sleeps after fifteen
   minutes and takes about a minute to wake. Never film a cold start.
2. Check the landing page shows **₹3,50,019 · 67.3 pts · 84.3%**. If it shows
   something smaller, someone ran a demo batch — say so on camera or redeploy.
3. Dismiss the Chrome banner, hide the bookmarks bar (`Cmd+Shift+B`), close any
   video-call window, go full screen.
4. `Cmd+Shift+5` → Record Entire Screen → microphone on.

---

## Beat sheet

### 0:00–0:25 · The problem, before anything else
**On screen:** the landing page, already loaded. Do not scroll yet.

> "Software is starting to do people's shopping. You tell an assistant to
> reorder the groceries or find a laptop stand under two thousand rupees, and it
> goes and buys it for you. Razorpay and NPCI are piloting exactly that in India
> right now.
>
> Here is the problem nobody has solved. When one of those AI shoppers gives up
> halfway through buying something, the shop gets nothing. No email address. No
> phone number. No reason. Just a request that stopped.
>
> Every tool ever built for winning back a lost sale assumes there is a person
> on the other end you can email a discount code to. You cannot email a bot a
> coupon."

Let that line land. It's the whole pitch.

### 0:25–0:50 · What it is, in two sentences
**On screen:** click **Open the live console**. Land on Recovery.

> "So I built the thing that does work on a machine buyer. It watches the
> checkout, works out from the shop's own records why the agent walked away,
> fixes that one thing, and offers the product again.
>
> Two halves. Recovery wins back sales that already failed. Prevention finds the
> problems in the shop's product listings before they cost anything. Let me show
> you one sale, slowly."

### 0:50–2:10 · One shopper, one product, start to finish
**On screen:** click **Walkthrough**. It runs a single attempt slowly, on
purpose. Narrate as each stage lights up.

> "One AI shopper. It has a budget, and a spending limit its owner set.
>
> It reads the shop's product list. It picks something. It opens the product
> page to check the details against what it was told to buy.
>
> And it stops. It doesn't complain, it doesn't ask a question, it just stops.
>
> Because the listing was missing a spec it needed — the wattage wasn't there.
> A person would have shrugged and bought it anyway. Software won't buy what it
> can't verify.
>
> Now watch what the shop actually saw: two page reads and then silence. That's
> it. That's everything a real merchant has to work with.
>
> Handshake reads those same two page reads and works out the reason. Then —
> and this is the part I care most about — it asks permission. Eleven fixed
> rules. Is this allowed? Have we already tried twice? Would this cost too much
> margin? Does it need a human's consent?
>
> No AI runs at this step. An AI is allowed to figure out *why* the sale failed.
> It is never allowed to decide *whether to spend the shop's money*. That's a
> checklist, and it's the same checklist every time.
>
> Permission granted. So: fill in the missing wattage from the shop's own
> records, and offer the product to the same agent again.
>
> It comes back. It buys. Nine thousand rupees that was gone."

Never quote Walkthrough totals — it forces every attempt into treatment so the
recovery path always runs, and the console says so.

### 2:10–2:40 · Proof, not a claim
**On screen:** click any green row in the attempts list.

> "Click any rupee and you get the receipt.
>
> Top: what the shopper was buying, what it cost, what its spending limit was,
> and in one sentence why it stopped and what we did.
>
> Below that: the shop's raw traffic — every request, every response, the exact
> error.
>
> And at the bottom, the audit trail. Every step is stamped and chained to the
> one before it, like links. Change any entry and the chain breaks visibly. So a
> finance team can check what happened after the fact instead of taking my word
> for it.
>
> One more thing. The console also shows the real reason, labelled as the answer
> key. We planted these problems, so we know the truth. The part of the system
> that works out the reason never sees that answer key — it only exists so I can
> mark my own homework honestly."

### 2:40–3:20 · Two hundred at once, and what the numbers mean
**On screen:** **Recovery** → attempts `200` → **Run batch**. It streams for
about twenty seconds. Land on the result card.

> "Two hundred attempts. Forty-six failed, with two lakh rupees on the table.
>
> Sixty-seven percent of that came back.
>
> Now, the number that matters more. Half of these attempts were a control
> group — we deliberately left them alone. That group recovered five percent on
> its own, because some shoppers retry by themselves. Ours recovered sixty-seven.
> The gap between those two is what the product does. That's the honest figure,
> and it's why I built a control group instead of just showing you the big
> number.
>
> And the cost: for every hundred rupees we brought back, we gave away one rupee
> forty-seven in discounts. Almost all of these failures didn't need a discount
> at all. They needed correct data."

Then point at the two panels on the right.

> "This panel is every action the rules blocked. Ten times the system wasn't
> confident enough about the reason, so it refused to act rather than guess.
> Refusing is a feature. Guessing with someone else's money is not.
>
> And this one: how often it named the right reason, scored against the answer
> key. Zero point nine four out of one. Fourteen it couldn't classify at all, and
> those are listed too."

### 3:20–3:45 · The off switch
**On screen:** flip the **Kill switch** in the sidebar to on, run 200 again,
then switch it back and run once more.

Do it as a before-and-after pair, not a mid-run flip — the batch finishes faster
than you can talk.

> "Kill switch on. Same two hundred attempts. Every reason still diagnosed
> correctly — and not one rupee moves. Discounts given: zero.
>
> A few still show as recovered. Those are shoppers that retried on their own,
> and the audit trail credits them to the shopper, not to us. I'd rather show
> you that than round it away.
>
> Switch off, run it again: thirty-six recovered, one lakh thirty-six thousand.
> Nothing changed except a human's permission."

### 3:45–4:30 · The half that needs no integration
**On screen:** **Prevention** → **Scan catalogue** at 300.

> "Everything so far is cleanup after the fact. But the missing spec that cost
> nine thousand rupees is still missing from that listing. It'll stop the next
> shopper too, and the one after that.
>
> So: point AI shoppers at the shop's listings on purpose. Three hundred tries,
> no problems planted — every failure is the shop's own data.
>
> The shop scores eighty-four percent ready for machine buyers. One missing
> field, on one listing, was refusing sixty-three thousand rupees.
>
> Then fix the worst seven listings and send the exact same shoppers again.
> Failures go from thirty-five to three. One lakh twenty-three thousand rupees
> recovered — and it stays recovered, because the field is now filled in.
>
> Same shoppers, same decisions, only the listings changed. So that's a
> measurement, not a forecast.
>
> And this half needs no integration whatsoever. Point it at a public product
> feed and it works today."

### 4:30–4:55 · What's real, and the one thing missing
**On screen:** the method line under the controls, then the sidebar pills.

> "What's real: the payments run through Razorpay's test system, and the
> shoppers' decisions come from a real language model. The shop's catalogue and
> the problems in it are ones I created — and both groups, treated and control,
> shop the same catalogue, so the gap between them measures the product and not
> the shop.
>
> Every screen states which setup produced its numbers. The whole run
> reproduces from a seed, to the rupee.
>
> The honest gap: today, no AI shopper checks back for a second offer. That
> doesn't exist in any payment standard yet. Somebody has to define it — and a
> payments company sitting between thousands of merchants is the obvious one to
> do it."

Stop recording. No outro, no thank-you slide.

---

## Rules while recording

**Show the weak numbers on screen.** The refusals, the fourteen it couldn't
classify, the one-rupee-forty-seven of discount, the method line. Volunteering
them is what makes the strong numbers believable.

**Say "shopper" and "listing", not "agent session" and "SKU".** The console now
does the same — rows read *"Induction Cooktop Mk II — agent stopped: the listing
was missing a spec it needed to commit"*.

**Never quote Walkthrough totals.** One attempt, forced into treatment. It's a
demonstration of the mechanism, not a measurement.

**Don't apologise for the simulation.** State it once, plainly, in the last
thirty seconds, and move on. Every measured result in the world states its
method.

---

## The four questions you will be asked

**"Your data is made up."** The catalogue and the planted problems are, and it
says so on screen. The payments are real Razorpay test-mode orders and the
shoppers' decisions come from a real model. Both groups shop the same catalogue,
so the gap measures the product. And because I planted the problems, I know the
right answers — which is the only reason I can report how often it diagnoses
correctly instead of just asserting that it does.

**"Seventy-one percent recovery is not believable."** For human shoppers, no.
Human abandonment is about hesitation, and a discount barely moves it. Machine
abandonment is mechanical: supply the missing wattage and the same shopper buys,
every time. The rate also depends on the mix of problems I chose, which is
exactly why I show the breakdown by cause instead of one blended number —
missing-data problems recover fully, ones needing a person's consent about half,
ones where the money genuinely isn't there, close to nothing.

**"The kill switch still recovered twenty-six thousand rupees."** Those are
shoppers that retried and succeeded without us. The audit trail records them as
the shopper's own doing, and the discount given is zero because no action ran.
It's the same effect the control group measures.

**"Is it production ready?"** No, and the README says so under Honest
limitations. It's a working prototype that proves the mechanism against real
payment infrastructure and puts a rupee figure on the opportunity. The gaps are
listed: no catalogue-system connector, no multi-tenancy, the priors in the rules
are set by hand rather than measured, and the second-offer step doesn't exist in
any payment standard yet.
